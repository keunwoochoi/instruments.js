# String and horn families: the continuously-excited instrument

Date: 2026-07-13
Status: draft (**revision 2**) — proposes scope, anchor instruments, and a staged plan for issue #50.

Revision 2 answers a 7/7 blocking persona panel on revision 1. "What revision 1 got wrong" is at the
end; if you reviewed r1, start there.

Owner selections recorded 2026-07-13 (#50 acceptance criteria 1–2):
- **First string anchor: cello** (bowed).
- **Horn family: trombone, trumpet, saxophone** — "horn" widened past brass to include the single-reed
  saxophone. **Trombone first.**
- **Sequencing:** fold the minimum gesture set into this campaign rather than blocking on all of #12.

This doc authorizes **no implementation** — not a broad orchestra, not additional GM families, not a
product-budget increase, and not any port. Each phase needs its own issue; any port needs
`skills/port-audit` first.

## Motivation

1. The owner wants to expand into strings and horns (#50).
2. #50 warned against silently collapsing "strings" to one instrument or assuming one brass. Both
   choices are now explicit.
3. #50's body asserted the repo "already has reusable … breath/control … building blocks." **It does
   not**, and the plan must not be built on that. Verified against `crates/dsp/` (this branch now
   contains it): there is no breath, bow, reed, or lip code anywhere, and no continuous-control path of
   any kind.

## Thesis

**The engine cannot make a bowed or blown sound, and the missing piece is not the bow or the reed — it
is the sustained gesture that drives them.**

The entire note-scoped WASM ABI is `ij_note_on(track, midi, vel)` and `ij_note_off(track, midi)`.
**Nothing about a sounding note can change.** That is sufficient for every instrument the engine has,
because a struck or plucked instrument is *fully determined at the moment of excitation* — after the
hammer leaves the string, the note is just a decay.

A bowed or blown instrument is the opposite. Its excitation is **continuous and coextensive with the
note**. Take that away and there is no instrument left — you have a filtered oscillator with an
envelope. **That is a pad.** And it is literally what ships: in the GM map `strings → 8` and
`brass → 8`, and instrument 8 is the subtractive synth pad. That was never laziness — it is what the
ABI permits.

So the bet is not "add a violin model." It is: **build the continuously-excited nonlinear waveguide
once, and make the four instruments variations on it.**

**How far that unification actually goes — stated honestly, because r1 overstated it.** McIntyre,
Schumacher & Woodhouse (1983) do unify the bowed string, the reed, and the flute jet under one
skeleton: *a linear resonator described by a reflection function, driven by a nonlinear excitation.*
The skeleton is real, and it is the shared core. But the **resonator** differs in every instrument, and
in three of four cases it breaks the MSW frame:

- the **bow** acts at an *interior* point of the string (two-sided scattering); the reed and lip act at
  a *termination* (one-sided). Different junction topology.
- MSW's reed is explicitly **quasi-static and memoryless**, so it cannot be the source for a *resonant*
  lip valve. That lineage is Fletcher's valve classification and Elliott & Bowsher, not MSW.
- MSW presumes a **linear resonator** — which the brass centrepiece here (nonlinear wave steepening in
  the bore) directly violates. Steepening is a *distributed bore nonlinearity* and cannot be lumped into
  a reflection function.
- the **saxophone** needs a spherical-wave conical guide, not a cylindrical one.

So the **junction-in-a-loop skeleton is genuinely shared; the resonator is not.** Leverage is real but
partial, and "trumpet is largely a reparameterization of trombone" is the one place it fully holds.
r1 priced in leverage the physics only partly delivers.

## Evidence base

**Verified in-repo, on this branch (which now contains the source it cites):**
- The note-scoped ABI is `ij_note_on` / `ij_note_off` only; `ij_pedal` is track-wide. No per-note
  continuous control, and **no note identity** — notes are addressed by `(track, midi)`, which is already
  ambiguous when the same key is struck twice while ringing.
- `strings`, `brass`, `voice`, `synth` all map to instrument 8 (`SynthPad`) in the GM group map.
- No bow, breath, reed, or lip code in `crates/dsp/`.
- `StringLoop` is a **single-delay-loop Karplus-Strong waveguide**, and it **cannot host a bow**: a
  friction junction needs the string velocity arriving at the bow point **from both directions** in order
  to scatter, which requires a two-rail bidirectional waveguide. **The existing string primitive is not
  reusable for the cello.** This is the largest honest cost in the plan.
- The engine is **AoS and scalar** — `Vec<Voice>`, enum-dispatched; no SIMD anywhere. Every budget below
  is a **scalar** budget. (r1 justified its budgets as "SIMD-friendly across the SoA voice bank." There is
  no SoA voice bank.)
- Measured voice costs @48 kHz (budget 2666.7 µs): synth pad 0.40 µs/voice, guitar 3.70, bass 3.89,
  e-piano 1.96, piano 13.22. Idle engine 19.9 µs.
- **`wdf.rs` already runs a warm-started damped Newton solve on the audio thread** (`HARD_ITERS = 2`,
  capped at 8), with oversampling as the sanctioned mitigation. **Bounded iteration is precedented here** —
  which matters a great deal below.

**Licensing:**
- **VSCO-2-CE** (`github.com/sgossner/VSCO-2-CE`), **CC0-1.0, already verified in
  `agentic-docs/licensing.md`.** The ledger cites it only for crash and upright-piano references and marks
  it scratchpad-only. r1 asserted it contains solo cello, trombone, trumpet and saxophone. **That is not
  verified** — neither the instruments' presence nor their articulation coverage. P0 must verify it before
  any model claim. The lesson from the piano P1 round applies directly: *the "staged" Salamander corpus
  was once a 404 HTML page.* **Verify references are actual audio at staging time, not at fit time.**
- **STK** (`thestk/stk`), MIT, already ✅ port-approved in the ledger, ships `Bowed`, `Brass`,
  `Saxofony`, `Clarinet`, `BandedWaveguide` — Cook & Scavone's canonical implementations. **A gift and a
  trap:** these models are pedagogical and will produce a recognizable-but-toy cello fast enough to tempt
  us into stopping. `skills/port-audit` and its legacy-flaws checklist are **mandatory before a line is
  copied.** The gate is owner listening, not "it sounds like a cello."

Literature: MSW (1983) for the skeleton; **Schelleng** for the bow force/velocity regime diagram;
Friedlander and Schumacher on the multi-valued friction characteristic; Woodhouse on bow–bridge distance
and Helmholtz corner sharpening; **Fletcher**, and **Elliott & Bowsher**, on outward-striking lip valves;
Msallam/Vergez and Campbell on brass wave steepening; Benade on conical bores and tone-hole lattice
cutoff; Scavone on conical waveguides.

## Design

### Layer 0 — The gesture set (the usable slice of #12)

**A bowed string needs four continuous controls, not three.** r1's headline — *"three scalars, and they
map exactly onto MPE X/Y/Z, so MPE's three are precisely the physical minimum"* — was **only true because
it conflated bow force with bow velocity.** Those are independent axes: **velocity** sets amplitude,
**force** selects the Schelleng regime (sul tasto / normale / raucous) at a given bow–bridge distance.
The playable space is a **plane**, not a line. Collapse them and every note is one canned bow-arm — you
cannot play a slow heavy *p* or a fast light *f*.

Worse, r1 had **no bow direction at all.** Bow velocity is **signed**: a down-bow→up-bow change is a
zero-crossing *inside a sustained note*, not a new note, and it is the primary rhythmic articulation of a
string player. MPE Z (pressure) is unipolar, so **as r1 specified it the ABI structurally could not
express a bow change** — every long note was one infinite bow.

| dim | bowed string | brass / reed |
|---|---|---|
| `pitch` | vibrato, portamento | slide, lip bend |
| `position` | bow–bridge distance β | embouchure / lip tension |
| `force` | bow force (selects the Schelleng regime) | breath pressure |
| `drive` | **signed** bow velocity — direction *and* speed | *(unused — breath is unsigned)* |

Three suffice for brass and reed; **the bowed string needs the fourth.** MPE's X/Y/Z carry three, and an
extra CC carries `drive`. The honest statement: **MPE's three per-note dimensions are necessary but not
sufficient for a bowed string.** That does not weaken the case for implementing them — it means the
headline was wrong.

**Articulation is discrete, not continuous.** Tonguing (brass/reed) and bow re-attack are *events*, not
scalars. `note_on` carries an articulation enum — `{ attack, tongued, slurred, legato }` — and a sounding
note can be **re-articulated without being retriggered**.

**Legato / note continuation.** r1's ABI made every `note_on` a fresh voice with a fresh waveguide, so a
slur was a **re-attack** — while r1's own S2/S3 gates demanded legato transitions and brass slotting (a
slur between slots is precisely a continued note across a lip-tension change). **The doc named an
acceptance criterion its own ABI could not meet.** Fixed: `note_on` may carry `tie_from: note_id`
("continue this excitation and retune"), with an explicit monophonic-legato continuation rule.

**The ABI — and the mistake r1 made about it.** r1 specified `ij_note_on(...) -> u32 note_id`: a WASM
return value produced on the audio thread. **That cannot work.** The public API is fire-and-forget across
`postMessage`; notes are **scheduled in the future** (`timeSeconds`) and **batched**. At call time the
voice does not exist and has no id to return — and a `Promise<id>` would break both the three-line path
and every pre-scheduled note list from `packages/midi`. r1 chose the one shape the architecture forbids,
for the phase it itself called highest-blast-radius and put first.

**Ids are caller-minted on the main thread:**

```
ij_note_on   (track, note_id, midi, vel, articulation, tie_from, frame_offset)
ij_note_expr (track, note_id, dim, value, frame_offset)    // dim ∈ {pitch, position, force, drive}
ij_note_off  (track, note_id, release_vel, frame_offset)
```

- **Frame offsets on every event.** Without them "sample-accurate" is a lie — events land on quantum
  boundaries, i.e. **2.67 ms granularity on the sustain control of a self-oscillating instrument**. And a
  stepped bow force is not a gain zipper: it **kicks the junction's operating point discontinuously.**
  Expression is applied with a per-sample ramp, whose cost sits inside the per-voice budget.
- **`release_vel` is carried now.** r1's `note_off(id)` dropped it, guaranteeing a *second* ABI break —
  and #12 names release velocity as in-scope. It costs one `f32`.
- Per-note identity also fixes the existing latent `(track, midi)` ambiguity for repeated same-key strikes.

**Transport policy — r1's was a stuck-note hazard.** r1 said continuous-control events are
"dropped-newest under saturation." That is exactly backwards. For a continuous scalar only the *latest*
value matters, so the correct policy is **coalesce per (note_id, dim)**, overwriting the stale value.
Dropping the newest **freezes** bow force or breath pressure at a stale value — and on a
**self-oscillating** instrument that is a note **stuck at full sustain**. Worse, **note lifecycle events
must be undroppable**: a dropped `note_off` on a blown voice never decays. It rings forever.

**Voice stealing must change, and r1 asserted it wouldn't.** Existing stealing was designed for struck and
plucked voices, whose tails are low-amplitude and duck out. **A self-oscillating bowed or blown voice is
at full amplitude the instant it is stolen** — stealing it is a hard step to zero, i.e. a click. A full
arrangement will exceed 64 slots routinely. Continuously-excited voices get an explicit **release ramp**
on steal, with a click gate.

**Default gesture — without it, the eval corpus renders silence.** Neither r1 doc said what happens when a
producer drops a cello on a track and plays the keyboard with no CC lane drawn. **That is the majority
case**, and the engine's actual driver is a note-list / SMF scheduler. If `force`/`drive` default to 0, a
bowed or blown note is **silent**, and S2/S3's dynamics and articulation gates have nothing to render.
Every continuously-excited instrument therefore ships a **default velocity→gesture envelope** (attack /
sustain / release of the drive control, per-preset shape), and there is a standing gate: **it must sound
professional from bare MIDI notes.**

### Layer 1 — The MSW core (shared)

**`BiWaveguide`** — a two-rail bidirectional waveguide, frequency-dependent termination filters, and a
scattering port at an arbitrary interior point. This is what `StringLoop` is not.

Continuous pitch means a **modulated delay length**, and that is where bowed and brass models actually go
wrong: an allpass interpolator transients and detunes under modulation, while a Lagrange interpolator
lowpasses the loop as a function of the fraction. **Name the interpolator and gate its modulation
artifacts** — vibrato and the trombone slide are the entire point of the pitch dimension.

**`NonlinearJunction`** — the MSW valve, in three specializations:
- **Bow:** stick–slip friction. **This is a state machine, not a curve.** The Friedlander characteristic
  is *multi-valued* — the load-line intersection has up to three roots, and selecting one requires
  carrying stick/slip state. That is a branch, and it *is* the hysteresis we want.
- **Reed:** a pressure-controlled beating valve (reed spring + Bernoulli flow; the reed can close).
- **Lip:** an **outward-striking mass–spring–damper whose own resonance interacts with the bore modes** —
  this is *why* brass slots onto harmonics. It is a 2-DOF implicit system per sample. **It is not a curve
  and cannot be tabulated.**

**Solution method — r1 defended the wrong flank.** r1 ruled out Newton as "data-dependent and branchy" and
prescribed a 1-D lookup: *"constant-time, branch-free."* But **this repo already ships a bounded Newton
solve on the audio thread** (`wdf.rs`), so iteration is precedented, not forbidden. And r1 then
contradicted itself — insisting the lip "must be modeled as a resonance, not a curve" and then proposing
exactly a curve. A static valve table is precisely **STK's simplification** — the one r1 calls "toy-like."

The honest method, per junction:

| junction | method | table rank |
|---|---|---|
| bow | 2-D characteristic (relative velocity × force) + **stick/slip state bit** | 2-D + branch |
| reed | 2-D (pressure × embouchure) | 2-D |
| lip | **bounded warm-started Newton**, following `wdf.rs`'s pattern and cap | ODE — not tabulated |

Bounded work per sample is preserved. "Branch-free" is not, and was never required.

**Oversampling is not optional.** Both headline features are broadband nonlinearities **inside feedback
loops**, so aliased energy **recirculates and detunes the loop** rather than merely adding a noise floor:
the bow's Helmholtz corner is a near-discontinuity *by design*, and brass shock formation synthesizes
energy above Nyquist *by construction*. `wdf.rs` already states this repo's rule — *"a Newton-root
nonlinearity aliases at 48 kHz … oversampling is the sanctioned fallback."* **The word "aliasing" does not
appear anywhere in r1.** Budget **2× oversampling** on the junction and on the nonlinear bore section, and
gate on it.

### Layer 2 — Bores and bodies

- **Cello:** two-rail bowed string → bridge admittance → body. The body reuses the **shared modal-body /
  bridge-port primitive** from the piano campaign (`2026-07-13-higher-capacity-piano.md`, A2) with
  different modes. Genuine shared leverage — and a reason to sequence the piano's A2 first.
- **Trombone / trumpet:** bore waveguide + a **bell reflection function** (the bell is essentially a
  high-pass: low modes reflect and sustain the oscillation, highs radiate out), plus **nonlinear wave
  steepening** at *ff*. That steepening is the one thing physical modeling wins outright: the *blat* of a
  loud brass note is a propagation nonlinearity, and **no sample library can produce it as a continuous
  function of dynamic.** Trumpet is then largely a reparameterization of bore, bell and lip.
- **Saxophone:** a **conical** bore (spherical wave variables, not cylindrical — genuinely different DSP),
  a **tone-hole lattice** with its characteristic cutoff, and the reed at the mouthpiece. The
  truncated-cone **apex reflection is a first-order filter that is marginally stable in the lossless
  limit** — a known numerical landmine, and it gets an explicit stability gate.

### Layer 3 — Sections. The thing that actually fixes `strings → pad`

r1 deferred ensembles, which means **after the cello ships, `strings → 8` is still a synth pad** — because
in a track, "strings" is a *section*, not a solo lead line.

A section is not a new model: it is N voices of the same core with **per-voice jitter** (bow force, β,
bow-change timing, intonation, onset). Without that jitter, 8 identical deterministic cellos **phase-lock
into one large fake cello** with comb filtering.

This is cheap, and it is the difference between "we modeled a cello" and "a producer can use this." It is
**S4** — not "deferred until demanded."

## Phased plan

**Standing gates, every phase, dual-rate (44.1 / 48 kHz):** no aliasing above Nyquist at *ff*; mobile
(iPhone 8 / Safari 16.4 floor, Pixel 6a; p99 < 50% of budget, `droppedQuanta == 0`); allocation-free,
lock-free, denormal-safe; **sounds professional from bare MIDI notes** (the default gesture envelope).

**S0 — The gesture set.** Caller-minted note ids; four continuous per-note dims with frame offsets and
per-sample ramps; articulation + `tie_from` legato; release velocity; **coalescing** transport with
undroppable note lifecycle; release-ramp voice stealing; MPE + CC (breath CC2, CC74) input in
`packages/midi`; a playground control surface. **Ships no new instrument and is independently valuable.**

This is the **highest-blast-radius phase and it is first** — and it is also the **cheapest possible moment
to break the ABI**: all three packages are `version: 0.0.0` and unpublished.

*Gate:* the **public TS surface is specified and the three-line path still works** — `noteOn(60)` /
`noteOff(60)` must survive as an overload, or PRINCIPLES #3 ("a web dev plays a note in three lines") is
being retired, and **that would be an owner decision, not an implementation detail.** Type-level compat
test; the README's three-line example compiles and runs; **`demos/bundler-matrix` still zero-config**
(Vite / Next / Webpack); **SSR-safe** — `navigator.requestMIDIAccess` is a textbook import-time SSR
landmine, and SSR-safe imports are a contract that must never break. A sounding note's force modulates
sample-accurately; zero allocation on the event path; **existing instruments render byte-identically**
(drift-check across the 80 standardized auditions); full-arrangement `dsp-bench` unchanged; **an explicit
core-JS + worklet gz ceiling** — r1 budgeted WASM only, and this phase grows the *JS* half of the contract
against a 4.7 KB module.

⚠️ The audio drift-check **cannot** detect a broken public signature, a broken `exports` map, or a types
regression — it compares audio bytes. r1 named it as S0's mitigation. The API/DX gates above are not
optional extras.

**S1 — `BiWaveguide` + MSW junctions.** Port-audit STK first; build the core; 2× oversampling.
*Gate:* self-oscillation **starts and stops with the force control**; Helmholtz motion visible in the
string waveform; bounded work per sample (bounded Newton permitted, unbounded not); **the delay
interpolator is named and its modulation artifacts measured** under vibrato and a full slide; each
junction's table rank and size declared. **#46 (bundle contract) is a precondition** — this is the first
WASM-touching phase.

**S2 — Cello.** Bowed string + shared modal body + bridge admittance.
*Gate:* the VSCO-2-CE corpus **verified and staged by checksum** (#52) — *including that the instrument is
actually present*, which is currently unverified; isolated articulations **including bow change**
(down↔up reversal — the seam that gives away every fake bowed line, and the moment a stick-slip junction is
most likely to drop out of oscillation) and a **slow-bow *pp* onset** (which must be allowed to scratch,
not fade in); détaché, legato, dynamics ladder, vibrato; **at least one multi-track musical context**;
≤ 10 µs/voice; per-voice state ≤ 20 KB — **it must not become the new size-setting `Kernel` variant** (see
the piano doc's ×64 law); owner blind listening + panel.

**S3 — Trombone.** Lip valve (bounded Newton) + bore + bell reflection + slide + steepening.
*Gate:* as S2, plus — the bore must **slot** (lip tension selects the harmonic; demonstrated, not
asserted); ***ff* must brassen** (measurable spectral enrichment with dynamic, not merely level); and a
**breath-release / note-end** gate: a note that stops dead is as fake as one that never brassens.

**S4 — Sections.** Per-voice jitter over the S2/S3 cores; remap GM `strings` and `brass` off the synth pad.
*Gate:* a section does not comb-filter or phase-lock; **a GM MIDI file with a string part stops sounding
like a pad**; the arrangement still fits the budget.

**S5 — Trumpet** (reparameterization of S3). **S6 — Saxophone** (conical bore + tone-hole lattice + reed;
plus an **apex stability** gate and a register-break gate).

## Budgets

Requirements, not measurements. **Scalar engine — no SIMD exists.**

| Budget | Requirement |
|---|---|
| Per-voice CPU @48 kHz | **≤ 10 µs/voice, inclusive of 2× oversampling** — between guitar (3.70) and piano (13.22) |
| Arrangement | 8 cello + 4 trombone + 16 piano + bass + drums ≤ **50% of budget, on M1 *and* mid-tier Android** |
| Per-voice state | **≤ 20 KB** — must not become the size-setting `Kernel` variant (paid ×64 across the bank) |
| Shared state | junction tables synthesized at init, **≤ 64 KB total** — *and each junction's table rank must be declared*, because a 2-D bow table is not a 1-D one |
| WASM | **≤ +25 KB raw / ≤ +10 KB gz** for the whole family. r1 gave **no gz ceiling** for the single largest WASM addition proposed anywhere in the repo — and **gz is the only unit the public contract is written in** |
| core JS + worklet | **S0 carries an explicit gz ceiling.** r1 budgeted zero JS bytes for the phase that grows the JS half of the contract |
| Init | **≤ 20 ms on the floor device** (iPhone 8), inside the gesture-unlock path |
| Degradation | voice stealing **with a release ramp** for self-oscillating voices; expression **coalesces**, never drops; **note lifecycle undroppable**; drops reported, never silent |

**Bundle — the composed number.** All-in today is **74,119 B gz** against the 102,400 B contract →
**~26 KB gz of headroom for the project's entire remaining life**, now enforced by
`scripts/audit/bundle-size-audit.sh` (#46). Claimants: this campaign (≤ +10 KB gz), the piano (≤ +5), the
808 kit (~+2), and the deferred shared room stage that both docs want and neither budgets. **These do not
obviously all fit.** #46 is a **precondition of S1**, the way #52 is a precondition of the DSP phases.

## Risks

1. **S0 is a breaking public-API change and it is first.** Mitigated by the API/DX gates above — *not* by
   the audio drift-check, which cannot see an API break. Cheapest possible moment: nothing is published.
2. **The bowed string is the hardest sound in this plan.** The stick–slip junction is easy to make
   *oscillate* and hard to make *musical*. Budget owner listening early and often, not at the end.
   *(Cello is **not** on the familiarity ladder — that is piano, guitar, drums; r1 said otherwise. The
   cello-over-violin choice stands on its own merits: violin is far less forgiving of intonation and
   vibrato error, and a mediocre violin is instantly recognizable as fake.)*
3. **STK will tempt us to stop too early.** The port-audit legacy-flaws checklist exists for exactly this.
4. **Shared dependency on the piano campaign** (the modal-body / bridge-port primitive). If the piano's A2
   slips, S2 waits or duplicates. Prefer waiting.
5. **The MSW leverage is partial** (see Thesis). Do not budget as though four instruments share one core.

## What revision 1 got wrong

The panel blocked r1 **7/7**.

1. **"Three scalars = exactly MPE X/Y/Z = precisely the minimum" was only true because it conflated bow
   force with bow velocity.** Two independent axes; a bowed string needs four.
2. **No bow direction.** Bow velocity is signed, MPE Z is unipolar — the ABI structurally could not express
   a bow reversal, the single most important string articulation.
3. **No tonguing and no legato/continuation semantics** — while r1's own S2/S3 gates *demanded* legato and
   slotting. The doc named an acceptance criterion its own ABI could not meet.
4. **The note-id ABI could not work through the transport.** A WASM return value cannot cross
   `postMessage`, and notes are scheduled in the future and batched. Ids are now caller-minted.
5. **"Drop-newest" was a stuck-note hazard** — it freezes bow force at full sustain on a self-oscillating
   instrument, and a dropped `note_off` rings forever. Now: coalesce; lifecycle undroppable.
6. **"Sample-accurate" was unachievable** — no frame offsets, no interpolation contract. Both added.
7. **`note_off` dropped release velocity**, guaranteeing a second ABI break. Added; it costs one `f32`.
8. **No default gesture** — a plain MIDI note into a bowed model is **silent**, which would have made the
   eval corpus render nothing at all.
9. **"Voice stealing unchanged" was a category error** — a self-oscillating voice is stolen at full amplitude.
10. **The table-junction argument defended the wrong flank** (`wdf.rs` already ships bounded Newton) and
    **contradicted itself** (lip "must be a resonance", then proposed a curve).
11. **Zero aliasing story**, in a design whose two headline features are broadband nonlinearities inside
    feedback loops. 2× oversampling is now budgeted and gated.
12. **The MSW "same object" claim was overstated**, and it mis-attributed the resonant lip valve to MSW.
13. **Sections were deferred** — which would have left `strings → synth pad` *still true* after the cello shipped.
14. **VSCO-2-CE's contents were asserted, not verified.**
15. **Budgets assumed a SoA/SIMD voice bank that does not exist**, gave no gz ceiling, budgeted zero JS, and
    had no mobile, SSR, or bundler gate.
16. **Cello was placed "on the familiarity ladder's upper half."** The ladder is piano, guitar, drums.

## Deferred until demanded

Violin, viola, double bass. French horn. Clarinet, flute, oboe, bassoon (the reed and jet cores make these
cheap *later* — that is the point of Layer 1, but they are not authorized here). Pizzicato and col legno.
Mutes; sul ponticello / sul tasto. Breath-controller hardware.

**Full MPE beyond the per-note dimensions above** — and note what actually remains in #12 once S0 lands:
**zone / master-channel routing and bend-range negotiation.** That is an input-layer concern, not a missing
architecture. Saying so stops #12 reading as a hole in the engine.

The shared room / early-reflection stage — wanted by every family, owned by its own issue, and competing
for the same ~26 KB gz.
