//! instruments.js DSP core.
//!
//! Constraints (AGENTS.md constitution #4, architecture doc 2026-07-11):
//! - Allocation-free after `Engine::new` — the audio thread never touches the allocator.
//! - All recursive filter state passes through [`flush_denormal`] (WASM has no hardware FTZ).
//! - One engine renders and mixes ALL tracks/instruments; the budget is 2.67 ms per
//!   128-frame quantum at 48 kHz for a full multi-track arrangement.
//! - Sample rate is per-instance, never global, never assumed 48 kHz (iOS locks to 44.1 kHz).
//! - Per-voice SIMD lane batching is deferred (tracked in the architecture doc); the SoA
//!   refactor happens when dsp-bench shows we need it.

#![deny(unsafe_code)]

pub mod kernels;

use kernels::{start_voice, Instrument, Kernel, Voice, MAX_BLOCK};

pub const MAX_VOICES: usize = 64;
pub const MAX_TRACKS: usize = 16;
pub const QUANTUM_FRAMES: usize = 128;

/// Flush denormals to zero. Denormals in recursive feedback loops are the top WASM perf
/// killer (Letz/Orlarey 2018); every state variable update must pass through this.
#[inline(always)]
pub fn flush_denormal(x: f32) -> f32 {
    if x.abs() < 1.0e-20 {
        0.0
    } else {
        x
    }
}

#[derive(Clone, Copy)]
pub struct TrackBus {
    pub instrument: Instrument,
    pub gain: f32,
    pub pan: f32, // -1.0 .. 1.0
    /// sustain pedal (CC64): note-offs are deferred while down
    pub pedal: bool,
    // smoothed equal-power gains (one-pole per block, no zipper noise)
    gl: f32,
    gr: f32,
}

impl TrackBus {
    fn targets(&self) -> (f32, f32) {
        let th = (self.pan.clamp(-1.0, 1.0) + 1.0) * core::f32::consts::FRAC_PI_4;
        (self.gain * th.cos(), self.gain * th.sin())
    }
}

pub struct Engine {
    pub sample_rate: f32,
    voices: Vec<Voice>,
    tracks: [TrackBus; MAX_TRACKS],
    track_buf: [f32; MAX_BLOCK],
    pub out_l: [f32; MAX_BLOCK],
    pub out_r: [f32; MAX_BLOCK],
    seed: u32,
}

impl Engine {
    /// All allocation happens here, once.
    pub fn new(sample_rate: f32) -> Self {
        let mut voices = Vec::with_capacity(MAX_VOICES);
        voices.resize(MAX_VOICES, Voice::off());
        Self {
            sample_rate,
            voices,
            tracks: [TrackBus {
                instrument: Instrument::Marimba,
                gain: 0.8,
                pan: 0.0,
                pedal: false,
                gl: 0.0,
                gr: 0.0,
            }; MAX_TRACKS],
            track_buf: [0.0; MAX_BLOCK],
            out_l: [0.0; MAX_BLOCK],
            out_r: [0.0; MAX_BLOCK],
            seed: 0x1234_5678,
        }
    }

    pub fn set_track(&mut self, track: usize, instrument: Instrument, gain: f32, pan: f32) {
        if track < MAX_TRACKS {
            let t = &mut self.tracks[track];
            t.instrument = instrument;
            t.gain = gain.clamp(0.0, 2.0);
            t.pan = pan.clamp(-1.0, 1.0);
        }
    }

    pub fn note_on(&mut self, track: usize, midi: u32, vel: f32) {
        if track >= MAX_TRACKS {
            return;
        }
        let inst = self.tracks[track].instrument;
        self.seed = self.seed.wrapping_mul(747796405).wrapping_add(2891336453);
        // voice choice: retrigger same (track,pitch) > free slot > oldest (steal)
        let mut slot = None;
        for (i, v) in self.voices.iter().enumerate() {
            if v.active() && v.track as usize == track && v.midi as u32 == midi && !v.releasing {
                slot = Some(i);
                break;
            }
        }
        if slot.is_none() {
            slot = self.voices.iter().position(|v| !v.active());
        }
        // steal preference: an already-releasing (quiet, fading) voice before a
        // still-ringing one — cutting a live tail is the audible failure mode
        let slot = slot.unwrap_or_else(|| {
            self.voices
                .iter()
                .enumerate()
                .max_by_key(|(_, v)| (v.releasing, v.age))
                .map(|(i, _)| i)
                .unwrap_or(0)
        });
        self.voices[slot] = Voice {
            kernel: start_voice(inst, midi, vel, self.sample_rate, self.seed),
            track: track as u8,
            midi: midi as u8,
            releasing: false,
            pedal_held: false,
            age: 0,
        };
    }

    pub fn note_off(&mut self, track: usize, midi: u32) {
        let inst = if track < MAX_TRACKS { self.tracks[track].instrument } else { return };
        // one-shot percussion ignores note-off; sustained/damped families release
        let damps = matches!(
            inst,
            Instrument::Vibraphone
                | Instrument::EPiano
                | Instrument::Guitar
                | Instrument::Bass
                | Instrument::SynthPad
        );
        if !damps {
            return;
        }
        let pedal = self.tracks[track].pedal;
        let sr = self.sample_rate;
        for v in self.voices.iter_mut() {
            if v.active() && v.track as usize == track && v.midi as u32 == midi && !v.releasing {
                if pedal {
                    v.pedal_held = true; // defer the release until pedal-up
                } else {
                    v.releasing = true;
                    match &mut v.kernel {
                        Kernel::Modal(m) => m.damp(sr),
                        Kernel::Pluck(p) => p.damp(),
                        Kernel::Synth(s) => s.release(),
                        _ => {}
                    }
                }
            }
        }
    }

    /// Sustain pedal (CC64). Pedal-up releases every note whose note-off was deferred.
    pub fn set_pedal(&mut self, track: usize, on: bool) {
        if track >= MAX_TRACKS {
            return;
        }
        self.tracks[track].pedal = on;
        if on {
            return;
        }
        let sr = self.sample_rate;
        for v in self.voices.iter_mut() {
            if v.active() && v.track as usize == track && v.pedal_held && !v.releasing {
                v.pedal_held = false;
                v.releasing = true;
                match &mut v.kernel {
                    Kernel::Modal(m) => m.damp(sr),
                    Kernel::Pluck(p) => p.damp(),
                    Kernel::Synth(s) => s.release(),
                    _ => {}
                }
            }
        }
    }

    pub fn all_off(&mut self) {
        let sr = self.sample_rate;
        for v in self.voices.iter_mut() {
            if v.active() && !v.releasing {
                v.releasing = true;
                match &mut v.kernel {
                    Kernel::Modal(m) => m.damp(sr),
                    Kernel::Pluck(p) => p.damp(),
                    Kernel::Synth(s) => s.release(),
                    Kernel::Drum(_) => {} // short one-shots; let them ring out
                    Kernel::Off => {}
                }
            }
        }
    }

    pub fn active_voices(&self) -> usize {
        self.voices.iter().filter(|v| v.active()).count()
    }

    /// Render one quantum for the whole arrangement into `out_l`/`out_r`.
    pub fn process(&mut self, frames: usize) {
        let frames = frames.min(MAX_BLOCK);
        self.out_l[..frames].fill(0.0);
        self.out_r[..frames].fill(0.0);
        let sr = self.sample_rate;

        for t in 0..MAX_TRACKS {
            // render every voice on this track into the mono track bus
            let mut any = false;
            self.track_buf[..frames].fill(0.0);
            for v in self.voices.iter_mut() {
                if !v.active() || v.track as usize != t {
                    continue;
                }
                any = true;
                let alive = match &mut v.kernel {
                    Kernel::Modal(m) => m.render(&mut self.track_buf[..frames]),
                    Kernel::Pluck(p) => p.render(&mut self.track_buf[..frames]),
                    Kernel::Drum(d) => d.render(&mut self.track_buf[..frames], sr),
                    Kernel::Synth(s) => s.render(&mut self.track_buf[..frames]),
                    Kernel::Off => false,
                };
                v.age += frames as u64;
                if !alive {
                    v.kernel = Kernel::Off;
                }
            }
            let (tl, tr) = self.tracks[t].targets();
            let bus = &mut self.tracks[t];
            if !any && bus.gl.abs() < 1e-6 && bus.gr.abs() < 1e-6 {
                bus.gl = tl;
                bus.gr = tr;
                continue;
            }
            // ~1 ms gain smoothing against zipper noise
            let c = 1.0 - (-1.0 / (0.001 * sr)).exp();
            for i in 0..frames {
                bus.gl += c * (tl - bus.gl);
                bus.gr += c * (tr - bus.gr);
                let s = self.track_buf[i];
                self.out_l[i] += s * bus.gl;
                self.out_r[i] += s * bus.gr;
            }
            bus.gl = flush_denormal(bus.gl);
            bus.gr = flush_denormal(bus.gr);
        }

        // master safety: transparent below ~-12 dBFS, soft-limits above
        for i in 0..frames {
            self.out_l[i] = soft_clip(self.out_l[i]);
            self.out_r[i] = soft_clip(self.out_r[i]);
        }
    }
}

/// Master safety limiter: exactly linear below the knee, then a tanh that is
/// value- AND slope-continuous at the knee (no step, no grit), asymptote 1.0.
#[inline(always)]
fn soft_clip(x: f32) -> f32 {
    const KNEE: f32 = 0.6;
    const REST: f32 = 1.0 - KNEE;
    let a = x.abs();
    if a <= KNEE {
        x
    } else {
        let y = KNEE + REST * ((a - KNEE) / REST).tanh();
        y.copysign(x)
    }
}

// ---------------------------------------------------------------------------
// WASM ABI — hand-rolled minimal C ABI (no bindgen glue; see architecture doc).
// The only unsafe in the crate lives here, at the FFI boundary.
// ---------------------------------------------------------------------------
#[allow(unsafe_code)]
pub mod ffi {
    use super::*;

    fn engine<'a>(p: *mut Engine) -> Option<&'a mut Engine> {
        #[allow(unsafe_code)]
        unsafe {
            p.as_mut()
        }
    }

    #[no_mangle]
    pub extern "C" fn ij_engine_new(sample_rate: f32) -> *mut Engine {
        Box::into_raw(Box::new(Engine::new(sample_rate)))
    }

    #[no_mangle]
    pub extern "C" fn ij_engine_free(p: *mut Engine) {
        if !p.is_null() {
            #[allow(unsafe_code)]
            unsafe {
                drop(Box::from_raw(p));
            }
        }
    }

    #[no_mangle]
    pub extern "C" fn ij_set_track(p: *mut Engine, track: u32, inst: u32, gain: f32, pan: f32) {
        if let Some(e) = engine(p) {
            e.set_track(track as usize, Instrument::from_u32(inst), gain, pan);
        }
    }

    #[no_mangle]
    pub extern "C" fn ij_note_on(p: *mut Engine, track: u32, midi: u32, vel: f32) {
        if let Some(e) = engine(p) {
            e.note_on(track as usize, midi, vel);
        }
    }

    #[no_mangle]
    pub extern "C" fn ij_note_off(p: *mut Engine, track: u32, midi: u32) {
        if let Some(e) = engine(p) {
            e.note_off(track as usize, midi);
        }
    }

    #[no_mangle]
    pub extern "C" fn ij_pedal(p: *mut Engine, track: u32, on: u32) {
        if let Some(e) = engine(p) {
            e.set_pedal(track as usize, on != 0);
        }
    }

    #[no_mangle]
    pub extern "C" fn ij_all_off(p: *mut Engine) {
        if let Some(e) = engine(p) {
            e.all_off();
        }
    }

    #[no_mangle]
    pub extern "C" fn ij_process(p: *mut Engine, frames: u32) {
        if let Some(e) = engine(p) {
            e.process(frames as usize);
        }
    }

    #[no_mangle]
    pub extern "C" fn ij_out_l(p: *mut Engine) -> *const f32 {
        engine(p).map(|e| e.out_l.as_ptr()).unwrap_or(core::ptr::null())
    }

    #[no_mangle]
    pub extern "C" fn ij_out_r(p: *mut Engine) -> *const f32 {
        engine(p).map(|e| e.out_r.as_ptr()).unwrap_or(core::ptr::null())
    }

    #[no_mangle]
    pub extern "C" fn ij_active_voices(p: *mut Engine) -> u32 {
        engine(p).map(|e| e.active_voices() as u32).unwrap_or(0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn render_seconds(e: &mut Engine, secs: f32) -> Vec<f32> {
        let total = (secs * e.sample_rate) as usize;
        let mut out = Vec::with_capacity(total);
        let mut done = 0;
        while done < total {
            let n = QUANTUM_FRAMES.min(total - done);
            e.process(n);
            out.extend_from_slice(&e.out_l[..n]);
            done += n;
        }
        out
    }

    fn zero_crossings(x: &[f32]) -> usize {
        x.windows(2).filter(|w| (w[0] >= 0.0) != (w[1] >= 0.0)).count()
    }

    #[test]
    fn denormals_are_flushed() {
        assert_eq!(flush_denormal(1.0e-30), 0.0);
        assert_eq!(flush_denormal(-1.0e-30), 0.0);
        assert_eq!(flush_denormal(0.5), 0.5);
    }

    #[test]
    fn silence_without_notes() {
        let mut e = Engine::new(48_000.0);
        let out = render_seconds(&mut e, 0.05);
        assert!(out.iter().all(|&s| s == 0.0));
    }

    #[test]
    fn note_produces_finite_bounded_audio() {
        let mut e = Engine::new(48_000.0);
        e.set_track(0, Instrument::Marimba, 0.8, 0.0);
        e.note_on(0, 69, 1.0);
        let out = render_seconds(&mut e, 0.5);
        let peak = out.iter().fold(0.0f32, |a, &s| a.max(s.abs()));
        assert!(out.iter().all(|s| s.is_finite()), "NaN/inf in output");
        assert!(peak > 0.01, "inaudibly quiet: peak={peak}");
        assert!(peak <= 1.0, "clipping escape: peak={peak}");
    }

    #[test]
    fn vibraphone_a4_is_in_tune_at_both_sample_rates() {
        for sr in [44_100.0f32, 48_000.0f32] {
            let mut e = Engine::new(sr);
            e.set_track(0, Instrument::Vibraphone, 0.8, 0.0);
            e.note_on(0, 69, 0.9); // A4 = 440 Hz
            let out = render_seconds(&mut e, 0.6);
            // after the attack, the fast-decaying upper partials are gone
            let tail = &out[(0.2 * sr) as usize..(0.5 * sr) as usize];
            let f_est = zero_crossings(tail) as f32 / 2.0 / 0.3;
            assert!(
                (f_est - 440.0).abs() < 440.0 * 0.03,
                "sr={sr}: estimated {f_est} Hz, want 440"
            );
        }
    }

    #[test]
    fn guitar_a3_is_in_tune_at_both_sample_rates() {
        // Pluck tuning is SR-dependent (delay length + fractional allpass) and iOS
        // locks contexts to 44.1 kHz — both rates must be verified.
        for sr in [44_100.0f32, 48_000.0f32] {
            let mut e = Engine::new(sr);
            e.set_track(0, Instrument::Guitar, 0.8, 0.0);
            e.note_on(0, 57, 0.8); // A3 = 220 Hz
            let out = render_seconds(&mut e, 0.6);
            let tail = &out[(0.25 * sr) as usize..(0.55 * sr) as usize];
            let f_est = zero_crossings(tail) as f32 / 2.0 / 0.3;
            assert!((f_est - 220.0).abs() < 220.0 * 0.02, "sr={sr}: estimated {f_est} Hz, want 220");
        }
    }

    #[test]
    fn pluck_tuning_is_velocity_independent() {
        // The loop-lowpass phase delay depends on velocity→brightness; without
        // compensation the string detunes with velocity (Juhan panel finding).
        let mut ests = Vec::new();
        for vel in [0.3f32, 0.9f32] {
            let mut e = Engine::new(48_000.0);
            e.set_track(0, Instrument::Guitar, 0.8, 0.0);
            e.note_on(0, 69, vel); // A4 = 440 Hz — short period exposes the error
            let out = render_seconds(&mut e, 0.6);
            let tail = &out[(0.25 * 48_000.0) as usize..(0.55 * 48_000.0) as usize];
            let f_est = zero_crossings(tail) as f32 / 2.0 / 0.3;
            assert!(
                (f_est - 440.0).abs() < 440.0 * 0.02,
                "vel={vel}: estimated {f_est} Hz, want 440"
            );
            ests.push(f_est);
        }
        let spread = (ests[0] - ests[1]).abs() / 440.0;
        assert!(spread < 0.01, "tuning drifts {:.2}% between velocities", spread * 100.0);
    }

    #[test]
    fn note_off_damps_guitar() {
        let mut e = Engine::new(48_000.0);
        e.set_track(0, Instrument::Guitar, 0.8, 0.0);
        e.note_on(0, 57, 0.9);
        let _ = render_seconds(&mut e, 0.2);
        e.note_off(0, 57);
        let out = render_seconds(&mut e, 0.4);
        let late = &out[(0.3 * 48_000.0) as usize..];
        let peak = late.iter().fold(0.0f32, |a, &s| a.max(s.abs()));
        assert!(peak < 0.01, "string still ringing after damp: {peak}");
    }

    #[test]
    fn sustain_pedal_defers_release_until_pedal_up() {
        let mut e = Engine::new(48_000.0);
        e.set_track(0, Instrument::Guitar, 0.8, 0.0);
        e.set_pedal(0, true);
        e.note_on(0, 57, 0.9);
        let _ = render_seconds(&mut e, 0.1);
        e.note_off(0, 57); // pedal is down — must keep ringing
        let held = render_seconds(&mut e, 0.4);
        let held_peak = held[(0.3 * 48_000.0) as usize..]
            .iter()
            .fold(0.0f32, |a, &s| a.max(s.abs()));
        assert!(held_peak > 0.005, "pedal failed to hold the note: {held_peak}");
        e.set_pedal(0, false); // pedal-up releases the deferred note-off
        let out = render_seconds(&mut e, 0.4);
        let late = &out[(0.3 * 48_000.0) as usize..];
        let peak = late.iter().fold(0.0f32, |a, &s| a.max(s.abs()));
        assert!(peak < 0.01, "string still ringing after pedal-up: {peak}");
    }

    #[test]
    fn synth_pad_sustains_and_releases() {
        let mut e = Engine::new(48_000.0);
        e.set_track(0, Instrument::SynthPad, 0.8, 0.0);
        e.note_on(0, 60, 0.8);
        let held = render_seconds(&mut e, 1.0);
        let sustain = &held[(0.8 * 48_000.0) as usize..];
        let sus_peak = sustain.iter().fold(0.0f32, |a, &s| a.max(s.abs()));
        assert!(sus_peak > 0.005, "pad died while held: {sus_peak}");
        e.note_off(0, 60);
        let out = render_seconds(&mut e, 3.5);
        let late = &out[(3.3 * 48_000.0) as usize..];
        let peak = late.iter().fold(0.0f32, |a, &s| a.max(s.abs()));
        assert!(peak < 1e-3, "pad still sounding 3.3 s after release: {peak}");
        assert_eq!(e.active_voices(), 0, "released pad voice not reclaimed");
    }

    #[test]
    fn voice_stealing_never_exceeds_pool() {
        let mut e = Engine::new(48_000.0);
        e.set_track(0, Instrument::Marimba, 0.8, 0.0);
        for i in 0..(MAX_VOICES as u32 + 40) {
            e.note_on(0, 40 + (i % 60), 0.7);
        }
        assert!(e.active_voices() <= MAX_VOICES);
        let out = render_seconds(&mut e, 0.1);
        assert!(out.iter().all(|s| s.is_finite()));
    }

    #[test]
    fn multitrack_arrangement_renders() {
        let mut e = Engine::new(48_000.0);
        e.set_track(0, Instrument::Marimba, 0.7, -0.3);
        e.set_track(1, Instrument::Bass, 0.8, 0.0);
        e.set_track(2, Instrument::Drums, 0.8, 0.2);
        e.set_track(3, Instrument::EPiano, 0.6, 0.3);
        e.note_on(0, 72, 0.8);
        e.note_on(1, 36, 0.9);
        e.note_on(2, 36, 1.0);
        e.note_on(2, 42, 0.6);
        e.note_on(3, 60, 0.7);
        e.note_on(3, 64, 0.7);
        e.note_on(3, 67, 0.7);
        let out = render_seconds(&mut e, 0.3);
        let peak = out.iter().fold(0.0f32, |a, &s| a.max(s.abs()));
        assert!(out.iter().all(|s| s.is_finite()));
        assert!(peak > 0.05 && peak <= 1.0, "arrangement peak={peak}");
    }
}
