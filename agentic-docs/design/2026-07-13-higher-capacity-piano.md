# Higher-capacity piano: make the box real

Date: 2026-07-13
Status: draft — proposes an architecture and a staged plan for issue #49.

This doc authorizes **nothing to ship**. It selects a first architectural bet, freezes a
comparator, and defines the budgets and gates a prototype must clear. It does **not** authorize
any piano model change, any product-budget increase, samples in the runtime, or any quality
claim. Owner blind listening and the persona panel remain the acceptance gates. Phase P0 (corpus
+ baseline freeze) must complete before any DSP phase begins.

## Motivation

1. The owner's judgment (issue #49): the current piano "has likely reached the ceiling of small
   parameter and local-topology changes." Post-#41 verdict was *"maybe yamaha p80 level. not bad
   i meant. good progress. but we can make it even better!!"* — a floor accepted, a ceiling raised.
2. The north star is unchanged: *"I want our piano sound to be as good as the Pianoteq sound"*
   (`2026-07-11-pianoteq-class-piano.md`).
3. That doc's own phase **P2 (soundboard/radiation) was never done**, and the modeling-loop audit
   (`agentic-docs/reports/2026-07-12-modeling-loop-audit.md`) names it "the weakest link."
   #49 is therefore not a blank-page redesign: it is P2, escalated from a filter swap to an
   architectural change, plus the coupling that P2 makes possible.
4. Issue #49 forbids "another single-parameter polish pass presented as the new architecture."
   The bet below changes the *topology* of the instrument, not its coefficients.

## Thesis

**Today the piano has no box.** The strings are modeled with real physics; everything downstream
of the strings is feed-forward cosmetics. String energy never passes through a soundboard, the
board never loads the string, and no string ever hears another string. The instrument is a set of
independent, well-modeled strings played into an EQ.

The bet: **spend the new capacity on the radiator and the coupling, not on the string and the
hammer.** Build a real frequency-dependent bridge admittance and a dense modal soundboard that is
**shared across all piano voices**, then close the loop so board motion returns into the strings.
Sympathetic resonance, pedal bloom, cross-note coupling, and a correct bass radiation balance then
emerge from the physics instead of being painted on — and, decisively, the dominant new cost is
**shared and polyphony-independent**, which is the only shape of spend that fits a 64-voice engine.

## Evidence base

### Baseline freeze (the comparator required by #49)

Measured on this machine, 128-frame quantum, from a clean release build of PR #41:

| Identity | Value |
|---|---|
| Commit | `0bf0ec3c4b4db7cb9aa7ed054ee4a056e1a95ed8` (`piano/hammer-contact-attack`, PR #41 head) |
| WASM sha256 | `1fd2dc6d2e47892f1f07e98e264887ac8334136cc9aacb4365c78ac7df801170` |
| WASM size | 163,430 B raw / 67,088 B gzip |

CPU, marginal cost per held voice (budget = 2666.7 µs @48 kHz, 2902.5 µs @44.1 kHz):

| Voices | 48 kHz | 44.1 kHz |
|---|---|---|
| piano, per voice | **13.22 µs** | 13.38 µs |
| piano ×16 | 240.1 µs (9.0%) | 237.1 µs (8.2%) |
| piano ×32 | 438.5 µs (16.4%) | 439.2 µs (15.1%) |
| piano ×64 | 870.5 µs (32.6%) | 887.4 µs (30.6%) |
| idle engine (shared body/reverb/mix) | 19.9 µs (0.75%) | 19.6 µs |

For scale, the same harness measures bass at 3.89 µs/voice, guitar 3.70, e-piano 1.96, synth pad
0.40. **The piano is already 3.4× the next-most-expensive voice in the engine.**

Memory (`std::mem::size_of`, same build):

| Struct | Bytes |
|---|---|
| `PianoVoice` | **25,760** |
| `Kernel` (enum) | 25,760 — *piano is the largest variant, so it sets the size* |
| `Voice` | 25,776 |
| **Voice bank (64 slots)** | **1,649,664** |
| `SympBank` × 16 tracks | 792,192 |

**The governing scaling law:** `Kernel` is an enum sized by its largest variant, so every one of
the 64 voice slots carries piano-sized state even when it holds a 280-byte marimba. **+1 KB of
per-voice piano state = +64 KB of engine.** Shared state costs ×1. Any architecture that spends
per-voice pays a 64× memory multiplier *and* a polyphony multiplier on CPU; any architecture that
spends shared pays neither. This single fact drives the recommendation below.

### Named residuals (each proposed mechanism below must cite one)

From a line-level audit of `crates/dsp/src/kernels.rs` at the baseline, plus the modeling-loop
audit and PR #41's own disclosures:

- **R1 — The soundboard is a knock generator, not a radiator.** `PIANO_BOARD_MODES = 12`, excited
  by a *synthetic raised-cosine pulse* (1–3 ms), not by string energy, and gated off entirely
  after 0.9 s. No string energy ever passes through a board. The string's own radiation path is
  pure EQ: a 10 kHz air lowpass, an `1 − e^(−t)` bloom gain, two one-pole highpasses, and one
  **fixed 270 Hz / −13 dB / Q 1.25 peaking dip** standing in for a measured mobility
  antiresonance — static and key-independent.
- **R2 — There is no bridge admittance.** The "bridge" is two scalars (`g0`, `g1`) plus a one-pole,
  solved to hit measured t60 targets. It couples the 2–3 unisons of *one note* and nothing else.
  The board never loads the string; there is no board→string path anywhere.
- **R3 — Sympathetic resonance is a fixed C-major chord.** `SympBank` is 12 Karplus-Strong loops
  on a **hardcoded tuning** — C2 G2 C3 E3 G3 A#3 C4 D4 E4 G4 A4 C5 — fed the track's mono mix
  feed-forward, with no return path into the strings and no relationship to the notes actually
  held. *Play in F# minor and the "sympathetic" bloom rings C major.* The pedal only changes loop
  loss and send level. This is issue #14's finding ("voices render in a vacuum"; "pedal-down
  should change the RESONANCE, not just note length") and it is worse than that issue knew.
- **R4 — Bass radiation excess: +15 dB at 20–60 Hz** vs reference (modeling-loop audit), a direct
  consequence of R1/R2 — there is no frequency-shaped mobility to load the bass strings.
- **R5 — Attack timbre residuals** (PR #41, disclosed): C4 *pp* attack centroid 359 Hz vs
  reference 423 Hz (still dark); A1 and C4 *ff* centroids run 3–4% high.
- **R6 — No re-strike into a ringing string.** PR #41 gives repeated strikes separate voices —
  confirmed independently here: piano ×64 costs 870 µs on #41 vs 659 µs on the sibling branch that
  still overwrites same-key voices. But a hammer striking an *already-ringing* string is still not
  modeled; the two voices simply sum.
- **R7 — Phantom/longitudinal partials are a squared-signal spray** through one measured formant,
  not a longitudinal wave. No true f_i + f_j combination comb.
- **R8 — No duplex/aliquot scale**; no una corda, half-pedal, or sostenuto (P4 unstarted); the
  damper is a loss-coefficient rewrite with no felt contact dynamics.
- **R9 — ff aliasing, C7–C8**, routed to #13, open.
- **R10 — Everything is anechoic.** No room or early-reflection stage anywhere.

Literature anchors (papers only, per the licensing constitution — no copyleft source opened):
Weinreich (1977) on coupled piano strings and the prompt/aftersound split; Conklin (1996) on
soundboard and duplex behavior; Askenfelt & Jansson on bridge driving-point mobility; Giordano on
measured soundboard admittance; Skudrzyk's mean-value method for modal density of a plate;
Bank (2003) for the nonlinear-hammer + coupled-string + shared-soundboard recipe the architecture
doc already cites; Chabassier et al. and Bilbao for the full-PDE comparison in Architecture B;
Smith & Van Duyne for commuted synthesis and the dispersion-allpass technique already in use.

**Unverified / to be established in P0:** every reference number above that is a *comparison to a
reference recording* (R4, R5) currently traces to a scratchpad corpus that no longer exists and
cannot be rebuilt from the repo. See "The corpus problem" below. Until P0 lands, these residuals
are directionally trusted but not re-measurable, and **no phase gate may cite them**.

## Design

Two materially higher-capacity architectures, compared. Both are genuinely bigger models; they
differ in **where** the capacity goes.

### Architecture A — Reciprocal bridge + shared dense soundboard (recommended)

Spend on the radiator and the coupling. Three layers, each staged so it can fail cheaply.

**A1 — Frequency-dependent bridge admittance.** Replace the `g0`/`g1` scalars and the fixed 270 Hz
dip with a real driving-point mobility filter Y(ω) — a cascade of ~8–12 biquads per register,
fitted at init to published grand-bridge mobility curves. Strings *terminate into* it.
→ Addresses **R2**, **R4**, and the key-independence half of **R1**.

**A2 — Shared dense modal soundboard.** A 200–400 mode modal bank, **shared per engine**, stereo
pair, synthesized at init from a parametric modal-density and damping law (Skudrzyk mean-value —
*synthesized*, not a sampled IR; no sample data enters the runtime). It is driven by the **summed
bridge force of every piano voice**, and its output is the piano's radiated sound.
→ Addresses **R1**, **R4**, and gives the instrument a body that a per-voice EQ structurally cannot.
**Cost is O(modes) per engine, independent of polyphony.**

**A3 — Close the loop (the actual bet).** Board velocity returns into each string's termination as
a two-port wave-scattering junction (WDF-style, passive by construction, one-sample delay in the
loop). The board is then a *shared coupling medium*: every undamped string is re-excited by the
motion every other string put into the board.
→ Addresses **R3** (sympathetic resonance and pedal bloom become *emergent* and correctly tuned to
whatever is actually held — the fixed C-major bank is deleted, not fixed), **R6** (a ringing string
is a live resonator that a new strike genuinely couples into), and opens **R8** (duplex/aliquot
segments are just additional string terminations on the same board).

Retiring `SympBank` frees 792 KB and removes a structurally wrong mechanism rather than tuning it.

**The risk, stated plainly:** A3 creates a feedback loop between 64 strings and one board. Done
naively it is a delay-free loop and it will blow up. It must be formulated as an energy-passive
scattering junction with a unit delay, proven passive offline, and stress-tested at full
polyphony. This is the one hard technical problem in the proposal, and it is why A3 is staged last
and behind a flag.

### Architecture B — Full stiff-string PDE + implicit hammer collision (rejected as the *first* bet)

Spend on the string and the hammer.

**B1** — Replace the single-delay-loop waveguide with a modal or FDTD stiff string carrying two
transverse polarizations plus a longitudinal wave (→ **R7**, true phantom partials; **R5**).
**B2** — An implicit hammer–string collision solver (Newton, iteration-capped): real hammer mass,
felt hysteresis, genuine multiple contact and re-contact episodes (→ **R5**, **R6**).
**B3** — 2–4× oversampling of the contact (→ **R9**).

**Why not first.** The cost lands in exactly the wrong place:

- **CPU:** three rails × three strings plus a per-sample nonlinear solve is a 3–6× per-voice
  estimate. The piano is *already* 13.22 µs/voice. At 3× that is ~40 µs/voice → 32 voices =
  1,280 µs = **48% of budget for the piano alone**, before bass, drums, or any other track. It
  breaks the architecture doc's own 50%-at-32-voices exit gate on its own.
- **Memory:** adding polarization and longitudinal rails roughly triples the delay memory →
  `PianoVoice` ≈ 75 KB → **voice bank ≈ 4.8 MB**, paid by all 64 slots, for an instrument that may
  be one track of six.
- **Constitution:** a data-dependent Newton iteration count on the audio thread is bounded only by
  a cap, is branchy, and fits the SoA/SIMD voice bank badly.

B is not wrong physics — it is the right *second* investment. Its payoff is also larger *after* A,
because a truer string is more audible through a real radiator than through a static EQ.

### Recommendation

**Architecture A, staged A1 → A2 → A3.** It targets the residual that the project's own audit
already named the weakest link (R1/R2/R4); its dominant cost is shared and polyphony-independent,
which is the only spend shape the 64-slot enum and the arrangement budget can absorb; it delivers
issue #14 as a consequence of the physics rather than a bolt-on; and it can fail cheaply, because
A1 and A2 are strict improvements that carry no stability risk and A3 — the risky part — is a
separable, flagged, provable step.

## Phased plan

Each phase is PR-sized and gated. **No phase may make a quality claim on metrics alone** (#49).

**P0 — Corpus and baseline freeze.** *Blocks every other phase.* Commit a fetch-by-checksum recipe
that rebuilds the reference corpus from the licensing ledger's identities (URL + sha256 +
canonicalization), covering what #49 demands: isolated velocity/register anchors **plus chords,
repeats, pedal, and a musical phrase**. Freeze the #41 baseline (identity table above) as a
reproducible comparator.
*Gate:* corpus rebuilds byte-identically on a clean machine from the committed recipe; baseline
renders reproduce byte-identically from the frozen WASM digest.

**P1 — Bridge admittance (open loop).** A1 only; the board stays one-way.
*Gate:* bass 20–60 dB radiation excess falls from +15 dB to ≤ +3 dB against the P0 corpus; the
owner-liked decay is unchanged (per-partial t60 within ±10% of baseline); full-arrangement
`dsp-bench` shows ≤ +2 µs/voice.

**P2 — Shared dense soundboard (open loop).** A2; string energy finally passes through a board.
*Gate:* spectral envelope and decay-tail match improve against the P0 corpus; **shared CPU ≤ 80
µs/quantum (3% of budget), flat in polyphony**; per-voice cost unchanged; init ≤ 20 ms;
allocation-free after init.

**P3 — Close the loop.** A3; retire `SympBank`.
*Gate:* offline energy test proves passivity; 10-minute stability soak at 64 voices with pedal
down, zero NaN, no runaway; **sympathetic bloom provably tracks held notes** — render an F# minor
chord with pedal down and show the bloom spectrum contains no C-major partials (the baseline
fails this test by construction); pedal-down changes resonance, not just note length; full
arrangement within budget.

**P4 — Re-evaluate B** against the residuals that survive A.

Every phase: owner blind listening (AB vs the frozen baseline) and the persona panel decide
whether the added complexity earned its cost. Metrics gate iteration; they never gate acceptance.

## Budgets

Binding for the whole campaign. Exceeding any of these is an owner decision, not an implementer's.

| Budget | Baseline | Ceiling |
|---|---|---|
| Per-voice CPU @48 kHz | 13.22 µs | **≤ 20 µs** (≤1.5×) |
| Shared piano CPU | 0 | **≤ 80 µs/quantum** (3% of budget), polyphony-independent |
| Piano-led arrangement (32 piano + bass + drums) | ~16% | **≤ 50%** of 2.67 ms — the architecture doc's exit gate |
| Per-voice state | 25,760 B | **≤ 28 KB** (remember: ×64) |
| Shared board state | 0 | **≤ 32 KB** (+792 KB freed by retiring `SympBank`) |
| WASM | 163,430 B raw / 67,088 gz | **≤ +12 KB raw / ≤ +5 KB gz**; bundle stays ≤ 100 KB gz |
| Init | — | **≤ 20 ms**; allocation-free thereafter |
| Degradation | voice stealing | unchanged — the shared board is polyphony-independent, so under load we shed voices and **never** the body |

Projected at the P3 target: 32 × 20 + 80 shared + 20 idle + ~60 other tracks ≈ **800 µs ≈ 30%** of
budget. Headroom preserved.

The audio-thread constitution is not relaxed: no allocation, no locks, no denormals, bounded work
per sample. #49 authorizes more *cost*, not an exemption.

## The corpus problem (why P0 blocks everything)

The licensing ledger is rigorous and the references are correctly *not* committed. But there is no
executable recipe that rebuilds them: `stage_loop_pilot_refs.py` only fabricates synthetic
fixtures "for runner plumbing tests only," and `evals/corpus/`, `evals/incumbents/`, and
`evals/listening/` are empty. The fitting audio lived in a scratchpad that is gone.

Consequence: **every reference-relative number in this doc's residual list is currently
unfalsifiable**, and #49's own acceptance criteria — "frozen as a reproducible baseline with exact
executable and stimulus identities" and "exact licensed references cover … chords, repeats, pedal,
and a musical phrase" — cannot be met without fixing it. P0 is not bureaucracy; it is the
precondition for knowing whether A worked.

## Deferred until demanded

Architecture B in full (revisit at P4). Mic models, binaural, and listener-position rendering.
Historic temperaments. Morphing between piano models. Key/action mechanism simulation (escapement,
jack, repetition lever). Una corda and sostenuto (P4 of the original doc, after this campaign).
A room / early-reflection stage — genuinely wanted (R10) and named by the audit as the biggest
cross-family gap, but it is one shared FDN for *all* instruments and belongs in its own issue, not
smuggled into the piano.
