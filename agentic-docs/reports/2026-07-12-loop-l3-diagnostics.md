# Loop L3 trajectory-diagnostics report

Date: 2026-07-12
Status: validation evidence for issue #22; this report evaluates metric behavior, not instrument quality.

## Added diagnostic surfaces

- Bounded 10 ms envelope and spectral-centroid trajectories retain raw values, normalized path cost, path length, maximum displacement, and the profile-owned warp limit.
- Fundamental-aware harmonic pairing reports per-harmonic render/reference frequency, cents residual, level residual, and aggregate absolute residuals around an explicitly declared expected fundamental.
- Per-harmonic 50 ms decay trajectories retain raw dB curves and bounded path evidence for the first six observable harmonics.
- Stereo diagnostics report native channel count, mid/side width, and inter-channel correlation before mono comparison.
- Profile-owned trust and warp thresholds are serialized in every report; kick timing is bounded more tightly and cymbal ultrasonic tolerance is explicitly distinct from pitched/default profiles.

## Synthetic validation

| Mutation | Expected response | Result |
|---|---|---|
| Identical decay trajectory | Zero envelope and partial-decay cost | Pass |
| Faster exponential decay | Envelope and fundamental-decay costs increase monotonically | Pass |
| Two-frame local shift | Bounded path cost falls relative to rigid alignment and maximum displacement stays within two frames | Pass |
| 440 Hz → 445 Hz detune | Fundamental-aware mean absolute cents residual increases from zero | Pass |
| Stereo phase difference → dual-mono collapse | Width falls and correlation rises | Pass |
| Profile selection | Kick warp and cymbal ultrasonic thresholds differ from default exactly as declared | Pass |

The equation-owned artifact fixture under metric `2026.07.12-l3` remains untrusted on crest, sample jump, and ultrasonic energy. Its bounded envelope cost is 3.4227 dB, centroid cost is 50.2173 semitones, mean absolute harmonic-frequency residual is 8.31 cents, and mean absolute harmonic-level residual is 0.60 dB across three audible matched harmonics. Harmonic summaries exclude components below −80 dB relative to the strongest matched partial so numerical-noise peaks cannot dominate the residual. These values are expected from the deliberately adversarial fixture and are not acceptance thresholds.

## Compatibility

The report schema advances from `1.0.0` to `1.1.0`, and the metric version advances from `2026.07.12-l1` to `2026.07.12-l3`. L1/L2 numeric baselines must not be silently reused; the campaign runner already rejects metric-version mismatch. Profile threshold values are now part of report configuration, so any future threshold change requires an intentional metric-version change and golden regeneration.
