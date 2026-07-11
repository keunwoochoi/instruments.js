# instruments.js (core)

The public API: engine lifecycle, worklet host, WASM handshake, voice/track management, scheduling, offline render.

Owner doc for API/packaging decisions. Contracts that must never break:
- SSR-safe imports (nothing touches `window`/`AudioContext` at import time)
- `sideEffects: false`, correct `exports` map, tree-shakeable ESM, first-class types
- One shared worklet/WASM engine for all tracks (multi-track = PRINCIPLES #4)
- The WASM payload counts in every published bundle-size number (~24 KB gz all-in today:
  18 KB wasm + 4 KB core JS + 2 KB worklet)

Asset loading, honestly: default URLs resolve via `import.meta.url`, which works
unbundled and under most Vite/Webpack 5 builds; the **supported path everywhere**
(incl. Next.js) is the explicit `workletUrl`/`wasmUrl` options pointing at
self-hosted copies. Zero-config across Vite/Next/Webpack is a Q2 GOAL, gated on
`demos/bundler-matrix/` fixtures running green in CI — it is not yet verified.
`exports` points at `dist/` (built by `npm run build`).
