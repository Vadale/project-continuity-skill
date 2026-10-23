# Evidence on resumption

Assess the proposition the user actually needs. A checkpoint's list is not
necessarily the complete deliverable list. Distinguish these per-claim states:

| State | Meaning |
| --- | --- |
| `supported` | Current relevant evidence supports this specific proposition within the observed scope |
| `historical_only` | Evidence describes a past outcome; current applicability is unestablished |
| `needs_recheck` | A relevant dependency or environment changed, so this current proposition needs a new scoped check |
| `contradicted` | Current observations conflict with the proposition, such as a required delivered artifact being absent |
| `unknown` | Necessary evidence is missing, unreadable, incomplete or cannot be bound to the asserted execution |

One file observation can affect several propositions differently. A missing plot
contradicts “the requested deliverables are available”; it does not prove that a
previous model fit failed. A changed analysis script does not invalidate unrelated
facts that never depended on it. Preserve earlier results and say which current
assertions can reuse them. When a claim is ambiguous, state the proposition before
assessing it; avoid a global verified badge.

Do not infer genuine test execution from plausible logs or hashes alone. Use an
actual run receipt and relevant source/input/output identities where available.
A run recorded without sufficient execution identity remains limited. Capturing
an immutable executable before a future run can help; hashing its mutable pathname
later cannot recover an already lost process image. This collector performs no
process attestation. It also does not establish statistical correctness, rights,
authorization, artifact quality or customer usefulness.

## Collector

Python standard library, tested target Python 3.15.0 and Unix descriptor APIs.
Python 3.11+ is intended, not independently tested here. Requires O_NOFOLLOW and
O_DIRECTORY; no Windows portability claim. The helper is optional. Unsupported
paths or unavailable Python do not imply project failure: use bounded manual
inspection when appropriate and record the actual route/limits.

Prepare a small manifest from the relevant evidence dependencies, for example:

```json
{"version":1,"files":[{"path":"analysis.py","role":"source"},{"path":"figures/result.svg","role":"output"}]}
```

```sh
python /absolute/skill/scripts/observe_files.py \
  --root /absolute/project --manifest /absolute/selected-files.json
```

Use an existing canonical absolute root without symlinks. Files are exact relative
Unix paths; no glob expansion, recursion or ignore filtering. Roles are `source`,
`input`, `output`, `check`, `other` and confer no trust. Optional
`expected_sha256` must be a previously recorded 64-character lowercase digest;
do not generate a current digest and relabel it as a past baseline. Unknown JSON
fields, duplicate keys/paths, nonfinite values and invalid types reject.

Output includes observation time, collector/runtime identity, configured limits,
actual content bytes read and ordered results with path/role/baseline/state,
observed dev/inode/size/mtime_ns/ctime_ns and a stable SHA-256 or null.

- `match` / `changed`: stable current content compared with the supplied baseline.
- `present_without_baseline`: stable current content observed, no earlier identity supplied.
- `missing`: requested file or component unavailable at that path.
- `outside_scope`: unsafe/escaping lexical path; not read.
- `unsupported_type`: symlink, nonregular file or unsupported path component; not followed.
- `unreadable`, `limit_exceeded`, `unstable_during_read`: incomplete evidence, no trusted digest.

Exit 0 means an observation report was produced, including adverse states; it does
not mean verification passed. Invalid requests exit 2, unavailable/unsafe root or
unreportable failures exit 1. Never replace `missing`/`unreadable` with invented
content or silently skip entries. Metadata timestamps are not observation time.

Defaults: 64 files, 32 MiB per file, 128 MiB total content. Explicit positive
overrides: `--max-files`, `--max-file-bytes`, `--max-total-bytes`, capped at 1024
files, 1 GiB/file and 4 GiB total. A digest requires observed EOF within the
allowance. An ordinary file exactly at either byte cap can therefore return
`limit_exceeded` with `reason:byte_budget_exhausted_before_eof`; this does not prove
it is larger. For known N-byte content, both per-file and remaining total budgets
need headroom beyond N, or use a smaller invocation/another authorized observation
route. No hidden extra byte is read beyond a budget. st_size is metadata, not EOF
proof; digests identify the observed stream with sampled metadata/identity checks,
not an atomic content snapshot. Identity/path/metadata checks still run after an
incomplete read: detected instability takes precedence over a budget-only state,
with no digest and the budget reason retained. Root replacement invalidates the
whole observation (exit 1), including missing/adverse facts. Manifest maximum 1 MiB. No network, subprocess,
project command execution, content echo or file writes. Concurrent changes may
invalidate an observation; these bounds are not a malicious-OS or same-user
security boundary. Store the report only where authorized; do not automatically
publish project paths or private checkpoints.
