/**
 * Demo arrangement: 8 bars, 100 BPM, Am–F–C–G ×2 — six tracks through one engine.
 * Plain JS module so the browser playground AND the Node verification harness share
 * the identical note list (deterministic renders).
 *
 * Humanization (panel finding, Hayoung lens): light swing on the 8ths, ±ms
 * micro-timing everywhere, composed melodic contours (not a random walk), and
 * per-bar dynamic shaping — all driven by a seeded PRNG so renders stay identical.
 */

const BPM = 100;
const BEAT = 60 / BPM;
const BAR = 4 * BEAT;
const SWING = 0.09; // fraction of a beat added to 8th-note offbeats

/** chord roots + voicings per bar (MIDI) */
const PROG = [
  { name: "Am", bass: 33, chord: [57, 60, 64], scale: [69, 72, 76, 79, 81] },
  { name: "F", bass: 29, chord: [53, 57, 60], scale: [69, 72, 77, 79, 81] },
  { name: "C", bass: 36, chord: [55, 60, 64], scale: [67, 72, 76, 79, 84] },
  { name: "G", bass: 31, chord: [55, 59, 62], scale: [67, 71, 74, 79, 83] },
];

/** Melody as scale-degree contours per bar: rise, answer, climb, resolve. -1 = rest. */
const MELODY = [
  [0, 1, 2, -1, 3, 2, 1, -1],
  [1, 2, 3, -1, 2, 1, 0, -1],
  [2, 3, 4, 3, 2, 3, 1, -1],
  [3, 2, 1, 2, 0, -1, 0, -1],
];
/** pass-2 variation: same shapes an octave-adjacent, denser end */
const MELODY2 = [
  [4, 3, 2, 3, 4, 3, 2, 1],
  [2, 3, 4, -1, 3, 2, 1, 0],
  [0, 1, 2, 3, 4, 3, 2, 3],
  [4, 3, 2, 1, 0, 1, 0, -1],
];

/** deterministic pseudo-random (mulberry32) so every render is identical */
function rng(seed) {
  let a = seed >>> 0;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export function demoSong() {
  const notes = [];
  const rand = rng(20260711);
  /** micro-timing: ±jitterMs, never before zero */
  const human = (t, jitterMs = 9) => Math.max(0, t + (rand() - 0.5) * 2 * jitterMs * 1e-3);
  const swung = (t, eighthIndex) => t + (eighthIndex % 2 === 1 ? SWING * BEAT : 0);
  const add = (group, midiPitch, start, dur, vel, isDrum = false) =>
    notes.push({
      instrumentGroup: group,
      midiPitch,
      startSeconds: +start.toFixed(4),
      endSeconds: +(start + dur).toFixed(4),
      velocity: Math.max(1, Math.min(127, Math.round(vel))),
      isDrum,
    });

  for (let pass = 0; pass < 2; pass++) {
    for (let b = 0; b < 4; b++) {
      const bar = (pass * 4 + b) * BAR;
      const { bass, chord, scale } = PROG[b];
      // dynamic arc across the form: build through each pass, pass 2 hotter
      const arc = 0.85 + 0.1 * (b / 3) + (pass === 1 ? 0.12 : 0);

      // Acoustic piano: rolled chord on the downbeat, quieter octave answer on beat 3
      chord.forEach((p, i) =>
        add("piano", p, human(bar + i * 0.018, 5), 2.6 * BEAT, (60 + i * 4 + rand() * 8) * arc));
      chord.slice(0, 2).forEach((p, i) =>
        add("piano", p + 12, human(bar + 2 * BEAT + i * 0.02, 6), 1.5 * BEAT, (44 + rand() * 10) * arc));

      // Bass: 1 · and-of-2 (swung) · 3 · approach on 4+
      add("bass", bass, human(bar, 4), 1.4 * BEAT, (92 + rand() * 8) * arc);
      add("bass", bass + 7, human(swung(bar + 1.5 * BEAT, 3), 6), 0.4 * BEAT, (68 + rand() * 8) * arc);
      add("bass", bass, human(bar + 2 * BEAT, 4), 1.2 * BEAT, (84 + rand() * 8) * arc);
      add("bass", bass + (b === 3 ? 2 : 12), human(swung(bar + 3.5 * BEAT, 7), 6), 0.45 * BEAT, (72 + rand() * 8) * arc);

      // Marimba: composed contour with phrase-shaped dynamics (peak mid-phrase)
      const line = (pass === 0 ? MELODY : MELODY2)[b];
      line.forEach((deg, s) => {
        if (deg < 0) return;
        const t = human(swung(bar + s * 0.5 * BEAT, s), 8);
        const phraseShape = 1 - Math.abs(s - 3.5) / 7; // rises to the middle, falls away
        const vel = (58 + 34 * phraseShape + (s % 4 === 0 ? 10 : 0) + rand() * 8) * arc;
        add("marimba", scale[deg], t, 0.45 * BEAT, vel);
      });

      // Glockenspiel: sparkle on pass 2 downbeats
      if (pass === 1) {
        add("glockenspiel", scale[4] + 12, human(bar + (b % 2) * 2 * BEAT, 10), 1.5 * BEAT, 54 + rand() * 8);
      }

      // Synth pad: whole-bar chord bed (classic-synth track — PRINCIPLES #5)
      chord.forEach((p, i) => add("strings", p + 12, human(bar + 0.04, 12), 3.9 * BEAT, (42 + i * 3) * arc));

      // Drums (GM): kick 1 & 3(+pickup bar 4), snare 2 & 4 (+ghost pass 2), swung hats
      add("percussion", 36, human(bar, 3), 0.2, 104 + rand() * 8, true);
      add("percussion", 36, human(bar + 2 * BEAT, 3), 0.2, 92 + rand() * 8, true);
      if (b === 3) add("percussion", 36, human(swung(bar + 3.5 * BEAT, 7), 4), 0.2, 82, true);
      add("percussion", 38, human(bar + 1 * BEAT, 3), 0.2, 96 + rand() * 10, true);
      add("percussion", 38, human(bar + 3 * BEAT, 3), 0.2, 100 + rand() * 10, true);
      if (pass === 1) add("percussion", 38, human(swung(bar + 2.5 * BEAT, 5), 5), 0.15, 26 + rand() * 8, true); // ghost
      for (let e = 0; e < 8; e++) {
        const open = e === 7 && b === 3;
        const t = human(swung(bar + e * 0.5 * BEAT, e), 4);
        add("percussion", open ? 46 : 42, t, 0.1, (open ? 76 : 48 + (e % 2) * 14 + rand() * 8) * arc, true);
      }
      if (pass === 1 && b === 0) add("percussion", 49, bar, 0.3, 108, true);
    }
  }
  return notes;
}

export const DEMO_SONG_SECONDS = 8 * BAR;
