#!/usr/bin/env node
import { spawn, spawnSync } from "node:child_process";
import { copyFile, mkdir, mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { manifestDigest, presentations, trialOrder } from "../../evals/listening/randomization.js";

const ROOT = fileURLToPath(new URL("../..", import.meta.url));
const PYTHON = process.env.PYTHON ?? "python3";
const port = 8174;
const server = spawn(PYTHON, ["-m", "http.server", String(port), "--bind", "127.0.0.1"], { cwd: ROOT, stdio: "ignore" });
const downloads = await mkdtemp(join(tmpdir(), "ij-listening-downloads-"));
const campaignRoot = await mkdtemp(join(ROOT, ".listening-e2e-"));
let browser;

function runPython(args) {
  const result = spawnSync(PYTHON, args, { cwd: ROOT, encoding: "utf8" });
  if (result.status !== 0) throw new Error(`python failed (${args.join(" ")}):\n${result.stdout}\n${result.stderr}`);
  return result.stdout;
}

async function completeSetup(page, listener) {
  await page.fill("#listener", listener);
  await page.fill("#experience", "harness validation");
  await page.fill("#environment", "headless browser");
  await page.fill("#device", "Playwright Chromium");
  await page.check("#volume");
  await page.click("#start");
}

async function exportSession(page, destination) {
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export raw session JSON" }).click();
  const download = await downloadPromise;
  await download.saveAs(destination);
  return JSON.parse(await readFile(destination, "utf8"));
}

async function playEveryVisibleSample(page) {
  for (const audio of await page.locator("audio").all()) {
    await audio.evaluate(async (element) => {
      await element.play();
      await new Promise((resolve) => setTimeout(resolve, 40));
      element.pause();
    });
  }
}

async function createCampaignBundle() {
  const baseline = join(campaignRoot, "baseline");
  const candidate = join(campaignRoot, "candidate");
  await mkdir(join(baseline, "renders"), { recursive: true });
  await mkdir(join(candidate, "renders"), { recursive: true });
  await copyFile(join(ROOT, "evals/listening/pilot/pilot-reference.wav"), join(baseline, "renders/case-a.wav"));
  await copyFile(join(ROOT, "evals/listening/pilot/pilot-candidate.wav"), join(candidate, "renders/case-a.wav"));
  const common = { family: "piano", metric_version: "browser-round-trip", manifest: { sha256: "a".repeat(64) }, cases: [{ id: "case-a" }] };
  await writeFile(join(baseline, "iteration.json"), `${JSON.stringify({ ...common, source: { commit: "1".repeat(40) } }, null, 2)}\n`);
  await writeFile(join(candidate, "iteration.json"), `${JSON.stringify({ ...common, source: { commit: "2".repeat(40) } }, null, 2)}\n`);
  runPython(["scripts/dev/listening.py", "prepare-campaign", candidate, "--baseline", baseline, "--out", join(candidate, "listening")]);
  return { candidate, bundle: join(candidate, "listening") };
}

async function waitForServer(url) {
  for (let attempt = 0; attempt < 100; attempt++) {
    try {
      const response = await fetch(url);
      if (response.ok) return;
    } catch {}
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error(`listening test server did not become ready: ${url}`);
}

try {
  await waitForServer(`http://127.0.0.1:${port}/evals/listening/`);
  browser = await chromium.launch();
  const page = await browser.newPage({ acceptDownloads: true });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => message.type() === "error" && errors.push(message.text()));

  const seed = 0x10010001;
  await page.goto(`http://127.0.0.1:${port}/evals/listening/?experiment=pilot/experiment.json&seed=${seed}`, { waitUntil: "networkidle" });
  await completeSetup(page, "browser-pilot");
  const visible = await page.locator("body").innerText();
  if (visible.includes("condition-h") || visible.includes("pilot-reference.wav") || visible.includes("hidden_reference")) throw new Error("visual identity leak");
  await playEveryVisibleSample(page);
  for (const slider of await page.locator('input[type="range"]').all()) await slider.fill("95");
  await page.getByRole("button", { name: "Submit session" }).click();
  const pilotSession = await exportSession(page, join(downloads, "pilot-session.json"));
  const pilotExperiment = JSON.parse(await readFile(join(ROOT, "evals/listening/pilot/experiment.json"), "utf8"));
  const expected = presentations(pilotExperiment, seed)["synthetic-tone-mushra"];
  const stored = await page.evaluate((key) => localStorage.getItem(key), `ij-listening:${pilotSession.session_id}`);
  const pilotAssertions = {
    digestMatches: pilotSession.experiment_digest === await manifestDigest(pilotExperiment),
    presentationMatches: JSON.stringify(pilotSession.trials[0].presentation) === JSON.stringify(expected),
    trialOrderMatches: JSON.stringify(pilotSession.trial_order) === JSON.stringify(trialOrder(pilotExperiment, seed)),
    rawRatingsStored: Object.keys(pilotSession.trials[0].response.ratings).length === 3,
    setupStored: pilotSession.setup.device === "Playwright Chromium" && pilotSession.setup.volume_check === true,
    localRoundTrip: stored === JSON.stringify(pilotSession),
    noVerdict: !("quality_verdict" in pilotSession),
  };

  const { bundle } = await createCampaignBundle();
  const bundleUrl = relative(ROOT, join(bundle, "index.html")).split(sep).join("/");
  await page.goto(`http://127.0.0.1:${port}/${bundleUrl}?seed=305419896`, { waitUntil: "networkidle" });
  await completeSetup(page, "campaign-browser-pilot");
  const campaignVisible = await page.locator("body").innerText();
  if (campaignVisible.includes("candidate") || campaignVisible.includes("incumbent") || campaignVisible.includes("case-a-candidate")) throw new Error("campaign visual identity leak");
  await playEveryVisibleSample(page);
  await page.getByRole("button", { name: "Sample 1" }).click();
  await page.getByRole("button", { name: "Submit session" }).click();
  const campaignSessionPath = join(downloads, "campaign-session.json");
  const campaignSession = await exportSession(page, campaignSessionPath);
  const campaignExperimentPath = join(bundle, "experiment.json");
  const analysisPath = join(downloads, "campaign-analysis.json");
  runPython(["scripts/dev/listening.py", "analyze", campaignExperimentPath, campaignSessionPath, "--out", analysisPath]);
  const campaignExperiment = JSON.parse(await readFile(campaignExperimentPath, "utf8"));
  const campaignAnalysis = JSON.parse(await readFile(analysisPath, "utf8"));
  const campaignAssertions = {
    digestMatchesAcrossLanguages: campaignSession.experiment_digest === await manifestDigest(campaignExperiment)
      && campaignSession.experiment_digest === campaignAnalysis.experiment_digest,
    rawChoiceStored: campaignSession.trials[0].response.choice === campaignSession.trials[0].presentation[0],
    pythonAcceptedBrowserSession: campaignAnalysis.n_submitted === 1 && campaignAnalysis.n_included === 1,
    rawSessionRetained: campaignAnalysis.raw_sessions[0].session_id === campaignSession.session_id,
    noVerdict: campaignAnalysis.quality_verdict === null,
  };
  const assertions = { noConsoleErrors: errors.length === 0, pilot: pilotAssertions, campaign: campaignAssertions };
  const verdict = errors.length === 0
    && Object.values(pilotAssertions).every(Boolean)
    && Object.values(campaignAssertions).every(Boolean) ? "PASS" : "FAIL";
  console.log(JSON.stringify({ verdict, seed, pilotPresentation: expected, assertions, errors }, null, 2));
  if (verdict !== "PASS") process.exitCode = 1;
} finally {
  if (browser) await browser.close();
  server.kill("SIGTERM");
  await rm(downloads, { recursive: true, force: true });
  await rm(campaignRoot, { recursive: true, force: true });
}
