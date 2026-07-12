#!/usr/bin/env node
import { spawn } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { chromium } from "playwright";
import { manifestDigest, presentations } from "../../evals/listening/randomization.js";

const port = 8174;
const server = spawn("python3", ["-m", "http.server", String(port), "--bind", "127.0.0.1"], { cwd: new URL("../..", import.meta.url), stdio: "ignore" });
const temporary = await mkdtemp(join(tmpdir(), "ij-listening-"));
let browser;
try {
  await new Promise((resolve) => setTimeout(resolve, 450));
  browser = await chromium.launch();
  const page = await browser.newPage({ acceptDownloads: true });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => message.type() === "error" && errors.push(message.text()));
  const seed = 0x10010001;
  await page.goto(`http://127.0.0.1:${port}/evals/listening/?experiment=pilot/experiment.json&seed=${seed}`, { waitUntil: "networkidle" });
  await page.fill("#listener", "browser-pilot");
  await page.fill("#experience", "harness validation");
  await page.fill("#environment", "headless browser");
  await page.fill("#device", "Playwright Chromium");
  await page.check("#volume");
  await page.click("#start");
  const visible = await page.locator("body").innerText();
  if (visible.includes("condition-h") || visible.includes("pilot-reference.wav") || visible.includes("hidden_reference")) throw new Error("visual identity leak");
  for (const slider of await page.locator('input[type="range"]').all()) {
    await slider.fill("95");
  }
  await page.getByRole("button", { name: "Submit session" }).click();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export raw session JSON" }).click();
  const download = await downloadPromise;
  const saved = join(temporary, "session.json");
  await download.saveAs(saved);
  const session = JSON.parse(await readFile(saved, "utf8"));
  const experiment = JSON.parse(await readFile(new URL("../../evals/listening/pilot/experiment.json", import.meta.url), "utf8"));
  const expected = presentations(experiment, seed)["synthetic-tone-mushra"];
  const stored = await page.evaluate((key) => localStorage.getItem(key), `ij-listening:${session.session_id}`);
  const assertions = {
    noConsoleErrors: errors.length === 0,
    digestMatches: session.experiment_digest === await manifestDigest(experiment),
    presentationMatches: JSON.stringify(session.trials[0].presentation) === JSON.stringify(expected),
    rawRatingsStored: Object.keys(session.trials[0].response.ratings).length === 3,
    setupStored: session.setup.device === "Playwright Chromium" && session.setup.volume_check === true,
    localRoundTrip: stored === JSON.stringify(session),
    noVerdict: !("quality_verdict" in session),
  };
  const verdict = Object.values(assertions).every(Boolean) ? "PASS" : "FAIL";
  console.log(JSON.stringify({ verdict, seed, presentation: expected, assertions, errors }, null, 2));
  if (verdict !== "PASS") process.exitCode = 1;
} finally {
  if (browser) await browser.close();
  server.kill("SIGTERM");
  await rm(temporary, { recursive: true, force: true });
}
