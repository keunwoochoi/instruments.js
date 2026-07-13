#!/usr/bin/env node
/**
 * Sizes the higher-capacity piano soundboard (#49) from measurement.
 *
 *   cargo build -p instruments-dsp --target wasm32-unknown-unknown --release \
 *     --features bench-scaffold
 *   npm run bench:soundboard
 *
 * Two numbers decide Architecture A:
 *
 *   1. The OPEN-LOOP board (A2): M independent 2nd-order modes driven by the summed
 *      bridge force. Cheap, and cheap regardless of polyphony.
 *
 *   2. The CLOSED-LOOP coupling (A3): the board's motion returning into every string.
 *      Projecting each string onto every mode costs O(M) PER VOICE and is what makes a
 *      naive coupled board unaffordable. Projecting a fixed basis of P bridge ports onto
 *      the modes costs O(P*M) ONCE PER SAMPLE — voices only read and write their port —
 *      so the coupling becomes a fixed shared cost. This bench measures that claim rather
 *      than asserting it.
 *
 * The scaffold is behind a Cargo feature and is never in the shipped wasm.
 */
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const WASM = process.argv[2]
  ? process.argv[2]
  : fileURLToPath(new URL("../../target/wasm32-unknown-unknown/release/instruments_dsp.wasm", import.meta.url));

const Q = 128;
const SR = Number(process.env.SR ?? 48000);
const BUDGET_US = (Q / SR) * 1e6;

const { instance } = await WebAssembly.instantiate(await readFile(WASM), {});
const { ij_bench_modes: modes, ij_bench_ports: ports } = instance.exports;

if (!modes || !ports) {
  console.error(
    "bench-soundboard: the measurement exports are missing.\n" +
      "Build with the feature first:\n" +
      "  cargo build -p instruments-dsp --target wasm32-unknown-unknown --release --features bench-scaffold",
  );
  process.exit(1);
}

const time = (fn, reps) => {
  for (let i = 0; i < 30; i++) fn(); // warm
  const t0 = process.hrtime.bigint();
  for (let i = 0; i < reps; i++) fn();
  return Number(process.hrtime.bigint() - t0) / 1000 / reps;
};
const pct = (us) => ((us / BUDGET_US) * 100).toFixed(2) + "%";

console.log(`budget ${BUDGET_US.toFixed(1)} us/quantum @ ${SR} Hz, ${Q} frames\n`);

console.log("OPEN LOOP (A2) — board alone, driven by summed bridge force");
console.log("  modes   us/quantum   %budget   ns/mode-sample");
for (const m of [64, 128, 200, 256, 400]) {
  const us = time(() => modes(m, Q), 400);
  console.log(
    `  ${String(m).padStart(5)}   ${us.toFixed(1).padStart(10)}   ${pct(us).padStart(7)}   ${(
      (us * 1000) / (m * Q)
    ).toFixed(2).padStart(14)}`,
  );
}

console.log("\nCLOSED LOOP (A3) — P bridge ports <-> M modes, both directions.");
console.log("This cost is SHARED: it does not scale with the number of sounding voices.");
console.log("  ports  modes   us/quantum   %budget");
for (const [p, m] of [
  [4, 96],
  [4, 128],
  [6, 128],
  [4, 200],
  [6, 200],
  [8, 256],
  [8, 400],
]) {
  const us = time(() => ports(p, m, Q), 200);
  console.log(
    `  ${String(p).padStart(5)}  ${String(m).padStart(5)}   ${us.toFixed(1).padStart(10)}   ${pct(us).padStart(7)}`,
  );
}

console.log(
  "\nThese are desktop numbers. The architecture doc's exit gate is 50% of budget\n" +
    "on M1 AND mid-tier Android; a phone is roughly 3-4x slower, so the shipped\n" +
    "config must degrade (fewer ports, fewer modes) and that must be measured on\n" +
    "device before A3 is accepted. See agentic-docs/design/2026-07-13-higher-capacity-piano.md.",
);
