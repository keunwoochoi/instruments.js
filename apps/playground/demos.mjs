/**
 * Beta demo set — REAL, public-domain music (owner 2026-07-21: original
 * arrangements were "too cute"; use real music MIDI). Every file is Mutopia
 * Project MIDI whose per-piece page states Public Domain for the sequence
 * itself, so it is safe to commit and ship. Provenance + sha in
 * agentic-docs/licensing.md ("Demo music (bundled MIDI)").
 *
 * The pieces are piano-forward (piano is the flagship), with two re-voiced onto
 * other instruments — arranging PD works is unrestricted — so the set also shows
 * the harp and the organ:
 *   The Entertainer / Elite Syncopations (Joplin) ...... piano   (ragtime)
 *   Clair de Lune (Debussy) ............................ piano   (impressionist)
 *   Première Arabesque (Debussy) ....................... harp    (idiomatic)
 *   Invention No. 2, BWV 773 (Bach) .................... organ   (baroque)
 *
 * A demo entry: { id, name, genre, combo, midi (url/path), instrument, excerpt
 * (seconds), mix }. The browser fetches `midi` and the Node harness reads it;
 * both then call parseMidi() and processMidi() — the excerpt+route is shared.
 */

export const DEMOS = [
  { id: "entertainer", name: "The Entertainer", genre: "Ragtime · Scott Joplin",
    combo: "piano", midi: "./midi/joplin-entertainer.mid",
    instrument: "piano", excerpt: 47, mix: { piano: { gain: 0.6 } } },
  { id: "clair", name: "Clair de Lune", genre: "Impressionist · Debussy",
    combo: "piano", midi: "./midi/debussy-clair-de-lune.mid",
    instrument: "piano", excerpt: 54, mix: { piano: { gain: 0.64 } } },
  { id: "arabesque", name: "Première Arabesque", genre: "Impressionist · Debussy",
    combo: "harp", midi: "./midi/debussy-arabesque-1.mid",
    instrument: "harp", excerpt: 47, mix: { harp: { gain: 0.6 } } },
  { id: "elite", name: "Elite Syncopations", genre: "Ragtime · Scott Joplin",
    combo: "piano", midi: "./midi/joplin-elite-syncopations.mid",
    instrument: "piano", excerpt: 47, mix: { piano: { gain: 0.6 } } },
  { id: "bach", name: "Invention No. 2", genre: "Baroque · J.S. Bach",
    combo: "organ", midi: "./midi/bach-invention-2.mid",
    instrument: "organ", excerpt: 49, mix: { organ: { gain: 0.5 } } },
];

/**
 * Turn a parsed MIDI (from packages/midi parseMidi) into the showcase note list:
 * take the first `excerpt` seconds from the first onset, re-zero, and (optionally)
 * re-voice every note onto one instrument. Pure — no I/O — so the browser and the
 * Node render harness share it exactly.
 */
export function processMidi(parsed, demo) {
  const src = parsed.notes;
  if (!src.length) return [];
  const first = src[0].startSeconds;
  const end = first + (demo.excerpt ?? 47);
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
