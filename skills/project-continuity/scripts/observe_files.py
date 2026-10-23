#!/usr/bin/env python3
"""Observe explicitly selected files; never execute project commands or certify completion."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

MAX_MANIFEST = 1048576
ROLES = {'source', 'input', 'output', 'check', 'other'}
DIR_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
FILE_FLAGS = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC


class Invalid(ValueError):
    pass


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise Invalid('duplicate JSON key')
        result[key] = value
    return result


def reject_constant(_):
    raise Invalid('nonfinite JSON value')


def load_manifest(name, max_files):
    if name == '-':
        data = sys.stdin.buffer.read(MAX_MANIFEST + 1)
    else:
        fd = os.open(name, FILE_FLAGS)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise Invalid('manifest must be a regular JSON file or stdin')
            with os.fdopen(fd, 'rb', closefd=False) as stream:
                data = stream.read(MAX_MANIFEST + 1)
        finally:
            os.close(fd)
    if len(data) > MAX_MANIFEST:
        raise Invalid('manifest exceeds 1 MiB')
    doc = json.loads(data.decode('utf-8'), object_pairs_hook=unique,
                     parse_constant=reject_constant)
    if not isinstance(doc, dict) or set(doc) != {'version', 'files'}:
        raise Invalid('expected version and files')
    if type(doc['version']) is not int or doc['version'] != 1:
        raise Invalid('unsupported manifest version')
    if not isinstance(doc['files'], list) or not 1 <= len(doc['files']) <= max_files:
        raise Invalid('file count outside selected limit')
    seen = set()
    for entry in doc['files']:
        if not isinstance(entry, dict) or not {'path', 'role'} <= set(entry) or set(entry) - {'path', 'role', 'expected_sha256'}:
            raise Invalid('invalid manifest entry fields')
        if not isinstance(entry['path'], str) or entry['path'] in seen:
            raise Invalid('paths must be unique strings')
        seen.add(entry['path'])
        if not isinstance(entry['role'], str) or entry['role'] not in ROLES:
            raise Invalid('unsupported role')
        if 'expected_sha256' in entry and (not isinstance(entry['expected_sha256'], str)
                or not re.fullmatch(r'[a-f0-9]{64}', entry['expected_sha256'])):
            raise Invalid('invalid expected SHA-256')
    return doc['files']


def identity(info):
    return info.st_dev, info.st_ino


def metadata(info):
    return {'dev': info.st_dev, 'ino': info.st_ino, 'size': info.st_size,
            'mtime_ns': info.st_mtime_ns, 'ctime_ns': info.st_ctime_ns}


def components(path):
    try:
        os.fsencode(path)
    except UnicodeError:
        return None
    parts = path.split('/')
    if path.startswith('/') or '\0' in path or any(p in ['', '.', '..'] for p in parts):
        return None
    return parts


@contextmanager
def parent_fd(rootfd, parts):
    """At most one intermediate directory FD; every component refuses symlinks."""
    current = os.dup(rootfd)
    chain = []
    try:
        for part in parts:
            info = os.stat(part, dir_fd=current, follow_symlinks=False)
            if not stat.S_ISDIR(info.st_mode):
                raise NotADirectoryError(errno.ENOTDIR, 'unsupported path component')
            child = os.open(part, DIR_FLAGS, dir_fd=current)
            os.close(current)
            current = child
            if identity(info) != identity(os.fstat(current)):
                raise Invalid('directory changed during observation')
            chain.append(identity(info))
        yield current, chain
    finally:
        os.close(current)


def os_state(exc):
    if exc.errno == errno.ENOENT:
        return 'missing'
    if exc.errno in [errno.ELOOP, errno.ENOTDIR, errno.ENXIO]:
        return 'unsupported_type'
    return 'unreadable'


def observe(rootfd, entry, limits, budget):
    result = {'path': entry['path'], 'role': entry['role'],
              'expected_sha256': entry.get('expected_sha256'), 'state': None,
              'observed': None, 'sha256': None}
    parts = components(entry['path'])
    if parts is None:
        result['state'] = 'outside_scope'
        return result
    try:
        with parent_fd(rootfd, parts[:-1]) as (directory, chain):
            named = os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)
            result['observed'] = metadata(named)
            if not stat.S_ISREG(named.st_mode):
                result['state'] = 'unsupported_type'
                return result
            fd = os.open(parts[-1], FILE_FLAGS, dir_fd=directory)
            try:
                before = os.fstat(fd)
                if not stat.S_ISREG(before.st_mode):
                    result['state'] = 'unsupported_type'
                    return result
                if metadata(named) != metadata(before):
                    raise Invalid('file replaced before observation')
                result['observed'] = metadata(before)
                remaining = limits['max_total_bytes'] - budget[0]
                if before.st_size > min(limits['max_file_bytes'], remaining):
                    result['state'] = 'limit_exceeded'
                    return result
                digest = hashlib.sha256()
                read = 0
                incomplete = False
                # Metadata size does not prove EOF (including regular pseudo-files).
                # Without allowance for a positive-length EOF read, withhold hash.
                while True:
                    allowance = min(limits['max_file_bytes'] - read,
                                    limits['max_total_bytes'] - budget[0])
                    if allowance <= 0:
                        incomplete = True
                        result['reason'] = 'byte_budget_exhausted_before_eof'
                        break
                    chunk = os.read(fd, min(65536, allowance))
                    if not chunk:
                        break
                    read += len(chunk)
                    budget[0] += len(chunk)
                    digest.update(chunk)
                # Checking identity/metadata costs no payload allowance. It remains
                # necessary at the cap: detected change is more informative than
                # budget-only incompleteness, and neither can yield a digest.
                try:
                    after = os.fstat(fd)
                    current = os.stat(parts[-1], dir_fd=directory, follow_symlinks=False)
                    if metadata(before) != metadata(after) or metadata(after) != metadata(current):
                        raise Invalid('file changed during observation')
                    with parent_fd(rootfd, parts[:-1]) as (again, final_chain):
                        final = os.stat(parts[-1], dir_fd=again, follow_symlinks=False)
                        if chain != final_chain or metadata(final) != metadata(after):
                            raise Invalid('path changed during observation')
                except OSError as exc:
                    raise Invalid('path unavailable after reading') from exc
                if incomplete:
                    result['state'] = 'limit_exceeded'
                    return result
                result['sha256'] = digest.hexdigest()
                baseline = entry.get('expected_sha256')
                result['state'] = ('present_without_baseline' if baseline is None else
                                   'match' if baseline == result['sha256'] else 'changed')
            finally:
                os.close(fd)
    except Invalid:
        result.update(state='unstable_during_read', sha256=None)
    except OSError as exc:
        result.update(state=os_state(exc), sha256=None, errno=exc.errno)
    return result


def collect(root, items, limits):
    supplied = Path(root)
    if not supplied.is_absolute() or supplied != supplied.resolve(strict=True):
        raise Invalid('root must be an existing canonical absolute directory')
    # Protect every ancestor at acquisition, not only the final root component.
    # resolve() alone cannot prevent a subsequent ancestor symlink substitution.
    if supplied.anchor != '/':
        raise Invalid('unsupported root anchor')
    slashfd = os.open('/', DIR_FLAGS)
    try:
        with parent_fd(slashfd, supplied.parts[1:]) as (rootfd, _):
            initial = os.fstat(rootfd)
            budget = [0]
            results = [observe(rootfd, entry, limits, budget) for entry in items]
            if (supplied != supplied.resolve(strict=True)
                    or identity(os.stat(supplied, follow_symlinks=False)) != identity(initial)):
                # All old-root observations are invalid, including missing/adverse.
                raise Invalid('root changed during observation')
            return {'version': 1, 'root': str(supplied),
                    'observed_at': datetime.now(timezone.utc).isoformat(),
                    'collector': {'version': '0.1.0', 'python': sys.version.split()[0]},
                    'limits': limits, 'bytes_read': budget[0], 'results': results}
    finally:
        os.close(slashfd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    parser.add_argument('--manifest', required=True)
    parser.add_argument('--max-files', type=int, default=64)
    parser.add_argument('--max-file-bytes', type=int, default=33554432)
    parser.add_argument('--max-total-bytes', type=int, default=134217728)
    args = parser.parse_args()
    limits = {'max_files': args.max_files, 'max_file_bytes': args.max_file_bytes,
              'max_total_bytes': args.max_total_bytes}
    for name, cap in [('max_files', 1024), ('max_file_bytes', 1073741824),
                      ('max_total_bytes', 4294967296)]:
        if not 1 <= limits[name] <= cap:
            parser.error('limit outside supported positive range')
    try:
        items = load_manifest(args.manifest, args.max_files)
    except (OSError, ValueError, TypeError, UnicodeError, RecursionError):
        print('Invalid continuity observation manifest.', file=sys.stderr)
        return 2
    try:
        report = collect(args.root, items, limits)
    except (OSError, ValueError, RuntimeError):
        print('Cannot observe the selected canonical root.', file=sys.stderr)
        return 1
    print(json.dumps(report, ensure_ascii=True, allow_nan=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
