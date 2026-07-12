import { RANDOMIZATION_ALGORITHM, manifestDigest, presentations } from "./randomization.js";

const $ = (selector) => document.querySelector(selector);
const manifestUrl = new URLSearchParams(location.search).get("experiment") ?? "pilot/experiment.json";
const experiment = await fetch(manifestUrl).then((response) => {
  if (!response.ok) throw new Error(`experiment load failed: ${response.status}`);
  return response.json();
});
const digest = await manifestDigest(experiment);
const base = new URL(manifestUrl, location.href);
const byTrial = Object.fromEntries(experiment.trials.map((trial) => [trial.id, trial]));
let session = null;
let trialIndex = 0;

$("#title").textContent = experiment.title;
$("#instructions").textContent = experiment.instructions;

function audioUrl(path) {
  return new URL(path, base).href;
}

function playCounts(order) {
  return Object.fromEntries(order.map((id) => [id, 0]));
}

function persist() {
  if (session) localStorage.setItem(`ij-listening:${session.session_id}`, JSON.stringify(session));
}

function player(label, id, path, response) {
  const wrapper = document.createElement("div");
  wrapper.className = "sample";
  wrapper.innerHTML = `<header><strong>${label}</strong><span class="plays">0 plays</span></header><audio controls preload="metadata"></audio>`;
  const audio = wrapper.querySelector("audio");
  audio.src = audioUrl(path);
  audio.addEventListener("play", () => {
    response.play_counts[id] += 1;
    wrapper.querySelector(".plays").textContent = `${response.play_counts[id]} plays`;
    persist();
  });
  return wrapper;
}

function baseResponse(trial, order) {
  return { trial_id: trial.id, protocol: trial.protocol, presentation: order, response: {}, play_counts: playCounts(order) };
}

function showTrial() {
  if (trialIndex >= experiment.trials.length) return finish();
  const trial = experiment.trials[trialIndex];
  const order = session.randomized_presentations[trial.id];
  const response = baseResponse(trial, order);
  const section = $("#trial");
  section.replaceChildren();
  section.hidden = false;
  const heading = document.createElement("div");
  heading.innerHTML = `<p class="progress">Trial ${trialIndex + 1} of ${experiment.trials.length} · ${trial.protocol.toUpperCase()}</p><h2>${trial.prompt}</h2>`;
  section.append(heading);
  const players = document.createElement("div");
  players.className = "players";
  const stimulus = Object.fromEntries(trial.stimuli.map((item) => [item.id, item]));
  if (trial.protocol === "mushra") {
    response.play_counts.reference = 0;
    players.append(player("Explicit reference", "reference", trial.reference.path, response));
  }
  order.forEach((id, index) => {
    const item = stimulus[id];
    const sample = player(`Sample ${index + 1}`, id, item.path, response);
    if (trial.protocol === "mushra") {
      const rating = document.createElement("label");
      rating.className = "rating";
      rating.innerHTML = `<span>0</span><input type="range" min="0" max="100" value="50"><output>—</output>`;
      const input = rating.querySelector("input"), output = rating.querySelector("output");
      input.addEventListener("input", () => {
        response.response.ratings ??= {};
        response.response.ratings[id] = Number(input.value);
        output.value = input.value;
        persist();
      });
      sample.append(rating);
    }
    players.append(sample);
  });
  if (trial.protocol === "abx") {
    response.play_counts.x = 0;
    const xItem = stimulus[trial.x_source];
    players.append(player("X", "x", xItem.path, response));
  }
  section.append(players);
  const choices = document.createElement("div");
  choices.className = "choices";
  if (trial.protocol !== "mushra") {
    const options = order.map((id, index) => ({ id, label: `Sample ${index + 1}` }));
    if (trial.protocol === "ab") options.push({ id: "tie", label: "No preference" });
    options.forEach((option) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = option.label;
      button.addEventListener("click", () => {
        response.response.choice = option.id;
        choices.querySelectorAll("button").forEach((item) => item.classList.remove("selected"));
        button.classList.add("selected");
        persist();
      });
      choices.append(button);
    });
    section.append(choices);
  }
  const next = document.createElement("button");
  next.textContent = trialIndex + 1 === experiment.trials.length ? "Submit session" : "Save and continue";
  next.addEventListener("click", () => {
    const complete = trial.protocol === "mushra"
      ? Object.keys(response.response.ratings ?? {}).length === order.length
      : Boolean(response.response.choice);
    if (!complete) return setStatus("Complete every rating or choice before continuing.");
    session.trials.push(response);
    trialIndex += 1;
    persist();
    showTrial();
  });
  section.append(next);
}

function setStatus(message) {
  $("#status").textContent = message;
}

function finish() {
  session.submitted_at = new Date().toISOString();
  delete session.randomized_presentations;
  persist();
  $("#trial").hidden = true;
  $("#complete").hidden = false;
  setStatus("Session stored locally. Export the raw JSON to preserve it.");
}

$("#start").addEventListener("click", () => {
  const listener = $("#listener").value.trim();
  const experience = $("#experience").value.trim();
  const environment = $("#environment").value.trim();
  const device = $("#device").value.trim();
  if (!listener || !experience || !environment || !device || !$("#volume").checked) return setStatus("Complete the setup and fixed-volume check first.");
  const forcedSeed = new URLSearchParams(location.search).get("seed");
  const seed = forcedSeed === null ? crypto.getRandomValues(new Uint32Array(1))[0] : Number(forcedSeed) >>> 0;
  session = {
    schema_version: "1.0.0",
    experiment_id: experiment.id,
    experiment_digest: digest,
    session_id: `${experiment.id}-${Date.now()}-${seed.toString(16).padStart(8, "0")}`,
    evidence_kind: "human",
    listener: { id: listener, experience, hearing_notes: $("#hearing").value.trim() },
    setup: { transducer: $("#transducer").value, environment, device, volume_check: true },
    randomization: { algorithm: RANDOMIZATION_ALGORITHM, seed },
    randomized_presentations: presentations(experiment, seed),
    started_at: new Date().toISOString(),
    submitted_at: "",
    trials: [],
  };
  $("#setup").hidden = true;
  showTrial();
});

$("#download").addEventListener("click", () => {
  const blob = new Blob([`${JSON.stringify(session, null, 2)}\n`], { type: "application/json" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `${session.session_id}.json`;
  link.click();
  URL.revokeObjectURL(link.href);
});

$("#clear").addEventListener("click", () => {
  localStorage.removeItem(`ij-listening:${session.session_id}`);
  location.reload();
});
