# Loop L4 listening-evidence report

Date: 2026-07-12
Status: validation evidence for issue #23 and PR #31; synthetic sessions validate the harness only and make no instrument-quality or release claim.

## Evidence contracts

- Experiment and session JSON are schema-validated, reject unknown fields, and bind every session to the exact experiment digest.
- Python and browser canonicalization use the same finite IEEE-double representation, reject unsafe integers and non-finite values, and are regression-tested on integer-valued, ordinary decimal, and small scientific-notation values.
- The seeded randomization records both condition presentation and trial order. The analyzer independently reconstructs both and rejects tampering.
- Campaign listening bundles are self-contained inside the sealed iteration. Every baseline and candidate source is SHA-256 identified, independently normalized to the declared BS.1770 integrated-loudness target, verified after writing, and recorded with gain/loudness provenance.
- The browser requires at least the experiment-declared playback count for every visible condition before submission. The analyzer also excludes insufficient-playback sessions so edited or externally produced evidence cannot bypass the rule.
- Raw listener responses, pseudonymous listener/setup metadata, play counts, seed, randomized order, exclusions, and uncertainty remain in the JSON analysis. `quality_verdict` is always null.

## Hidden-reference and anchor pilot

The committed equation-generated MUSHRA pilot contains one explicit reference, one bit-identical hidden reference, one candidate, and one degraded anchor at -23 LUFS. Six deterministic synthetic sessions are submitted; five are included, and the session rating the hidden reference below the declared threshold is retained raw and excluded with an explicit reason. Bootstrap and Wilson uncertainty are deterministic. This pilot demonstrates harness behavior only; the ratings are not human evidence.

## Campaign round trip

The L2 campaign runner now replaces its label-revealing A/B page with a sealed `listening/` experiment whenever a baseline-backed run reaches `candidate` or `listening_required`. The audit creates a temporary baseline/candidate campaign, prepares its level-matched bundle, loads the bundle without an experiment query override, verifies no role or filename leaks into visible text, plays every condition, exports a browser session, and passes that exact export through the Python analyzer. Browser and Python experiment digests, presentation order, trial order, raw choice, raw-session retention, and null verdict all agree.

## Deliberate limits

- No real listener preference result is committed or inferred from the synthetic pilot.
- The harness records evidence and uncertainty; it does not decide whether a candidate ships.
- Learned embeddings remain absent. Their weights, license, offline execution, and domain validity still require a separate review.
- Raw human session files remain local unless the experiment owner deliberately preserves them as evidence.

## Reproduction

```sh
python3 -m pip install -r scripts/dev/requirements-loop.txt
npm install
npx playwright install chromium
npm run audit:listening
```
