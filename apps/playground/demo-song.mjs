/**
 * Demo arrangement: 8 bars, 100 BPM, Am–F–C–G ×2 — five tracks through one engine.
 * Plain JS module so the browser playground AND the Node verification harness share
 * the identical note list (deterministic renders).
 */

const BPM = 100;
const BEAT = 60 / BPM;
const BAR = 4 * BEAT;

/** chord roots + voicings per bar (MIDI) */
const PROG = [
  { name: "Am", bass: 33, chord: [57, 60, 64], scale: [69, 72, 76, 79, 81] },
  { name: "F", bass: 29, chord: [53, 57, 60], scale: [69, 72, 77, 79, 81] },
  { name: "C", bass: 36, chord: [55, 60, 64], scale: [67, 72, 76, 79, 84] },
  { name: "G", bass: 31, chord: [55, 59, 62], scale: [67, 71, 74, 79, 83] },
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
  const add = (group, midiPitch, start, dur, vel, isDrum = false) =>
    notes.push({
      instrumentGroup: group,
      midiPitch,
      startSeconds: +start.toFixed(4),
      endSeconds: +(start + dur).toFixed(4),
      velocity: Math.round(vel),
      isDrum,
    });

  for (let pass = 0; pass < 2; pass++) {
    for (let b = 0; b < 4; b++) {
      const bar = (pass * 4 + b) * BAR;
      const { bass, chord, scale } = PROG[b];

      // E-piano: rolled chord on the downbeat, answer on beat 3
      chord.forEach((p, i) => add("epiano", p, bar + i * 0.02, 2.6 * BEAT, 64 + i * 4));
      chord.slice(0, 2).forEach((p, i) => add("epiano", p + 12 * (i === 0 ? 0 : 0), bar + 2 * BEAT + i * 0.02, 1.6 * BEAT, 52));

      // Bass: 1 · and-of-2 · 3 · approach on 4+
      add("bass", bass, bar, 1.4 * BEAT, 96);
      add("bass", bass + 7, bar + 1.5 * BEAT, 0.4 * BEAT, 72);
      add("bass", bass, bar + 2 * BEAT, 1.2 * BEAT, 88);
      add("bass", bass + (b === 3 ? 2 : 12), bar + 3.5 * BEAT, 0.45 * BEAT, 76);

      // Marimba: melody — eighth-note phrases from the bar's scale, human velocities
      const phraseLen = pass === 0 ? 6 : 8;
      for (let s = 0; s < phraseLen; s++) {
        const t = bar + s * 0.5 * BEAT;
        const deg = Math.floor(rand() * scale.length);
        const vel = 62 + Math.floor(rand() * 40) + (s % 4 === 0 ? 14 : 0);
        add("marimba", scale[deg], t, 0.45 * BEAT, Math.min(120, vel));
      }

      // Glockenspiel: sparkle on pass 2 downbeats
      if (pass === 1) {
        add("glockenspiel", scale[4] + 12, bar + (b % 2) * 2 * BEAT, 1.5 * BEAT, 58);
      }

      // Synth pad: whole-bar chord bed (classic-synth track — PRINCIPLES #5)
      chord.forEach((p, i) => add("strings", p + 12, bar + 0.05, 3.9 * BEAT, 44 + i * 3));

      // Drums (GM): kick 1 & 3(+"and" pickup in bar 4), snare 2 & 4, hats 8ths
      add("percussion", 36, bar, 0.2, 108, true);
      add("percussion", 36, bar + 2 * BEAT, 0.2, 96, true);
      if (b === 3) add("percussion", 36, bar + 3.5 * BEAT, 0.2, 84, true);
      add("percussion", 38, bar + 1 * BEAT, 0.2, 100, true);
      add("percussion", 38, bar + 3 * BEAT, 0.2, 104, true);
      for (let e = 0; e < 8; e++) {
        const open = e === 7 && b === 3;
        add("percussion", open ? 46 : 42, bar + e * 0.5 * BEAT, 0.1, open ? 80 : 52 + (e % 2) * 16, true);
      }
      if (pass === 1 && b === 0) add("percussion", 49, bar, 0.3, 110, true);
    }
  }
  return notes;
}

export const DEMO_SONG_SECONDS = 8 * BAR;
