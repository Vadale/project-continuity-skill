# Resume from a checkpoint that overstates delivery

Fictional example; the table below illustrates evidence judgments, not a recorded run.

## Input and natural request

The handoff says an analysis and two figures were delivered. Current selected
files include the analysis receipt and first figure; the second figure is absent.
No evidence shows a relevant analysis-code change.

> We moved to a new chat. Check this handoff against the current files and finish
> the missing figure in the existing output folder. Do not rerun unchanged fits.

## What the result should contain

| Claim | Current judgment | Next step |
|---|---|---|
| Earlier analysis completed | Historical evidence can remain useful if its dependencies still match | Check only consequential dependencies |
| Both figures delivered | Current delivery is incomplete if the second required file is absent | Recover or create the missing figure within the existing mandate |
| The whole analysis failed | Not established by a missing output | Preserve the distinction between execution and delivery |

The assistant then performs the authorized missing work if the required tools
and inputs exist, verifies the result and updates the existing checkpoint. It
reports any blocking gap instead of inventing completion.

## When to use another workflow

A summary of an unrelated article is not a project handoff. A new project idea
with no prior work calls for kickoff rather than recovery.
