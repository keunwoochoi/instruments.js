# String and horn families: the continuously-excited instrument

Date: 2026-07-13
Status: draft — proposes scope, anchor instruments, and a staged plan for issue #50.

Owner selections recorded 2026-07-13 (issue #50 acceptance criteria 1–2):
- **First string anchor: cello** (bowed).
- **Horn family scope: trombone, trumpet, saxophone** — "horn" is widened past brass to include the
  single-reed saxophone. Trombone is proposed as the *first* anchor of the three (rationale below).
- **Sequencing: fold the minimum gesture set into this campaign** rather than blocking on the full
  #12 MPE architecture.

This doc authorizes **no implementation**. It does not authorize a broad orchestra, additional GM
families, a product-budget increase, or any port. Each phase below needs its own issue, and any
port needs `skills/port-audit` first.

## Motivation

1. The owner wants to expand into strings and horns (#50).
2. #50 warned against silently collapsing "strings" to one instrument or assuming one brass. The
   owner has now made both choices explicit, so this doc can be concrete.
3. #50 asserted the repo "already has reusable … breath/control … building blocks." **This is not
   true and the plan must not be built on it.** Verified against `crates/dsp/src/`: there is no
   breath, bow, reed, or lip code anywhere, and no continuous-control path of any kind.

## Thesis

**The engine cannot currently make a bowed or blown sound, and the missing piece is not the bow or
the reed — it is the sustained gesture that drives them.**

The entire note-scoped WASM ABI is `ij_note_on(track, midi, vel)` and `ij_note_off(track, midi)`.
Nothing about a sounding note can change. That is sufficient for every instrument the engine has
today, because a struck or plucked instrument is *fully determined at the moment of excitation* —
after the hammer leaves the string or the pick leaves the string, the note is just a decay.

A bowed or blown instrument is the opposite. Its excitation is **continuous and coextensive with
the note**: bow force and bow position are being applied for the entire duration; breath pressure
and embouchure are being applied for the entire duration. Take that away and there is no
instrument left — you have a filtered oscillator with an envelope. **That is a pad.** And it is
exactly, literally what ships today: in the GM map, `strings → 8` and `brass → 8`, and instrument
8 is the subtractive synth pad.

So the bet is not "add a violin model." It is: **build the continuously-excited nonlinear
waveguide once, and make all four instruments variations on it.**

That unification is real, not rhetorical. McIntyre, Schumacher & Woodhouse (1983), *"On the
oscillations of musical instruments"*, treats the bowed string, the reed woodwind, and the flute
jet as **one object**: a nonlinear scattering junction embedded in a delay loop, driven by a
continuous control. The lip valve of a brass instrument is the same object with an outward-striking
valve. Cello, trombone, trumpet, and saxophone are then **bore/body/junction parameterizations of a
single new core** — which is the shared-DSP-leverage argument #50 asked for, and it is the reason
these four are the right four to take together.

## Evidence base

**Verified in-repo (this branch, read directly from source):**
- Note-scoped ABI is `ij_note_on` / `ij_note_off` only. `ij_pedal` is track-wide. There is no
  per-note continuous control, and no note identity — notes are addressed by `(track, midi)`,
  which is already ambiguous for repeated same-key strikes.
- `strings`, `brass`, `voice`, and `synth` all map to instrument 8 (`SynthPad`) in the GM group
  map (`scripts/dev/render-demo.mjs`, mirroring `packages/core`).
- No bow, breath, reed, or lip code exists in `crates/dsp/`.
- `StringLoop` is a **single-delay-loop Karplus-Strong waveguide.** This matters: it cannot host a
  bow. A friction junction needs the string velocity arriving at the bow point **from both
  directions** so it can scatter — that requires a two-rail (bidirectional) waveguide. **The
  existing string primitive is not reusable for the cello.** This is the largest honest cost in
  the plan.
- Measured voice costs on this machine (48 kHz, 2666.7 µs budget): synth pad 0.40 µs/voice,
  guitar 3.70, bass 3.89, e-piano 1.96, piano 13.22. Idle engine 19.9 µs/quantum.

**Licensing — already cleared, which is unusually lucky:**
- **VSCO-2-CE** (`github.com/sgossner/VSCO-2-CE`), **CC0-1.0, already verified in
  `agentic-docs/licensing.md`.** It is a full orchestral library and contains solo **cello,
  trombone, trumpet, and saxophone** — all four selected instruments. The ledger currently cites it
  only for crash and upright-piano references. *To confirm at P0: per-instrument articulation and
  dynamic-layer coverage is adequate; CC0 grant re-verified.*
- **STK** (`thestk/stk`), **MIT, already marked port-approved in the ledger**, ships `Bowed`,
  `Brass`, `Saxofony`, `Clarinet`, and `BandedWaveguide` — Cook & Scavone's canonical
  implementations of precisely the MSW framework above. This is a license-clean starting point.
  **Caveat, stated up front:** STK's instruments are pedagogical and are widely (and fairly)
  described as recognizable but toy-like. We port them as a **correctness oracle and structural
  reference**, not as the shipping model. `skills/port-audit` and its legacy-flaws checklist are
  mandatory before any line is copied.

Literature anchors (papers only): McIntyre/Schumacher/Woodhouse (1983) for the unified framework;
Friedlander and Schumacher on the bowed-string friction characteristic and its multi-valued
(hysteretic) solution; Woodhouse on bow-bridge distance and Helmholtz corner sharpening; Smith's
waveguide formulation; Msallam/Vergez et al. and Campbell on brass lip valves and **nonlinear wave
steepening in the bore** (the ff "brassiness" that sampled brass structurally cannot do);
Benade on conical bores and tone-hole lattice cutoff for the saxophone; Scavone's thesis on
conical waveguides.

## Design

### Layer 0 — The minimum gesture set (the #12 slice)

Derive the control requirement from the physics rather than from a MIDI spec, then observe that
they coincide.

- A **bowed string** needs, continuously: bow **force/velocity** (the sustain control — no force,
  no sound), bow-bridge **distance β** (sets brightness and Helmholtz corner sharpness), and
  continuous **pitch** (vibrato, portamento).
- A **brass/reed** instrument needs, continuously: **breath pressure** (the sustain control),
  **embouchure/lip tension** (which bore mode the instrument locks onto — "slotting"), and
  continuous **pitch** (the trombone slide is *nothing but* continuous pitch).

That is three continuous per-note scalars. They map exactly onto **MPE's three per-note
dimensions** — X (pitch), Y (timbre), Z (pressure). So the minimum gesture set the physics demands
*is* MPE's X/Y/Z. We do not invent a bespoke control path; we implement the industry-standard
three, and that is precisely the minimum. This is a strong de-risking result for #12: it gives that
issue a concrete, physics-derived floor instead of an open-ended architecture.

**ABI consequence (real work, not a footnote):** per-note control requires per-note *identity*.
`ij_note_on` must return a note/voice id, and expression must be addressed to it:

```
ij_note_on(track, midi, vel) -> u32 note_id
ij_note_expr(note_id, dim, value)      // dim ∈ {pitch, timbre, pressure}
ij_note_off(note_id)
```

This also fixes an existing latent bug — `(track, midi)` addressing is already ambiguous when the
same key is struck twice while ringing. Event transport must stay fixed-capacity and
allocation-free (this is issue #34's territory; treat it as a dependency, not a rewrite).

### Layer 1 — The MSW nonlinear excitation core (shared by all four instruments)

Two new primitives, both allocation-free and bounded:

**`BiWaveguide`** — a two-rail bidirectional waveguide (left- and right-going delay lines) with a
frequency-dependent loss/reflection filter at each termination, and a scattering port at an
arbitrary interior point. This is the thing `StringLoop` is not.

**`NonlinearJunction`** — the MSW valve, solved each sample against the waveguide's Thévenin
impedance, in three specializations:
- **Bow:** stick–slip friction characteristic (velocity-dependent, hysteretic).
- **Reed:** pressure-controlled beating valve — reed spring displacement plus Bernoulli flow;
  the reed can close.
- **Lip:** outward-striking mass–spring–damper lip valve whose own resonance interacts with the
  bore modes — this is *why* brass slots onto harmonics, and it must be modeled as a resonance,
  not a curve.

**Audio-thread constraint drives the solution method.** The MSW junction is a nonlinear equation
per sample. A Newton iteration is data-dependent and branchy — the same objection this project
already raised against Architecture B in the piano doc (`2026-07-13-higher-capacity-piano.md`).
Use instead a **precomputed lookup of the friction/valve characteristic intersected with the
waveguide impedance line** — constant-time, branch-free, allocation-free, denormal-safe, and
SIMD-friendly across the SoA voice bank. Table synthesis happens at init.

### Layer 2 — Bores and bodies

- **Cello:** two-rail bowed string → bridge → body. The body is the **same shared modal-body
  primitive the piano campaign is building** (`2026-07-13-higher-capacity-piano.md`, A2), with
  different modes and a different bridge admittance. This is genuine, load-bearing shared leverage
  between the two campaigns, and it is a reason to sequence the piano's A2 first.
- **Trombone / trumpet:** a bore waveguide terminated by a **bell reflection function** — the bell
  is essentially a high-pass: low modes reflect back to sustain the oscillation, highs radiate out.
  At *ff*, add **nonlinear wave steepening** in the bore (shock formation). This is the single most
  valuable thing physical modeling buys here: the *blat* of a loud brass note is a propagation
  nonlinearity, and no sample library can produce it as a continuous function of dynamic.
  Trombone and trumpet differ mainly in bore profile, bell, and lip parameters — trumpet is
  largely a reparameterization once trombone exists.
- **Saxophone:** a **conical** bore (which requires spherical wave variables, not the cylindrical
  formulation — a genuinely different waveguide) plus a **tone-hole lattice** with its
  characteristic cutoff frequency, and the reed junction at the mouthpiece. This is the most
  new-DSP of the three horns and is correctly sequenced last.

### Why trombone first among the three horns

Simplest bore of the brass; the slide is pure continuous pitch, so it *forces the Layer-0 gesture
path to be correct* rather than letting us fake it; and once it works, trumpet is mostly
parameterization. Saxophone needs a new (conical) bore type and should follow.

## Phased plan

Each phase is PR-sized, gated, and gets its own dependency-linked issue.

**S0 — Minimum gesture set.** Note ids in the ABI; three continuous per-note dimensions; MPE and
CC (breath CC2, CC74) input in `packages/midi`; a playground control surface. **Ships no new
instrument and is independently valuable** — it is the #12 slice.
*Gate:* a sounding note's pressure modulates sample-accurately; zero allocation on the event path;
fixed-capacity transport; existing instruments bit-identical (drift-check); full-arrangement
`dsp-bench` unchanged.

**S1 — `BiWaveguide` + table-based MSW junction.** Port-audit STK first; build the core.
*Gate:* self-oscillation starts and stops with the pressure control; Helmholtz motion visible in
the string waveform; constant-time junction (no data-dependent iteration); allocation- and
lock-free; denormal-safe at both 44.1 and 48 kHz.

**S2 — Cello** (first string anchor). Bowed string + shared modal body + bridge admittance.
*Gate:* license-clean VSCO-2-CE corpus staged by checksum; isolated articulations (sustain,
détaché, legato transition, dynamics ladder, vibrato); **at least one multi-track musical
context**; owner blind listening + persona panel decide.

**S3 — Trombone** (first horn anchor). Lip valve + bore + bell reflection + slide.
*Gate:* as S2, plus two horn-specific gates — the bore must **slot** (lip tension selects the
harmonic) and *ff* must **brassen** (measurable spectral enrichment with dynamic, not just level).

**S4 — Trumpet.** Bore/bell/lip reparameterization of S3. *Gate:* as S3.

**S5 — Saxophone.** Conical bore + tone-hole lattice + reed junction. *Gate:* as S3, minus
slotting, plus register-break behavior.

## Budgets

Requirements, not measurements. Any prototype that cannot meet these is rejected at its gate.

| Budget | Requirement |
|---|---|
| Per-voice CPU @48 kHz | **≤ 10 µs/voice** — i.e. between guitar (3.70) and piano (13.22). A table-based junction plus a two-rail guide should land well under this; if it does not, the design is wrong. |
| Arrangement gate | An orchestral-ish arrangement (8 cello + 4 trombone + 16 piano + bass + drums) stays **≤ 50%** of the 2.67 ms budget — the architecture doc's exit gate. |
| Per-voice state | **≤ 20 KB.** Remember the piano lesson: `Kernel` is an enum sized by its largest variant, so per-voice state is paid ×64 across the whole voice bank. A bowed-string voice must not become the new size-setting variant. |
| Shared state | Junction lookup tables synthesized at init, **≤ 64 KB total**, shared across all voices. |
| WASM | **≤ +25 KB raw** for the whole family; core + one instrument stays **≤ 100 KB gz**. |
| Init | **≤ 20 ms** for table synthesis; allocation-free thereafter. |
| Degradation | Voice stealing unchanged. Continuous-control events are dropped-newest under transport saturation, never allocated for, and the drop is reported — no silent fallback. |

The audio-thread constitution is unchanged: no allocation, no locks, no denormals, **bounded work
per sample** (this is what rules out an iterative junction solver).

## Risks

1. **S0 is an ABI change** and touches the public API, event transport, and every existing
   instrument's call path. It is the highest-blast-radius phase and it is first. Mitigate with the
   existing drift-check tripwire (existing instruments must render byte-identically).
2. **The bowed string is the hardest sound in this plan to get right**, and cello is on the
   familiarity ladder's upper half. The stick-slip junction is easy to make *oscillate* and hard to
   make *musical*; a bad bowed string is instantly recognizable as fake. Expect several iterations
   and budget for owner listening early, not at the end.
3. **STK will tempt us to stop too early.** Its models will produce a recognizable cello and a
   recognizable trumpet quickly, and they will not be good enough. The port-audit legacy-flaws
   checklist exists for exactly this; the gates are owner listening, not "it sounds like a cello."
4. **Shared dependency on the piano campaign** (the modal body / bridge admittance primitive). If
   #49's A2 slips, S2 either waits or duplicates the primitive. Prefer waiting.

## Deferred until demanded

Violin, viola, double bass, string ensemble/section patches. French horn. Clarinet, flute, oboe,
bassoon (the reed and jet cores would make these cheap later — that is the point of Layer 1, but
they are not authorized here). Pizzicato and col legno articulations. Mutes (brass) and sul
ponticello / sul tasto (strings). Full MPE beyond the three-dimension minimum (that remains #12's
to own). Breath-controller hardware support. A room / early-reflection stage — wanted by every
family, owned by its own issue.
