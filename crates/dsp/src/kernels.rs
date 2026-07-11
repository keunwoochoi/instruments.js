//! Instrument kernels. All state is fixed-size and allocated inside the voice pool at
//! engine init; `render` never allocates. Every recursive state variable passes through
//! `flush_denormal` once per block.
//!
//! Synthesis references (papers/manuals only — see agentic-docs/licensing.md):
//! - Extended Karplus-Strong: Jaffe & Smith 1983; Smith, *Physical Audio Signal Processing*.
//! - Modal bar synthesis: Adrien 1991; tuned-bar partial ratios from standard acoustics
//!   literature (Rossing, *Science of Percussion Instruments*: marimba ~1:4:10,
//!   free bar 1:2.76:5.40:8.93).
//! - Two-pole resonator form: y[n] = 2r·cos(ω)·y[n-1] − r²·y[n-2] + g·x[n].

use crate::flush_denormal;

pub const MAX_BLOCK: usize = 128;
pub const MAX_MODES: usize = 8;
/// 2048 samples ≥ one period of 23.4 Hz at 48 kHz — covers 5-string bass low B (30.9 Hz).
pub const PLUCK_BUF: usize = 2048;

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Instrument {
    Marimba = 0,
    Vibraphone = 1,
    Glockenspiel = 2,
    MusicBox = 3,
    Guitar = 4,
    Bass = 5,
    EPiano = 6,
    Drums = 7,
    /// Classic subtractive pad (PRINCIPLES #5: no paradigm purity — fast + beautiful wins).
    SynthPad = 8,
}

impl Instrument {
    pub fn from_u32(v: u32) -> Self {
        match v {
            1 => Self::Vibraphone,
            2 => Self::Glockenspiel,
            3 => Self::MusicBox,
            4 => Self::Guitar,
            5 => Self::Bass,
            6 => Self::EPiano,
            7 => Self::Drums,
            8 => Self::SynthPad,
            _ => Self::Marimba,
        }
    }
}

#[inline(always)]
pub fn midi_to_hz(midi: f32) -> f32 {
    440.0 * ((midi - 69.0) / 12.0).exp2()
}

/// Deterministic per-voice noise (no host RNG in the core — reproducible renders).
#[derive(Clone, Copy)]
pub struct Lcg(pub u32);
impl Lcg {
    #[inline(always)]
    fn next(&mut self) -> f32 {
        self.0 = self.0.wrapping_mul(1664525).wrapping_add(1013904223);
        // top 23 bits → [-1, 1)
        (self.0 >> 9) as f32 * (2.0 / 8388608.0) - 1.0
    }
}

/// t60 seconds → per-sample amplitude ratio.
#[inline(always)]
fn t60_gain(t60: f32, sr: f32) -> f32 {
    if t60 <= 0.0 {
        0.0
    } else {
        (-6.907755 / (t60 * sr)).exp() // ln(10^-3)
    }
}

// ---------------------------------------------------------------------------
// Modal bank (mallets, bells, e-piano partials, drum modes)
// ---------------------------------------------------------------------------

#[derive(Clone, Copy)]
pub struct ModalVoice {
    n_modes: usize,
    a1: [f32; MAX_MODES],
    r2: [f32; MAX_MODES],
    y1: [f32; MAX_MODES],
    y2: [f32; MAX_MODES],
    g: [f32; MAX_MODES],
    /// raised-cosine strike pulse
    pulse_len: u32,
    pulse_pos: u32,
    pulse_amp: f32,
    click_amp: f32,
    click_decay: f32,
    click_env: f32,
    /// pickup nonlinearity drive (0 = linear) — e-piano
    drive: f32,
    rng: Lcg,
    life: u64,
    age: u64,
}

pub struct ModeDef {
    pub ratio: f32,
    pub amp: f32,
    pub t60: f32,
}

impl ModalVoice {
    #[allow(clippy::too_many_arguments)]
    pub fn start(
        f0: f32,
        vel: f32,
        sr: f32,
        modes: &[ModeDef],
        strike_ms: f32,
        click: f32,
        drive: f32,
        seed: u32,
    ) -> Self {
        let mut v = Self {
            n_modes: 0,
            a1: [0.0; MAX_MODES],
            r2: [0.0; MAX_MODES],
            y1: [0.0; MAX_MODES],
            y2: [0.0; MAX_MODES],
            g: [0.0; MAX_MODES],
            pulse_len: 1,
            pulse_pos: 0,
            pulse_amp: 0.0,
            click_amp: click * vel,
            click_decay: t60_gain(0.006, sr),
            click_env: 1.0,
            drive,
            rng: Lcg(seed | 1),
            life: 0,
            age: 0,
        };
        // Harder hits → shorter contact → brighter. Soft hits roll the top modes off.
        let contact_ms = strike_ms * (1.6 - vel).max(0.35);
        v.pulse_len = ((contact_ms * 1e-3 * sr) as u32).max(2);
        v.pulse_amp = vel;
        let nyq = 0.45 * sr;
        let mut max_t60 = 0.0f32;
        for m in modes.iter() {
            if v.n_modes == MAX_MODES {
                break;
            }
            let f = f0 * m.ratio;
            if f >= nyq {
                continue; // never synthesize above Nyquist — aliasing guard
            }
            // Higher partials decay faster on real bars; also fade them for soft hits.
            let t60 = m.t60 / (1.0 + 0.7 * (m.ratio - 1.0) * 0.3);
            let r = t60_gain(t60, sr);
            let w = core::f32::consts::TAU * f / sr;
            let i = v.n_modes;
            v.a1[i] = 2.0 * r * w.cos();
            v.r2[i] = r * r;
            // (1−r) normalizes resonator gain across decay times; vel^brightness on uppers.
            let bright = vel.powf(0.7 + 0.8 * (m.ratio - 1.0).min(4.0) * 0.25);
            v.g[i] = m.amp * (1.0 - r) * 2.5 * bright;
            v.n_modes += 1;
            max_t60 = max_t60.max(t60);
        }
        v.life = ((max_t60 * 1.2 + 0.05) * sr) as u64;
        v
    }

    /// Render one block, ADD into `out`. Returns false when the voice is spent.
    pub fn render(&mut self, out: &mut [f32]) -> bool {
        let inv_len = 1.0 / self.pulse_len as f32;
        for o in out.iter_mut() {
            // excitation: raised-cosine contact pulse + mallet click noise
            let mut x = 0.0;
            if self.pulse_pos < self.pulse_len {
                let ph = self.pulse_pos as f32 * inv_len;
                x = self.pulse_amp * 0.5 * (1.0 - (core::f32::consts::TAU * ph).cos());
                self.pulse_pos += 1;
            }
            if self.click_amp > 1e-5 {
                x += self.click_amp * self.click_env * self.rng.next();
                self.click_env *= self.click_decay;
            }
            let mut s = 0.0;
            for m in 0..self.n_modes {
                let y = self.a1[m] * self.y1[m] - self.r2[m] * self.y2[m] + self.g[m] * x;
                self.y2[m] = self.y1[m];
                self.y1[m] = y;
                s += y;
            }
            if self.drive > 0.0 {
                let d = 1.0 + self.drive;
                s = (d * s).tanh() / d.tanh().max(1e-6) * 0.8;
            }
            *o += s;
        }
        for m in 0..self.n_modes {
            self.y1[m] = flush_denormal(self.y1[m]);
            self.y2[m] = flush_denormal(self.y2[m]);
        }
        self.age += out.len() as u64;
        self.age < self.life
    }

    pub fn damp(&mut self, sr: f32) {
        // pull every mode's decay down to ~90 ms (mallet grab / pedal up)
        for m in 0..self.n_modes {
            let r_new = t60_gain(0.09, sr);
            let r_old2 = self.r2[m].max(1e-12);
            let scale = (r_new * r_new) / r_old2;
            self.r2[m] *= scale;
            self.a1[m] *= scale.sqrt();
        }
        self.life = self.age + (0.12 * sr) as u64;
    }
}

// ---------------------------------------------------------------------------
// Extended Karplus-Strong plucked string
// ---------------------------------------------------------------------------

#[derive(Clone, Copy)]
pub struct PluckVoice {
    buf: [f32; PLUCK_BUF],
    len: usize,
    pos: usize,
    /// loop one-pole lowpass state + coefficient (brightness)
    lp: f32,
    lp_c: f32,
    /// per-sample loop loss
    loss: f32,
    /// fractional-delay allpass
    ap_c: f32,
    ap_x1: f32,
    ap_y1: f32,
    level: f32,
    life: u64,
    age: u64,
    sr: f32,
}

impl PluckVoice {
    pub fn start(f0: f32, vel: f32, sr: f32, t60: f32, bright: f32, pick_pos: f32, seed: u32) -> Self {
        // total loop delay = len + allpass frac + ~0.5 (loop LP phase delay near f0)
        let period = sr / f0;
        let ideal = period - 0.5;
        let len = (ideal.floor() as usize).clamp(2, PLUCK_BUF - 1);
        let frac = ideal - len as f32;
        let ap_c = (1.0 - frac) / (1.0 + frac);
        let mut v = Self {
            buf: [0.0; PLUCK_BUF],
            len,
            pos: 0,
            lp: 0.0,
            lp_c: (bright * (0.35 + 0.6 * vel)).clamp(0.05, 0.995),
            loss: t60_gain(t60, sr),
            ap_c,
            ap_x1: 0.0,
            ap_y1: 0.0,
            level: 0.5 * (0.35 + 0.65 * vel),
            life: ((t60 * 1.5) * sr) as u64,
            age: 0,
            sr,
        };
        // Excitation pre-loaded into the delay line: velocity-lowpassed noise,
        // comb-filtered at the pick position (Jaffe-Smith), DC-removed.
        let mut rng = Lcg(seed | 1);
        let mut lp = 0.0f32;
        let exc_c = 0.25 + 0.72 * vel; // soft pluck = duller excitation
        let mut tmp = [0.0f32; PLUCK_BUF];
        for t in tmp.iter_mut().take(len) {
            lp += exc_c * (rng.next() - lp);
            *t = lp;
        }
        let p = ((pick_pos * len as f32) as usize).clamp(1, len - 1);
        let mut mean = 0.0;
        for i in 0..len {
            let comb = tmp[i] - 0.9 * tmp[(i + len - p) % len];
            v.buf[i] = comb;
            mean += comb;
        }
        mean /= len as f32;
        for b in v.buf.iter_mut().take(len) {
            *b -= mean;
        }
        v
    }

    pub fn render(&mut self, out: &mut [f32]) -> bool {
        for o in out.iter_mut() {
            let y = self.buf[self.pos];
            // loop lowpass (string damping / brightness)
            self.lp += self.lp_c * (y - self.lp);
            // fractional-delay allpass keeps the string in tune
            let ap = self.ap_c * (self.lp - self.ap_y1) + self.ap_x1;
            self.ap_x1 = self.lp;
            self.ap_y1 = ap;
            self.buf[self.pos] = ap * self.loss;
            self.pos = (self.pos + 1) % self.len;
            *o += y * self.level;
        }
        self.lp = flush_denormal(self.lp);
        self.ap_y1 = flush_denormal(self.ap_y1);
        self.age += out.len() as u64;
        self.age < self.life
    }

    pub fn damp(&mut self) {
        self.loss = t60_gain(0.07, self.sr);
        self.life = self.age + (0.1 * self.sr) as u64;
    }
}

// ---------------------------------------------------------------------------
// Subtractive synth pad — two polyBLEP saws → 2-pole lowpass → ADSR
// (classic-synth track per PRINCIPLES #5; polyBLEP keeps the top end alias-free,
//  which is the producer persona's #1 dismissal criterion)
// ---------------------------------------------------------------------------

/// polyBLEP residual: subtracts the aliased step at the saw wrap.
#[inline(always)]
fn poly_blep(t: f32, dt: f32) -> f32 {
    if t < dt {
        let x = t / dt;
        x + x - x * x - 1.0
    } else if t > 1.0 - dt {
        let x = (t - 1.0) / dt;
        x * x + x + x + 1.0
    } else {
        0.0
    }
}

#[derive(Clone, Copy)]
pub struct SynthVoice {
    phase: [f32; 2],
    dphase: [f32; 2],
    lp1: f32,
    lp2: f32,
    cutoff_hz: f32,
    // ADSR
    env: f32,
    stage: u8, // 0 attack, 1 decay, 2 sustain, 3 release
    attack_c: f32,
    decay_c: f32,
    sustain: f32,
    release_c: f32,
    level: f32,
    sr: f32,
    age: u64,
    life: u64,
}

impl SynthVoice {
    pub fn start(f0: f32, vel: f32, sr: f32) -> Self {
        let detune = 1.004; // ~7 cents apart
        Self {
            phase: [0.0, 0.37],
            dphase: [f0 / (sr * detune), f0 * detune / sr],
            lp1: 0.0,
            lp2: 0.0,
            cutoff_hz: (300.0 + 2800.0 * vel * vel + f0 * 1.5).min(0.4 * sr),
            env: 0.0,
            stage: 0,
            attack_c: 1.0 - (-1.0 / (0.12 * sr)).exp(),
            decay_c: 1.0 - (-1.0 / (0.45 * sr)).exp(),
            sustain: 0.72,
            release_c: 1.0 - (-1.0 / (0.35 * sr)).exp(),
            level: 0.16 * (0.4 + 0.6 * vel),
            sr,
            age: 0,
            life: (30.0 * sr) as u64, // safety cap; normally ends via release
        }
    }

    pub fn render(&mut self, out: &mut [f32]) -> bool {
        // block-rate filter coefficient (envelope moves slowly; no audible zipper)
        let fc = self.cutoff_hz * (0.35 + 0.65 * self.env);
        let c = 1.0 - (-core::f32::consts::TAU * fc / self.sr).exp();
        for o in out.iter_mut() {
            let mut s = 0.0;
            for v in 0..2 {
                let t = self.phase[v];
                s += (2.0 * t - 1.0) - poly_blep(t, self.dphase[v]);
                self.phase[v] += self.dphase[v];
                if self.phase[v] >= 1.0 {
                    self.phase[v] -= 1.0;
                }
            }
            // ADSR
            match self.stage {
                0 => {
                    self.env += self.attack_c * (1.02 - self.env);
                    if self.env >= 1.0 {
                        self.env = 1.0;
                        self.stage = 1;
                    }
                }
                1 => {
                    self.env += self.decay_c * (self.sustain - self.env);
                    if (self.env - self.sustain).abs() < 1e-3 {
                        self.stage = 2;
                    }
                }
                2 => {}
                _ => self.env += self.release_c * (0.0 - self.env),
            }
            self.lp1 += c * (s - self.lp1);
            self.lp2 += c * (self.lp1 - self.lp2);
            *o += self.lp2 * self.env * self.level;
        }
        self.lp1 = flush_denormal(self.lp1);
        self.lp2 = flush_denormal(self.lp2);
        self.env = flush_denormal(self.env);
        self.age += out.len() as u64;
        let dead = self.stage == 3 && self.env < 1e-4;
        !dead && self.age < self.life
    }

    pub fn release(&mut self) {
        self.stage = 3;
    }
}

// ---------------------------------------------------------------------------
// Drum kit (GM pitches) — sine-sweep kick, mode+noise snare, filtered-noise cymbals
// ---------------------------------------------------------------------------

#[derive(Clone, Copy)]
pub struct DrumVoice {
    kind: DrumKind,
    phase: f32,
    freq: f32,
    freq_end: f32,
    sweep: f32,
    amp: f32,
    env: f32,
    decay: f32,
    hp: f32,
    hp_c: f32,
    noise_amt: f32,
    tone_amt: f32,
    modal: ModalVoice,
    has_modal: bool,
    rng: Lcg,
    life: u64,
    age: u64,
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum DrumKind {
    Kick,
    Noise, // snare wires, hats, cymbals
}

impl DrumVoice {
    pub fn start(gm_note: u32, vel: f32, sr: f32, seed: u32) -> Self {
        let mut v = Self {
            kind: DrumKind::Noise,
            phase: 0.0,
            freq: 0.0,
            freq_end: 0.0,
            sweep: 0.0,
            amp: vel,
            env: 1.0,
            decay: t60_gain(0.2, sr),
            hp: 0.0,
            hp_c: 0.2,
            noise_amt: 1.0,
            tone_amt: 0.0,
            modal: ModalVoice::start(200.0, 0.0, sr, &[], 1.0, 0.0, 0.0, seed),
            has_modal: false,
            rng: Lcg(seed | 1),
            life: (0.6 * sr) as u64,
            age: 0,
        };
        match gm_note {
            35 | 36 => {
                // kick: 110→43 Hz sweep, soft knee
                v.kind = DrumKind::Kick;
                v.freq = 110.0;
                v.freq_end = 43.0;
                v.sweep = (-1.0 / (0.035 * sr)).exp();
                v.decay = t60_gain(0.42, sr);
                v.amp = vel * 0.9;
                v.life = (0.6 * sr) as u64;
            }
            38 | 40 => {
                // snare: two shell modes + bright wire noise
                v.decay = t60_gain(0.16, sr);
                v.hp_c = 0.35;
                v.noise_amt = 0.5 + 0.5 * vel;
                v.has_modal = true;
                v.modal = ModalVoice::start(
                    186.0,
                    vel,
                    sr,
                    &[
                        ModeDef { ratio: 1.0, amp: 0.9, t60: 0.11 },
                        ModeDef { ratio: 1.78, amp: 0.55, t60: 0.08 },
                    ],
                    0.4,
                    0.0,
                    0.0,
                    seed ^ 0x9e37,
                );
                v.life = (0.35 * sr) as u64;
            }
            42 | 44 => {
                // closed hat
                v.decay = t60_gain(0.055, sr);
                v.hp_c = 0.72;
                v.amp = vel * 0.55;
                v.life = (0.12 * sr) as u64;
            }
            46 => {
                // open hat
                v.decay = t60_gain(0.38, sr);
                v.hp_c = 0.7;
                v.amp = vel * 0.5;
                v.life = (0.7 * sr) as u64;
            }
            49 | 57 => {
                // crash
                v.decay = t60_gain(1.6, sr);
                v.hp_c = 0.5;
                v.amp = vel * 0.5;
                v.life = (2.2 * sr) as u64;
            }
            51 | 59 => {
                // ride: ping partial + wash
                v.decay = t60_gain(1.1, sr);
                v.hp_c = 0.55;
                v.amp = vel * 0.35;
                v.tone_amt = 0.5;
                v.freq = 640.0;
                v.freq_end = 640.0;
                v.sweep = 1.0;
                v.life = (1.6 * sr) as u64;
            }
            _ => {
                // tom-ish fallback: pitched mode by GM note
                v.has_modal = true;
                v.decay = t60_gain(0.25, sr);
                v.noise_amt = 0.25;
                let f = midi_to_hz(gm_note as f32) * 0.5;
                v.modal = ModalVoice::start(
                    f.clamp(60.0, 400.0),
                    vel,
                    sr,
                    &[
                        ModeDef { ratio: 1.0, amp: 1.0, t60: 0.3 },
                        ModeDef { ratio: 1.5, amp: 0.4, t60: 0.15 },
                    ],
                    0.8,
                    0.15,
                    0.0,
                    seed ^ 0x51ed,
                );
                v.life = (0.5 * sr) as u64;
            }
        }
        v
    }

    pub fn render(&mut self, out: &mut [f32], sr: f32) -> bool {
        let dt = 1.0 / sr;
        for o in out.iter_mut() {
            let mut s;
            match self.kind {
                DrumKind::Kick => {
                    self.freq = self.freq_end + (self.freq - self.freq_end) * self.sweep;
                    self.phase = (self.phase + self.freq * dt).fract();
                    s = (core::f32::consts::TAU * self.phase).sin() * self.env;
                    // contact click for the first ~4 ms
                    if self.age < (0.004 * sr) as u64 {
                        s += 0.3 * self.rng.next() * self.env;
                    }
                }
                DrumKind::Noise => {
                    let n = self.rng.next();
                    self.hp += self.hp_c * (n - self.hp); // lowpass...
                    let hp = n - self.hp; // ...subtracted = one-pole highpass
                    s = hp * self.env * self.noise_amt;
                    if self.tone_amt > 0.0 {
                        self.phase = (self.phase + self.freq * dt).fract();
                        s += self.tone_amt * (core::f32::consts::TAU * self.phase).sin() * self.env;
                    }
                }
            }
            self.env *= self.decay;
            *o += s * self.amp;
            self.age += 1;
        }
        self.hp = flush_denormal(self.hp);
        self.env = flush_denormal(self.env);
        if self.has_modal {
            self.modal.render(out);
        }
        self.age < self.life
    }
}

// ---------------------------------------------------------------------------
// Voice = one note on one track
// ---------------------------------------------------------------------------

#[derive(Clone, Copy)]
pub enum Kernel {
    Off,
    Modal(ModalVoice),
    Pluck(PluckVoice),
    Drum(DrumVoice),
    Synth(SynthVoice),
}

#[derive(Clone, Copy)]
pub struct Voice {
    pub kernel: Kernel,
    pub track: u8,
    pub midi: u8,
    pub releasing: bool,
    pub age: u64,
}

impl Voice {
    pub const fn off() -> Self {
        Self { kernel: Kernel::Off, track: 0, midi: 0, releasing: false, age: 0 }
    }
    pub fn active(&self) -> bool {
        !matches!(self.kernel, Kernel::Off)
    }
}

/// Per-instrument note-on: builds the right kernel with per-family preset numbers.
pub fn start_voice(inst: Instrument, midi: u32, vel: f32, sr: f32, seed: u32) -> Kernel {
    let f0 = midi_to_hz(midi as f32);
    let vel = vel.clamp(0.0, 1.0);
    match inst {
        Instrument::Marimba => {
            // rosewood bar, tuned 1:4:10 (Rossing); short bright contact
            let key = (midi as f32 - 45.0) / 40.0; // decay shortens up the keyboard
            let t = (1.4 - key).clamp(0.35, 1.6);
            Kernel::Modal(ModalVoice::start(
                f0,
                vel,
                sr,
                &[
                    ModeDef { ratio: 1.0, amp: 1.0, t60: t },
                    ModeDef { ratio: 3.98, amp: 0.42, t60: t * 0.30 },
                    ModeDef { ratio: 10.2, amp: 0.16, t60: t * 0.12 },
                    ModeDef { ratio: 17.9, amp: 0.05, t60: t * 0.07 },
                ],
                1.1,
                0.10,
                0.0,
                seed,
            ))
        }
        Instrument::Vibraphone => {
            let t = 6.0 - 3.0 * ((midi as f32 - 53.0) / 36.0).clamp(0.0, 1.0);
            Kernel::Modal(ModalVoice::start(
                f0,
                vel,
                sr,
                &[
                    ModeDef { ratio: 1.0, amp: 1.0, t60: t },
                    ModeDef { ratio: 4.0, amp: 0.28, t60: t * 0.22 },
                    ModeDef { ratio: 10.0, amp: 0.10, t60: t * 0.07 },
                ],
                1.6,
                0.05,
                0.0,
                seed,
            ))
        }
        Instrument::Glockenspiel => Kernel::Modal(ModalVoice::start(
            f0,
            vel,
            sr,
            // free-bar ratios (steel, no arch tuning)
            &[
                ModeDef { ratio: 1.0, amp: 1.0, t60: 2.6 },
                ModeDef { ratio: 2.756, amp: 0.35, t60: 1.4 },
                ModeDef { ratio: 5.404, amp: 0.18, t60: 0.7 },
                ModeDef { ratio: 8.933, amp: 0.06, t60: 0.35 },
            ],
            0.7,
            0.12,
            0.0,
            seed,
        )),
        Instrument::MusicBox => Kernel::Modal(ModalVoice::start(
            f0,
            vel,
            sr,
            // plucked steel comb tooth: slightly inharmonic shimmer
            &[
                ModeDef { ratio: 1.0, amp: 1.0, t60: 2.2 },
                ModeDef { ratio: 2.02, amp: 0.22, t60: 1.1 },
                ModeDef { ratio: 5.7, amp: 0.10, t60: 0.5 },
                ModeDef { ratio: 9.1, amp: 0.04, t60: 0.25 },
            ],
            0.5,
            0.16,
            0.0,
            seed,
        )),
        Instrument::Guitar => {
            let key = ((midi as f32) - 40.0) / 44.0;
            let t60 = (4.2 - 2.6 * key).clamp(0.8, 4.2);
            Kernel::Pluck(PluckVoice::start(f0, vel, sr, t60, 0.55, 0.28, seed))
        }
        Instrument::Bass => {
            let t60 = 5.0 - 2.0 * (((midi as f32) - 28.0) / 32.0).clamp(0.0, 1.0);
            Kernel::Pluck(PluckVoice::start(f0, vel, sr, t60, 0.38, 0.18, seed))
        }
        Instrument::EPiano => {
            // tine + tone-bar partial through a velocity-driven pickup nonlinearity
            let key = ((midi as f32) - 40.0) / 48.0;
            let t = (7.0 - 4.5 * key).clamp(1.2, 7.0);
            Kernel::Modal(ModalVoice::start(
                f0,
                vel,
                sr,
                &[
                    ModeDef { ratio: 1.0, amp: 1.0, t60: t },
                    ModeDef { ratio: 3.97, amp: 0.14 + 0.5 * vel * vel, t60: 0.5 },
                    ModeDef { ratio: 6.24, amp: 0.05 * vel, t60: 0.2 },
                ],
                2.2,
                0.03,
                0.6 + 2.4 * vel,
                seed,
            ))
        }
        Instrument::Drums => Kernel::Drum(DrumVoice::start(midi, vel, sr, seed)),
        Instrument::SynthPad => Kernel::Synth(SynthVoice::start(f0, vel, sr)),
    }
}
