/**
 * Beta demo set — REAL music MIDI (owner 2026-07-21..22). The set is
 * MULTI-INSTRUMENT-forward: the owner wanted full arrangements that exercise the
 * whole library, not cute originals or solo piano ("find more multi-instrument
 * songs"). Two licence-clean families are used, both committable and shippable:
 *
 *   • CC0 1.0 originals (github.com/m-malandro/CC0-midis) — multitrack pieces
 *     with real General-MIDI instrument assignments, so packages/midi's
 *     gmProgramToGroup routes each part across our library automatically:
 *     drums, distorted/steel guitar, bass, piano, strings, brass, synth, mallets.
 *   • Public-Domain Bach organ works (Mutopia Project, PD sequence) — the
 *     chordal Toccata & Fugue and the Invention the owner liked, re-voiced onto
 *     the organ.
 *
 * A demo entry: { id, name, genre, combo, midi, instrument (null = keep the
 * MIDI's own per-part instruments), excerpt (seconds), mix }. The browser
 * fetches `midi`, the Node harness reads it; both call parseMidi()+processMidi().
 * Provenance + sha + licence in agentic-docs/licensing.md ("Demo music").
 */

export const DEMOS = [
  { id: "overture", name: "Overture 2021", genre: "Orchestral rock · full band",
    combo: "drums · strings · brass · guitar · piano · bass", midi: "./midi/cc0-overture-2021.mid",
    instrument: null, excerpt: 58,
    mix: {
      drums: { gain: 0.175, pan: 0 }, "guitar-distorted": { gain: 0.228, pan: -0.25 },
      bass: { gain: 0.385, pan: 0 }, piano: { gain: 0.333, pan: 0.15 },
      violin: { gain: 0.385, pan: -0.15 }, viola: { gain: 0.315, pan: 0.1 },
      trumpet: { gain: 0.35, pan: 0.2 }, trombone: { gain: 0.315, pan: -0.2 },
      woodwind: { gain: 0.28, pan: 0.25 },
    } },
  { id: "arena", name: "Arena Rock", genre: "Rock band",
    combo: "drums · distorted guitar · bass · piano · synth", midi: "./midi/cc0-arena-rock.mid",
    instrument: null, excerpt: 52,
    mix: {
      drums: { gain: 0.234, pan: 0 }, "guitar-distorted": { gain: 0.36, pan: -0.2 },
      bass: { gain: 0.54, pan: 0 }, piano: { gain: 0.468, pan: 0.18 }, synth: { gain: 0.396, pan: 0.25 },
    } },
  { id: "remember", name: "Do You Remember", genre: "Mellow band",
    combo: "steel guitar · piano · bass · cello", midi: "./midi/cc0-do-you-remember.mid",
    instrument: null, excerpt: 54,
    mix: {
      "guitar-steel": { gain: 0.52, pan: -0.2 }, piano: { gain: 0.52, pan: 0.15 },
      bass: { gain: 0.598, pan: 0 }, cello: { gain: 0.52, pan: 0.2 }, synth: { gain: 0.364, pan: 0.3 },
      drums: { gain: 0.169, pan: 0 },
    } },
  { id: "toccata", name: "Toccata & Fugue in D minor", genre: "Baroque · J.S. Bach (BWV 565)",
    combo: "organ", midi: "./midi/bach-toccata-fugue-dm.mid",
    instrument: "organ", excerpt: 52, mix: { organ: { gain: 0.44 } } },
  { id: "invention", name: "Invention No. 2", genre: "Baroque · J.S. Bach (BWV 773)",
    combo: "organ", midi: "./midi/bach-invention-2.mid",
    instrument: "organ", excerpt: 49, mix: { organ: { gain: 0.5 } } },
];

/**
 * Turn a parsed MIDI (from packages/midi parseMidi) into the showcase note list:
 * take the first `excerpt` seconds from the first onset, re-zero, and either keep
 * each note's own instrument (instrument == null → multi-instrument, routed by
 * gmProgramToGroup) or re-voice every note onto one instrument. Pure — no I/O —
 * so the browser and the Node render harness share it exactly.
 */
export function processMidi(parsed, demo) {
  const src = parsed.notes;
  if (!src.length) return [];
  const first = src[0].startSeconds;
  const end = first + (demo.excerpt ?? 50);
  const out = [];
  for (const nRaw of src) {
    if (nRaw.startSeconds >= end) continue;
    const start = nRaw.startSeconds - first;
    const finish = Math.min(nRaw.endSeconds, end) - first;
    if (finish <= start) continue;
    out.push({
      instrumentGroup: demo.instrument ?? nRaw.instrumentGroup,
      midiPitch: nRaw.midiPitch,
      startSeconds: +start.toFixed(5),
      endSeconds: +finish.toFixed(5),
      velocity: nRaw.velocity,
      isDrum: demo.instrument ? false : !!nRaw.isDrum,
    });
  }
  return out;
}
