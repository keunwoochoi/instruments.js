/**
 * Beta demo set — original, license-clean arrangements that exercise the library
 * across genres, instrument combinations, and solo tunes (the beta's listening
 * surface; owner 2026-07-21). Each demo is a plain note list in the engine's
 * NoteEvent shape so the browser showcase and any Node render share it exactly.
 *
 * A demo: { id, name, genre, bpm, combo, seconds, mix, build() -> NoteEvent[] }.
 * NoteEvent: { instrumentGroup, midiPitch, startSeconds, endSeconds, velocity, isDrum? }.
 *
 * All music here is composed for this repo (no third-party MIDI, no licence to
 * clear). Voicings and lines are idiomatic but deliberately short — these are
 * auditions, not pieces.
 */
import { demoSong, DEMO_MIX, DEMO_SONG_SECONDS } from "./demo-song.mjs";

// ---- tiny music toolkit ----------------------------------------------------
const PC = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 };
/** note name -> MIDI, e.g. "F#4" -> 66, "Bb2" -> 46 (middle C = C4 = 60). */
export function n(name) {
  const m = /^([A-G])([#b]?)(-?\d)$/.exec(name);
  if (!m) throw new Error(`bad note ${name}`);
  const acc = m[2] === "#" ? 1 : m[2] === "b" ? -1 : 0;
  return PC[m[1]] + acc + (Number(m[3]) + 1) * 12;
}
function mulberry32(a) {
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
/** builder factory: returns { add, humanize, rand } bound to one note list. */
function pen(seed) {
  const notes = [];
  const rand = mulberry32(seed);
  const humanize = (t, ms = 8) => Math.max(0, t + (rand() - 0.5) * 2 * ms * 1e-3);
  const add = (group, midi, start, dur, vel, isDrum = false) => {
    notes.push({
      instrumentGroup: group,
      midiPitch: midi,
      startSeconds: +start.toFixed(4),
      endSeconds: +(start + Math.max(0.03, dur)).toFixed(4),
      velocity: Math.max(1, Math.min(127, Math.round(vel))),
      isDrum,
    });
  };
  return { notes, add, humanize, rand };
}

// ---- jazz combo: piano + upright bass + jazz kit + trumpet -----------------
// F major. 8-bar head, played twice: | Gm7 | C7 | Fmaj7 | Dm7 | Gm7 | C7 | Fmaj7 | (Gm7 C7) |
function buildJazz() {
  const BPM = 128, B = 60 / BPM, BAR = 4 * B;
  const { notes, add, humanize, rand } = pen(0x1a22);
  const sw = (t, e) => t + (e % 2 ? 0.11 * B : 0); // swing the offbeat 8ths
  // rootless LH/RH piano voicings (3rd & 7th + tensions), bass roots, chord tones for the walk
  const CH = [
    { root: n("G2"), voic: [n("F3"), n("A3"), n("Bb3"), n("D4")], tones: [n("G2"), n("Bb2"), n("D3"), n("F3")] }, // Gm7
    { root: n("C2"), voic: [n("E3"), n("Bb3"), n("D4")],          tones: [n("C2"), n("E2"), n("G2"), n("Bb2")] }, // C7
    { root: n("F2"), voic: [n("A3"), n("E4"), n("C4")],           tones: [n("F2"), n("A2"), n("C3"), n("E3")] }, // Fmaj7
    { root: n("D2"), voic: [n("F3"), n("C4"), n("A3")],           tones: [n("D2"), n("F2"), n("A2"), n("C3")] }, // Dm7
  ];
  const FORM = [0, 1, 2, 3, 0, 1, 2, 1]; // chord index per bar (bar 8 -> C7 turnaround w/ Gm7 half)
  // a singable trumpet head, scale degrees over F major per bar (-1 = rest)
  const HEAD = [
    [n("A4"), n("C5"), -1, n("D5"), n("C5"), n("A4"), -1, -1],
    [n("Bb4"), n("A4"), n("G4"), -1, n("E4"), -1, n("G4"), -1],
    [n("F4"), n("A4"), n("C5"), -1, -1, n("A4"), -1, -1],
    [n("D5"), n("C5"), n("A4"), n("F4"), n("G4"), -1, -1, -1],
  ];
  for (let pass = 0; pass < 2; pass++) {
    for (let b = 0; b < 8; b++) {
      const bar = (pass * 8 + b) * BAR;
      const ch = CH[FORM[b]];
      const arc = 0.9 + (pass ? 0.08 : 0);
      // walking bass: a quarter per beat, chord tones + a chromatic approach into the next bar
      const next = CH[FORM[(b + 1) % 8]].root;
      const walk = [ch.tones[0], ch.tones[1], ch.tones[2], next + (rand() < 0.5 ? 1 : -1)];
      for (let beat = 0; beat < 4; beat++)
        add("bass", walk[beat], humanize(bar + beat * B, 6), 0.92 * B, (86 + rand() * 10) * arc);
      // ride: spang-a-lang (1, 2, &2, 3, 4, &4), hi-hat foot on 2 and 4, jazz kit
      for (let beat = 0; beat < 4; beat++) {
        add("drums-jazz", 51, humanize(bar + beat * B, 5), 0.2, (58 + (beat % 2 ? 12 : 0) + rand() * 8) * arc, true);
        if (beat % 2) add("drums-jazz", 51, humanize(sw(bar + beat * B + 0.5 * B, 1), 5), 0.15, (46 + rand() * 8) * arc, true);
        if (beat === 1 || beat === 3) add("drums-jazz", 42, humanize(bar + beat * B, 4), 0.12, 40 + rand() * 8, true);
      }
      // feathered kick on 1 (the de-tonalized jazz kick — soft), light snare comps
      add("drums-jazz", 36, humanize(bar, 5), 0.15, 34 + rand() * 8, true);
      if (rand() < 0.4) add("drums-jazz", 38, humanize(sw(bar + 2.5 * B, 5), 6), 0.12, 30 + rand() * 8, true);
      // piano comping: rootless voicing stabs on the & of 1 and beat 3-ish, sparse
      const hit1 = sw(bar + 0.5 * B, 1);
      ch.voic.forEach((p, i) => add("piano", p, humanize(hit1 + i * 0.006, 6), 0.7 * B, (52 + rand() * 10) * arc));
      if (rand() < 0.7) ch.voic.forEach((p, i) => add("piano", p, humanize(bar + 2.5 * B + i * 0.006, 7), 0.6 * B, (44 + rand() * 10) * arc));
      // trumpet head (pass shapes dynamics; lays out on pass-2 bar 8 for a breath)
      if (!(pass === 1 && b === 7)) {
        HEAD[b % 4].forEach((p, s) => {
          if (p < 0) return;
          const t = humanize(sw(bar + s * 0.5 * B, s), 9);
          add("trumpet", p, t, 0.44 * B, (66 + (s === 0 ? 8 : 0) + rand() * 10) * arc);
        });
      }
    }
  }
  return notes;
}

// ---- classical: piano arpeggios + violin melody + cello ---------------------
// G major, gentle 4/4, ~68 bpm. 12 bars: I  IV  I  V  vi  IV  I  V  I ...
function buildClassical() {
  const BPM = 68, B = 60 / BPM, BAR = 4 * B;
  const { notes, add, humanize } = pen(0xc1a5);
  // (bass, arpeggio cells low->high, violin target)
  const P = [
    { bass: n("G2"), arp: [n("G3"), n("B3"), n("D4"), n("B3")], mel: n("D5") }, // G
    { bass: n("C3"), arp: [n("C3"), n("E3"), n("G3"), n("E3")], mel: n("E5") }, // C
    { bass: n("G2"), arp: [n("G3"), n("B3"), n("D4"), n("B3")], mel: n("B4") }, // G
    { bass: n("D3"), arp: [n("D3"), n("F#3"), n("A3"), n("F#3")], mel: n("A4") }, // D
    { bass: n("E2"), arp: [n("E3"), n("G3"), n("B3"), n("G3")], mel: n("G4") }, // Em
    { bass: n("C3"), arp: [n("C3"), n("E3"), n("G3"), n("E3")], mel: n("C5") }, // C
    { bass: n("G2"), arp: [n("G3"), n("B3"), n("D4"), n("B3")], mel: n("D5") }, // G
    { bass: n("D3"), arp: [n("D3"), n("A3"), n("D4"), n("A3")], mel: n("F#5") }, // D
  ];
  const FORM = [0, 1, 2, 3, 4, 5, 6, 7, 0, 1, 2, 6];
  // violin phrase: a rising then resolving line, one sustained note per two beats
  const VIOL = [n("D5"), n("E5"), n("D5"), n("B4"), n("A4"), n("B4"), n("D5"), n("A5"),
                n("G5"), n("E5"), n("D5"), n("G5")];
  for (let b = 0; b < FORM.length; b++) {
    const bar = b * BAR;
    const p = P[FORM[b]];
    const arc = 0.9 + 0.1 * Math.sin((b / FORM.length) * Math.PI); // gentle swell over the phrase
    // cello: sustained bass note, whole bar, with a mid-bar neighbor on cadence bars
    add("cello", p.bass, humanize(bar, 10), BAR * 0.98, (54 + 8) * arc);
    // piano: eight-note broken chord, two cells per bar
    for (let e = 0; e < 8; e++) {
      const cell = p.arp[e % 4] + (e >= 4 ? 0 : 0);
      add("piano", cell, humanize(bar + e * 0.5 * B, 6), 0.5 * B * 0.95, (40 + (e % 4 === 0 ? 10 : 0)) * arc);
    }
    // violin: the melody, one note held ~2 beats, entering from bar 1
    const mv = VIOL[b];
    add("violin", mv, humanize(bar + 0.02, 12), BAR * 0.55, (58 + 6) * arc);
    if (b % 2 === 1) add("violin", p.mel, humanize(bar + 2 * B, 10), BAR * 0.45, (54) * arc);
  }
  return notes;
}

// ---- piano solo: a wistful original in A minor, ~84 bpm --------------------
function buildPianoSolo() {
  const BPM = 84, B = 60 / BPM, BAR = 4 * B;
  const { notes, add, humanize } = pen(0x9142);
  // LH broken-chord pattern (bass, then chord tones), RH melody per bar
  const P = [
    { lh: [n("A2"), n("E3"), n("A3"), n("C4")], },  // Am
    { lh: [n("F2"), n("C3"), n("F3"), n("A3")], },  // F
    { lh: [n("C3"), n("G3"), n("C4"), n("E4")], },  // C
    { lh: [n("G2"), n("D3"), n("G3"), n("B3")], },  // G
    { lh: [n("D3"), n("A3"), n("D4"), n("F4")], },  // Dm
    { lh: [n("E2"), n("B2"), n("E3"), n("G3")], },  // Em
  ];
  const FORM = [0, 1, 2, 3, 0, 1, 4, 5, 0, 1, 2, 3];
  const MEL = [
    [n("E5"), -1, n("A5"), -1, n("G5"), -1, n("E5"), -1],
    [n("F5"), -1, n("A5"), n("G5"), n("F5"), -1, n("C5"), -1],
    [n("E5"), -1, n("G5"), -1, n("C6"), -1, n("B5"), -1],
    [n("D5"), n("E5"), n("G5"), -1, n("D5"), -1, -1, -1],
    [n("A5"), -1, n("C6"), n("B5"), n("A5"), n("G5"), n("E5"), -1],
    [n("F5"), -1, n("E5"), -1, n("D5"), -1, n("B4"), -1],
  ];
  for (let b = 0; b < FORM.length; b++) {
    const bar = b * BAR;
    const p = P[FORM[b]];
    const arc = 0.86 + 0.16 * Math.sin((b / FORM.length) * Math.PI);
    // LH: bass on 1, then a rising broken chord across the bar (eighths)
    p.lh.forEach((cell, i) => add("piano", cell, humanize(bar + i * B, 7), (i === 0 ? 1.9 : 0.9) * B, (46 + (i === 0 ? 10 : 0)) * arc));
    p.lh.slice(1).forEach((cell, i) => add("piano", cell, humanize(bar + (2 + i) * B, 7), 0.9 * B, (40) * arc));
    // RH melody: eighth grid, phrase-shaped dynamics
    MEL[b % MEL.length].forEach((mp, s) => {
      if (mp < 0) return;
      const shape = 1 - Math.abs(s - 3.5) / 6;
      add("piano", mp, humanize(bar + s * 0.5 * B, 6), 0.5 * B * 1.4, (54 + 22 * shape) * arc);
    });
  }
  return notes;
}

// ---- guitar solo: nylon fingerstyle in E minor, ~100 bpm -------------------
function buildGuitarSolo() {
  const BPM = 100, B = 60 / BPM, BAR = 4 * B;
  const { notes, add, humanize } = pen(0x6547);
  // (bass, chord voicing on the guitar, melody note for the top)
  const P = [
    { bass: n("E2"), ch: [n("B2"), n("E3"), n("G3")], top: n("B3") }, // Em
    { bass: n("C3"), ch: [n("G3"), n("C4"), n("E4")], top: n("G4") }, // C
    { bass: n("G2"), ch: [n("D3"), n("G3"), n("B3")], top: n("D4") }, // G
    { bass: n("D3"), ch: [n("A3"), n("D4"), n("F#4")], top: n("A4") }, // D
    { bass: n("A2"), ch: [n("E3"), n("A3"), n("C4")], top: n("E4") }, // Am
    { bass: n("B2"), ch: [n("F#3"), n("B3"), n("D4")], top: n("F#4") }, // Bm
  ];
  const FORM = [0, 1, 2, 3, 0, 1, 4, 5, 0, 1, 2, 3];
  for (let b = 0; b < FORM.length; b++) {
    const bar = b * BAR;
    const p = P[FORM[b]];
    const arc = 0.9 + 0.1 * Math.sin((b / FORM.length) * Math.PI);
    // Travis-ish fingerpick: bass on 1 and 3, chord tones on the offbeats, melody on top
    add("guitar", p.bass, humanize(bar, 6), 1.9 * B, (58) * arc);
    add("guitar", p.bass + 7, humanize(bar + 2 * B, 6), 1.9 * B, (50) * arc);
    const cells = [p.ch[0], p.ch[1], p.ch[2], p.ch[1]];
    for (let e = 0; e < 4; e++)
      add("guitar", cells[e], humanize(bar + (e + 0.5) * B, 7), 0.6 * B, (42 + (e % 2) * 6) * arc);
    // melody: top note on beat 1 and a passing note into the next bar
    add("guitar", p.top, humanize(bar + 0.5 * B, 8), 1.1 * B, (60) * arc);
    if (b % 2 === 1) add("guitar", p.top + 2, humanize(bar + 3.5 * B, 8), 0.5 * B, 52 * arc);
  }
  return notes;
}

// ---- registry --------------------------------------------------------------
export const DEMOS = [
  {
    id: "pop", name: "Neon Afternoon", genre: "Pop / band",
    combo: "piano · guitars · bass · mallets · drums", bpm: 100,
    seconds: DEMO_SONG_SECONDS, mix: DEMO_MIX, build: demoSong,
  },
  {
    id: "jazz", name: "Blue Note Diner", genre: "Jazz combo",
    combo: "trumpet · piano · upright bass · brushed jazz kit", bpm: 128,
    seconds: 2 * 8 * (4 * 60 / 128) + 2.5, build: buildJazz,
    mix: {
      trumpet: { gain: 0.66, pan: 0.12 }, piano: { gain: 0.52, pan: -0.2 },
      bass: { gain: 0.68, pan: 0.0 }, "drums-jazz": { gain: 0.52, pan: 0.1 },
    },
  },
  {
    id: "classical", name: "G-major Reverie", genre: "Classical",
    combo: "violin · cello · piano", bpm: 68,
    seconds: 12 * (4 * 60 / 68) + 3, build: buildClassical,
    mix: {
      violin: { gain: 0.5, pan: -0.1 }, cello: { gain: 0.44, pan: 0.15 },
      piano: { gain: 0.4, pan: 0.05 },
    },
  },
  {
    id: "piano-solo", name: "Amber, Alone", genre: "Solo piano",
    combo: "piano", bpm: 84,
    seconds: 12 * (4 * 60 / 84) + 3, build: buildPianoSolo,
    mix: { piano: { gain: 0.6, pan: 0.0 } },
  },
  {
    id: "guitar-solo", name: "Six Strings at Dusk", genre: "Solo guitar",
    combo: "nylon guitar", bpm: 100,
    seconds: 12 * (4 * 60 / 100) + 3, build: buildGuitarSolo,
    mix: { guitar: { gain: 0.92, pan: 0.0 } },
  },
];
