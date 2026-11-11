/**
 * End-to-end test of the core workflow in a real browser:
 *   Display word -> Hear -> Record (fake mic) -> Analyze -> Score -> AI feedback -> Next word -> Repeat
 *
 * Requires the backend (port 8000, with models) and the Vite dev server (port 5173) running.
 *   node e2e/practice-flow.cjs
 * Env: APP_URL, API_URL, PYTHON (interpreter with the project installed), SHOTS (screenshot dir).
 */
const { chromium, devices } = require("playwright");
const { execFileSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");

const APP = process.env.APP_URL || "http://localhost:5173";
const API = process.env.API_URL || "http://127.0.0.1:8000";
const PY = process.env.PYTHON || "python3";
const SHOTS = process.env.SHOTS || path.join(__dirname, "..", "docs", "images");
const TMP = fs.mkdtempSync(path.join(os.tmpdir(), "e2e-"));
fs.mkdirSync(SHOTS, { recursive: true });

async function api(p, body, token) {
  const res = await fetch(API + p, {
    method: body ? "POST" : "GET",
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${p}: ${res.status} ${await res.text()}`);
  return res.json();
}

function fakeMic(word, swap) {
  const out = path.join(TMP, `${word}${swap ? "-err" : ""}.wav`);
  const args = [path.join(__dirname, "make_fake_mic_wav.py"), word, out];
  if (swap) args.push("--swap", swap);
  console.log(execFileSync(PY, args, { encoding: "utf8" }).trim());
  return out;
}

async function browserWithMic(wav, token, device) {
  const browser = await chromium.launch({
    args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
      `--use-file-for-fake-audio-capture=${wav}%noloop`, "--autoplay-policy=no-user-gesture-required"],
  });
  const context = await browser.newContext(device ?? { viewport: { width: 1280, height: 900 }, deviceScaleFactor: 2 });
  await context.grantPermissions(["microphone"], { origin: APP });
  await context.addInitScript((t) => localStorage.setItem("sayitright.token", t), token);
  return { browser, page: await context.newPage() };
}

async function recordAndWait(page, label) {
  await page.getByRole("button", { name: "Record", exact: true }).click();
  await page.getByText(/Recording… say/).waitFor({ timeout: 10000 });
  await page.waitForTimeout(1600);
  await page.screenshot({ path: path.join(SHOTS, `${label}-recording.png`) });
  await page.getByRole("heading", { name: /Pronunciation score: \d+\/100/ }).or(page.getByText("Please record again"))
    .waitFor({ timeout: 45000 });
  await page.getByText(/Writing personalised tips/).waitFor({ state: "detached", timeout: 30000 }).catch(() => {});
  await page.waitForTimeout(400);
}

(async () => {
  const email = `e2e-${Date.now()}@example.com`;
  const { access_token: token } = await api("/api/auth/register", { email, password: "e2e-password", display_name: "Alex" });
  const session = await api("/api/sessions", { mode: "phoneme", phoneme: "r", size: 3 }, token);
  const [w1, w2] = session.words.map((w) => w.word.word);
  console.log(`session ${session.id}: ${session.words.map((w) => w.word.word).join(", ")}`);

  // --- Word 1: correct pronunciation
  let { browser, page } = await browserWithMic(fakeMic(w1), token);
  await page.goto(`${APP}/practice`);
  await page.getByRole("heading", { name: "Practise your pronunciation" }).waitFor();
  await page.screenshot({ path: path.join(SHOTS, "01-practice-setup.png"), fullPage: true });
  // The example audio is prefetched when the word appears, so playback starts inside the click.
  const audioResp = page.waitForResponse((r) => r.url().includes("/audio") && r.status() === 200);
  await page.goto(`${APP}/practice/${session.id}`);
  await page.getByText(`Word 1 of ${session.total_words}`).waitFor();
  const ref = await audioResp;
  console.log(`reference audio prefetched: ${ref.headers()["x-reference-source"]}`);
  await page.getByRole("button", { name: /Hear pronunciation/ }).click();
  await page.screenshot({ path: path.join(SHOTS, "02-exercise.png"), fullPage: true });
  await recordAndWait(page, "03");
  await page.screenshot({ path: path.join(SHOTS, "04-results-correct.png"), fullPage: true });
  const score1 = await page.getByRole("heading", { name: /Pronunciation score/ }).textContent();
  console.log(`word 1 '${w1}': ${score1}`);
  await page.getByRole("button", { name: /Next word/ }).click();
  await page.getByText(`Word 2 of ${session.total_words}`).waitFor();
  console.log("advanced to word 2");
  await browser.close();

  // --- Word 2: controlled /r/ -> /w/ substitution
  ({ browser, page } = await browserWithMic(fakeMic(w2, "R:W"), token));
  await page.goto(`${APP}/practice/${session.id}`);
  await page.getByText(`Word 2 of ${session.total_words}`).waitFor();
  await recordAndWait(page, "05");
  await page.screenshot({ path: path.join(SHOTS, "06-results-error.png"), fullPage: true });
  console.log(`word 2 '${w2}' (r->w): ${await page.getByRole("heading", { name: /Pronunciation score/ }).textContent()}`);
  const issues = await page.locator("#improve-h + ul li").allTextContents();
  console.log("areas to improve:", issues);
  // Try again path
  await page.getByRole("button", { name: /Try again/ }).click();
  await page.getByRole("button", { name: "Record", exact: true }).waitFor();
  console.log("try again resets the recorder");

  await page.goto(`${APP}/dashboard`);
  await page.getByRole("heading", { name: "Pronunciation score over time" }).waitFor();
  await page.waitForTimeout(600);
  await page.screenshot({ path: path.join(SHOTS, "07-dashboard.png"), fullPage: true });
  await page.goto(`${APP}/history`);
  await page.getByRole("heading", { name: "Your attempts" }).waitFor();
  await page.screenshot({ path: path.join(SHOTS, "08-history.png"), fullPage: true });
  await browser.close();

  // --- Mobile layout
  ({ browser, page } = await browserWithMic(fakeMic(w1), token, devices["iPhone 13"]));
  await page.goto(`${APP}/practice/${session.id}`);
  await page.getByText(/Word \d of/).waitFor();
  await page.screenshot({ path: path.join(SHOTS, "09-mobile-exercise.png"), fullPage: true });
  await browser.close();

  const attempts = await api("/api/attempts", null, token);
  console.log("attempts stored:", attempts.items.map((a) => `${a.word}=${a.overall_score}(${a.rating})`).join(", "));
  console.log("E2E OK");
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
