export const RANDOMIZATION_ALGORITHM = "xorshift32-fisher-yates-v1";

export function xorshift32(input) {
  let state = input >>> 0;
  if (state === 0) state = 0x6d2b79f5;
  state ^= state << 13;
  state ^= state >>> 17;
  state ^= state << 5;
  return state >>> 0;
}

export function shuffleIds(values, seed) {
  const out = [...values];
  let state = seed >>> 0;
  for (let index = out.length - 1; index > 0; index--) {
    state = xorshift32(state);
    const swap = state % (index + 1);
    [out[index], out[swap]] = [out[swap], out[index]];
  }
  return out;
}

export function trialSeed(sessionSeed, trialIndex) {
  let state = sessionSeed >>> 0;
  for (let i = 0; i <= trialIndex; i++) state = xorshift32((state ^ 0x9e3779b9) >>> 0);
  return state;
}

export function presentations(experiment, seed) {
  return Object.fromEntries(experiment.trials.map((trial, index) => [
    trial.id,
    shuffleIds(trial.stimuli.map((item) => item.id), trialSeed(seed, index)),
  ]));
}

export function canonicalJson(value) {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

export async function manifestDigest(experiment) {
  const bytes = new TextEncoder().encode(canonicalJson(experiment));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((value) => value.toString(16).padStart(2, "0")).join("");
}
