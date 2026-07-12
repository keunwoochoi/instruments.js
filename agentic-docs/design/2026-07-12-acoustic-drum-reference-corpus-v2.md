# Acoustic drum reference corpus v2

Date: 2026-07-12
Status: draft — this document proposes a source-diverse kick/snare evidence program for issue #43. It does not authorize downloading or redistributing audio, changing DSP, accepting any kit, or making pop/rock/jazz quality claims before source receipts, trust audits, panel review, and human listening pass.

## Motivation

The owner correctly challenged the evidence behind the pop, rock, and jazz kits, especially kick and snare. Lessons carried forward:

1. Four isolated cases cannot identify six core targets. The audited matrix has one pop kick, one rock kick, one rock snare, and one held-out jazz brush/snare; it has no pop snare, jazz kick, real velocity ladder, or source-independent held-out kick/snare pair.
2. A genre label is not an acoustic specification. “Pop,” “rock,” and “jazz” must resolve to recorded construction, head/tuning/damping, beater or brush technique, microphone role, room contribution, and velocity behavior.
3. One microphone perspective cannot own both the physical voice and the produced record. Close/direct channels may fit excitation and shell/body behavior; overhead, mid, and room channels are separate radiation/listening evidence and cannot be silently folded into the same numeric target.
4. A single hit is not a drum. Real velocity layers and repeated hits must be evaluated as distributions; amplitude-scaled copies do not count as dynamics or round robins.
5. The 808 campaign is comparatively better specified because it records original-hardware provenance and invalid axes explicitly. Acoustic kits need at least that level of honesty, plus source diversity and real performer variation.

## Thesis

Build the acoustic-kit corpus around physical and recording axes first, then map those validated targets to product presets. Each pop, rock, and jazz kick/snare claim requires a tune source and an entirely source-independent held-out source, three real strike-energy regions, multiple repeated hits, and explicit close versus spatial microphone roles. Absolute velocity-to-loudness evidence is valid only within one unchanged recording chain; cross-source comparisons own timbre and envelope shape only unless gain calibration is documented.

The corpus remains scratchpad-only and content-addressed. Git stores source receipts, licenses, immutable digests, canonicalization operations, case manifests, invalid-axis declarations, and reports—not reference audio. DSP fitting cannot begin until the source-selection phase proves that every claimed axis is actually observable.

## Evidence base

### Current-state audit

- The exact acoustic matrix at commit [`e59291d`](https://github.com/keunwoochoi/instruments.js/blob/e59291d1f7450e7c5e0f0ac2e07995fd37e3f885/evals/cases/drums.json) contains only four cases: pop kick ff, rock kick mf, rock snare ff, and held-out jazz brush mf. The audit finding is tracked in [issue #43](https://github.com/keunwoochoi/instruments.js/issues/43).
- The exact reference contract at [`e59291d`](https://github.com/keunwoochoi/instruments.js/blob/e59291d1f7450e7c5e0f0ac2e07995fd37e3f885/evals/reference-manifest.json) identifies the existing `virtuosity-drums` material as CC0 and declares room bleed, but it does not make the four-case matrix source-diverse.
- The four declared pop/rock/jazz files are absent from the visible scratchpad, while implementation comments attribute rock material to CC-BY Muldjord/Naked sources that the generic manifest can incorrectly inherit as Virtuosity/CC0. Unregistered references currently receive an empty corpus contract rather than a license/invalid-axis failure. P0/P1 must close these trust holes before any acquisition or fit.
- A staged Virtuosity receipt already records real soft/mid/hard jazz-kick close hits plus matched mid and overhead perspectives, without level normalization. This is useful tune evidence but cannot be its own held-out source.

### Primary source candidates

- [Virtuosity Drums’ official product notes](https://versilian-studios.com/virtuosity-drums/) and [manual](https://versilian-studios.com/Distro/VirtuosityDrumsManual.pdf) document a CC0 contemporary-jazz kit, up to 36 natural dynamic layers for kick/snare/toms, independent kick/snare close microphones, overhead/mid/room/vintage positions, kick damping, snares on/off, bleed control, and diverse snare articulations. It has dense natural dynamics but no kick/snare round robins, so it is a jazz tune source rather than proof of all jazz drums.
- [DRSKit’s official DrumGizmo page](https://www.drumgizmo.org/wiki/doku.php?id=kits%3Adrskit) declares CC-BY-4.0, says the handcrafted kit is intended from jazz through rock, and documents 13 channels including front/back kick, top/bottom snare, overheads, and ambience. The official archive contains dozens of power-ranked kick/snare hits plus rim and whisker techniques. It is the source-independent jazz held-out candidate and a neutral pop challenge source, not two independent sources.
- [SM Drums’ official project page](https://smmdrums.wordpress.com/for-reaper/) documents dry, unnormalized WAVs with 127 kick velocity layers ×2 round robins and 127 snare layers ×4 round robins, including no-ring and studio-ring snare variants. However, the author page does not display an explicit legal grant; the SFZ catalog’s “Public Domain” label is not enough. SM Drums remains rights-blocked until a bundled license or written author confirmation is retained.
- [Naked Drums’ licensed SFZ repository](https://github.com/sfzinstruments/WilkinsonAudio.NakedDrums) and [catalog entry](https://sfzinstruments.github.io/drums/naked_drums/) declare CC-BY-4.0, a Yamaha Recording Custom 22-inch kick, two documented snares, multiple room/overhead/close channels, ten round robins, and up to five velocity layers. It is the pop tune candidate pending exact archive, processing, and mic-map receipt verification.
- [MuldjordKit’s official DrumGizmo page](https://drumgizmo.org/wiki/doku.php?id=kits%3Amuldjordkit) declares CC-BY-4.0, identifies a Tama Superstar metal/rock kit, and documents inside-kick D112/trigger, snare top/bottom, overhead, and ambience channels. It also declares a snare phase-inversion requirement and known low-layer defects; those caveats must become enforceable invalid-axis/source exclusions.
- [CrocellKit’s official DrumGizmo page](https://drumgizmo.org/wiki/doku.php?id=kits%3Acrocellkit) declares CC-BY-4.0, identifies the actual metal-band recording kit, and documents independent inside/outside kick, top/bottom snare, three overhead, and two ambience channels. The archive contains 51 left-kick hits, 49 right-kick hits, and 98 center-snare hits; left/right double-pedal articulations must remain distinct. It is the source-independent rock held-out candidate after an energy-distribution audit.
- [DrumGizmo’s official sampling workflow](https://drumgizmo.org/wiki/doku.php?id=getting_dgedit) instructs recording at least 30 hits per drum from very light to very hard with separate close, overhead, and room tracks. This supports distributional velocity/round-robin gates rather than one hand-picked hit per label.
- [Big Rusty Drums’ official page](https://shop.karoryfer.com/pages/free-big-rusty-drums) and [CC0 repository](https://github.com/sfzinstruments/karoryfer.big-rusty-drums) document more than 4,400 samples from a 24-inch kick and 14×8 snare using sticks, brushes, and mallets, with close/overhead capture, snare bottom, damping variants, center/edge/rimshot/sidestick hits, and brush stirs/flutters. It is a source-independent brush/articulation candidate, not the velocity-curve authority because exact velocity-bin coverage is not published.
- [Swirly Drums’ official page](https://shop.karoryfer.com/pages/free-swirly-drums) documents CC0 brush-only sampling, controllable snare stirs/flutters, center/edge hits, and a brushed kick among more than 4,700 samples. It is a brush-technique tune candidate, not automatically a jazz-kit target: the source itself says its drums are punk/metal instruments played gently with brushes.
- [Ben Burnes’ official brushed-drum page](https://ben-burnes.gumroad.com/l/bb_brushed) declares CC0 Yamaha Birch Custom Absolute snare recordings with two brush types. It remains an optional challenge candidate until its downloaded manifest proves real dynamic/repetition coverage and a complete license receipt.
- [ENST-Drums’ primary ISMIR paper](https://ismir2006.ismir.net/PAPERS/ISMIR0627_Paper.pdf) documents isolated hits and professional performances from three drummers and their own kits, with sticks, rods, mallets, brushes, close kick/snare channels, and stereo overheads. It is a high-value source-diversity candidate, but no staging is authorized until the dataset’s current audio-use terms are captured and approved.
- [RWC Musical Instrument Sound’s primary database page](https://staff.aist.go.jp/m.goto/RWC-MDB/rwc-mdb-i.html) documents professional performers, multiple manufacturers/styles, and three dynamics including individual drum-kit sounds. It remains unverified because access/use terms and acquisition authority are not cleared.
- The physical case model follows published snare-drum coupled-system work rather than treating a snare as one filtered noise burst ([Bilbao, JASA 2012](https://www.research.ed.ac.uk/en/publications/time-domain-simulation-and-sound-synthesis-for-the-snare-drum/)). Velocity is a physical axis because measured membrane spectra and modal behavior change with striking force ([Dahl, nonlinear drum-membrane study](https://www.research.ed.ac.uk/files/16389380/Nonlinear_Effects_in_Drum_Membranes.pdf)).
- Attack is trajectory evidence, not one duration scalar: controlled timbre-perception work found attack temporal centroid more explanatory than attack time alone ([Kazazis, Depalle, and McAdams, JASA 2021](https://www.mcgill.ca/mpcl/files/mpcl/kazazis_2021b_jasa.pdf)).

Anything not verified from a primary license/source page remains a candidate, not evidence. Commercial libraries, unclear “royalty free” packs, normalized previews, mixed song stems, and copyleft code or assets are excluded.

Rejected core candidates are recorded rather than forgotten: Aasimonster has documented inter-channel timing errors; IDMT-SMT-Drums is CC-BY-NC-ND with insufficient acoustic mic provenance; Salamander has only two velocity levels plus normalized/defective files; AVL provides buses rather than preserved direct/overhead/room stems. They may not silently re-enter as calibration truth.

## Design

### 1. Source receipt and license boundary

Every accepted source gets a scratchpad receipt containing source URL, retrieval date, immutable upstream version or archive checksum, exact license text and checksum, credited authors/performers, original sample rate/bit depth, kit construction, heads/tuning/damping when known, strike implement or brush technique, microphone/channel map, disclosed processing, and every selected source-file SHA-256. Unknown facts remain explicitly `unknown`; genre is never used to invent construction or tuning. `agentic-docs/licensing.md` links the receipt class but does not duplicate per-file facts.

A source fails closed when the audio license is ambiguous, attribution cannot be satisfied, lossy previews are the only available assets, processing or normalization destroys a claimed axis, channel roles cannot be reconstructed, or upstream version identity is missing. Reference-only use does not relax provenance.

### 2. Canonicalization without laundering the recording

Canonical files preserve the source’s natural amplitude relationships within one mic chain. Allowed operations are decode, channel-role-preserving extraction, resampling with recorded kernel/version, polarity correction only when the source requires it, onset alignment to a fixed lead, and zero-padding to a declared duration. Every operation and pre/post digest is sealed.

Close/direct, overhead or mid, and room/ambience channels remain separate cases. They are never averaged into a single “canonical drum.” Cross-source timbre comparisons may use a separately prepared level-matched listening copy, but that copy never replaces the raw-amplitude canonical evidence. Absolute LUFS and velocity-loudness axes are invalid across different sessions unless upstream gain calibration is documented.

### 3. Distributional case model

The independent unit is `source_group_id = corpus + recording session + performer + physical kit + microphone setup`. Every hit, velocity, and channel from one source group remains on one side of the split. Each core source/voice/mic role uses three strike-energy regions—soft, medium, hard—selected from recorded hit-energy metadata or measured source RMS/peak ordering, never inferred from filenames alone. Each region retains at least five repeated hits when the source contains them, and an accepted deeply sampled source must expose at least 30 total varying hits per voice in line with DrumGizmo’s own capture guidance. The case report owns median and robust spread for attack, spectrum, band envelope, and loudness; tuning against one favorable round robin is forbidden.

Tune and held-out separation is by source group, not merely by hit, mic, or velocity. A fit may inspect every tune-source velocity and repeated-hit distribution. The held-out source remains sealed until the candidate and hypothesis are frozen. A third `threshold_calibration` role may establish repeat-vs-repeat metric floors once, but it can never tune DSP. Leave-one-source-family-out rotations are preregistered and all reported; favorable folds cannot be selected after the fact. Within-source extra repetitions and spatial microphones are diagnostics, not substitutes for source-independent holdout.

### 4. Product target matrix

| Preset | Tune source | Source-independent holdout | Core physical target |
|---|---|---|---|
| Pop | Naked Drums | DRSKit neutral stick hits | dry/direct studio kick and snare, controlled low-band decay, clear but non-metallic attack, natural velocity curve; SM Drums may replace or augment only after rights clearance |
| Rock | MuldjordKit | CrocellKit | harder beater/inside-kick attack, stronger high-mid snare crack and wire band, larger sustained shell/room energy without one narrow modal ring |
| Jazz | Virtuosity Drums | DRSKit | less click-dominated kick, audible mid/overhead radiation, longer but diffuse decay, stick snare with controlled wire texture and source-credible room |
| Jazz brush technique | Swirly Drums | Big Rusty Drums; DRS whisker hits as a second challenge | brush center/edge hit plus stir/flutter temporal texture; no release claim until source-independent dynamic/repetition coverage is verified |

These are hypotheses to test, not permission to force every source toward a stereotype. A preset passes only when tune and held-out sources agree on the direction of improvement and owner listening prefers it in representative phrases.

### 5. Metrics and trust gates

Kick and snare profiles retain the loop’s general MR-STFT, multiscale log-mel, loudness, and artifact gates, but add owned drum diagnostics:

- attack energy trajectories in 0–5, 5–20, and 20–50 ms windows by low, low-mid, high-mid, and high bands;
- onset crest, spectral flux, and centroid trajectories rather than one scalar attack centroid;
- band-wise decay slopes and time-varying spectral centroid, with room/bleed invalidity applied by source/mic role;
- pitch salience, peak Q, and harmonic concentration to reject the owner’s “vibraphone-like” narrow tonal kick failure even when total decay matches;
- snare shell-to-wire/noise energy, high-band wire decay, and noise-to-tonal balance;
- within-source velocity-to-loudness and velocity-to-timbre trajectories, plus monotonicity and saturation behavior;
- repeated-hit median, interquartile range, and worst-decile artifact checks so the model matches a distribution rather than one sample.

Signal trust also requires lossless native audio, deterministic transformations, no clipping or unexplained pre-onset transient, declared polarity/sample offset for multichannel groups, and duplicate-audio fingerprint rejection across source groups. Metric thresholds are calibrated on same-source repeat-vs-repeat and cross-source same-voice baselines before they gate DSP. A metric that cannot rank those known relationships predictably remains diagnostic-only. A candidate’s named hypothesis axis must improve by at least 0.5 pooled robust standard deviations on tune and keep the same direction in at least two source groups; every required held-out axis must have an upper 95% bootstrap regression bound no worse than +0.25 robust standard deviations. Removing any one tune source must retain the improvement sign or the result is labeled `source_specific`. No aggregate score may hide a red attack, tonality, velocity, or held-out gate.

### 6. Listening evidence

Isolated full-playback A/B uses the L4 public/private bundle and preregisters whether loudness matching is appropriate for the question. Phrase campaigns add source-independent pop, rock, and jazz grooves with kick/snare interplay, repeated hits, ghost notes, fills, cymbal masking, and the shared reverb stage. Those phrases are listening stimuli, not aligned single-hit metric targets.

Owner blind listening is required per preset. Trained-ear sessions must disclose mic perspective and must not compare a close render against an untreated room reference as though they were the same target. Physical iOS and live-playability gates remain independent.

## Phased plan

### P0 — source receipts and rejection ledger

One PR records the seven compact-corpus source receipts, optional candidate receipts, immutable archive/license hashes, exact selected file inventory, mic maps, processing/normalization facts, and explicit rejected sources. Gate: two accepted independent sources per pop/rock/jazz kick and snare, with no audio committed and every claimed axis traceable. SM Drums, ENST, RWC, or any paid/restricted source remains excluded until its own authority and rights gate is lifted.

### P1 — corpus schema and trust auditor

One PR extends the declarative case contract with source ID, voice, preset hypothesis, strike technique, energy region, repetition set, mic role, channel processing, and valid/invalid axes. The auditor rejects missing source independence, fake velocity ladders, mixed mic roles, absent repetitions, and cross-source absolute-loudness claims. Gate: adversarial fixtures fail for every rule and existing loop audits remain green.

### P2 — pop canonical campaign

One PR stages Naked Drums tune and DRSKit neutral held-out kick/snare distributions, produces deterministic canonical receipts, calibrates repeat-distribution floors, and replaces provisional pop cases. Gate: three real energy regions × both voices × both sources, at least five repeats per region where available, complete provenance, and no DSP change. If the panel finds DRS insufficiently independent from the jazz holdout role, P2 remains blocked until another accepted pop source replaces it.

### P3 — rock canonical campaign

One PR stages MuldjordKit tune and CrocellKit holdout while enforcing snare polarity, excluding disclosed defective hits, and separating inside/outside/overhead/room roles. Gate: the same distribution/provenance requirements plus explicit phase and trigger-channel policy; no DSP change.

### P4 — jazz and brush canonical campaign

One PR stages Virtuosity tune and DRSKit holdout for stick kick/snare, retains close/mid/overhead/room diagnostics, and stages Swirly tune plus Big Rusty/DRS brush challenges. Gate: source-independent stick coverage passes; brush remains provisional unless its independent held-out dynamic/repetition contract passes.

### P5 — metric calibration and provisional-baseline report

One PR calibrates drum diagnostics against repeat-vs-repeat and cross-source baselines, publishes uncertainty and failure examples, then reruns current pop/rock/jazz renders without tuning. Gate: metrics separate known same-source variation from meaningful source/model defects and the report explicitly identifies every existing claim that remains untrusted.

### P6 — DSP campaigns, one voice/preset hypothesis per PR

Only after P0–P5 pass, open separate kick/snare modeling PRs with one physical hypothesis, tune/held-out evidence, full arrangement `dsp-bench`, cross-family drift, exact-head panel, and owner blind listening. Jazz kick #39 is re-evaluated rather than grandfathered; no prior parameter fit survives solely because it improved the old four-case matrix.

## Deferred until demanded

- Toms, hats, rides, crashes, and percussion beyond phrase-level drift guards.
- Shipping any reference audio or sampler runtime in the product.
- Emulating commercial production chains, sample replacement, gated reverb, or mastered-record loudness.
- A genre classifier or a claim that one acoustic kit defines all pop, rock, or jazz.
- Learned embeddings until weights, license, offline execution, and drum-domain validity pass separate review.
- Brush release if a second independent, license-clean source cannot prove adequate dynamics and repetition.
