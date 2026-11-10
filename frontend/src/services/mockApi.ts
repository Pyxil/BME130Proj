/**
 * In-browser mock backend (enabled with VITE_USE_MOCKS=true / `npm run dev:mock`).
 *
 * For UI development only. Words, phonemes and the sample analysis/feedback
 * shapes are recorded from the real backend (src/mocks/fixtures.json); results
 * for other words are produced by adapting those samples deterministically.
 * Nothing here is real speech analysis.
 */
import fixtures from "../mocks/fixtures.json";
import type {
  AnalysisResult, AttemptOut, AttemptSummary, FeedbackResponse, ProgressOut, SessionOut, User, WordSummary,
} from "../types";
import { ApiError, type RequestOptions } from "./api";

type Fixtures = {
  words: WordSummary[];
  phonemes: unknown[];
  samples: Record<string, { analysis: AnalysisResult; feedback: FeedbackResponse }>;
  status: unknown;
  word_variants: Record<string, unknown[]>;
};
const fx = fixtures as unknown as Fixtures;

let user: User = {
  id: 1, email: "demo@example.com", display_name: "Demo", audience: "adult", preferred_accent: "us",
  store_recordings_consent: false, created_at: new Date().toISOString(),
};
const sessions = new Map<string, { id: string; mode: string; word_ids: number[]; current_index: number; status: string; started_at: string; completed_at: string | null; target_phoneme: string | null }>();
const attempts: AttemptOut[] = [];
let counter = 0;

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));
const word = (id: number) => fx.words.find((w) => w.id === id)!;

function mockAnalysis(w: WordSummary): AnalysisResult {
  counter += 1;
  if (counter % 4 === 0) {
    return { ...fx.samples.quality_noisy.analysis, word: w.word, word_id: w.id, analysis_id: `mock-${counter}` };
  }
  const template = fx.samples.rabbit_r_as_w.analysis;
  const weak = w.phonemes.findIndex((p) => w.target_sounds.includes(p));
  const scores = w.phonemes.map((p, i) => ({
    index: i, phoneme: p, arpabet: p, score: i === weak ? 68 : 95, posterior: i === weak ? 0.02 : 0.97,
    status: (i === weak ? "poor" : "good") as "poor" | "good", likely_realization: i === weak ? "w" : null,
    likely_realization_probability: i === weak ? 0.9 : null, deletion_probability: 0, accepted_variant: null,
    start_s: null, end_s: null,
  }));
  const issues = weak >= 0 ? [{
    id: `ph${weak}-substitution`, type: "substitution" as const, severity: "moderate" as const, phoneme: w.phonemes[weak],
    position: weak, realized_as: "w", message: `The /${w.phonemes[weak]}/ sound may have sounded more like /w/. (mock)`, evidence: {},
  }] : [];
  return {
    ...template, analysis_id: `mock-${counter}`, word: w.word, word_id: w.id, overall_score: weak >= 0 ? 69 : 96,
    rating: weak >= 0 ? "needs_practice" : "mastered", phonetically_accurate: weak < 0, phoneme_scores: scores,
    identified_issues: issues, recognized_word: w.word, word_recognized: true,
    matched_variant: { id: "us", accent: "General American", ipa: w.ipa, arpabet: [] },
    engine: { name: "mock", model: null, phoneme_level: true, calibration: null, notes: "Mock data - not a real analysis" },
  };
}

function sessionOut(id: string): SessionOut {
  const s = sessions.get(id);
  if (!s) throw new ApiError(404, "Session not found");
  const words = s.word_ids.map((wid, i) => {
    const att = attempts.filter((a) => a.session_id === id && a.word_id === wid);
    const scored = att.filter((a) => a.analysis.overall_score != null);
    const best = scored.length ? Math.max(...scored.map((a) => a.analysis.overall_score!)) : null;
    const last = scored.at(-1);
    return {
      position: i, word: word(wid), attempts: att.length, best_score: best, last_score: last?.analysis.overall_score ?? null,
      last_rating: last?.analysis.rating ?? null,
      status: (!att.length ? "pending" : last?.analysis.rating === "mastered" ? "mastered" : "attempted") as "pending" | "attempted" | "mastered",
    };
  });
  const bests = words.map((w) => w.best_score).filter((x): x is number => x != null);
  return {
    id, mode: s.mode as SessionOut["mode"], target_phoneme: s.target_phoneme, status: s.status as SessionOut["status"],
    started_at: s.started_at, completed_at: s.completed_at, current_index: s.current_index, total_words: words.length,
    words_attempted: words.filter((w) => w.attempts).length, words,
    average_score: bests.length ? bests.reduce((a, b) => a + b, 0) / bests.length : null, focus_phonemes: [],
  };
}

function summary(a: AttemptOut): AttemptSummary {
  return {
    id: a.attempt_id, word_id: a.word_id, word: a.analysis.word, session_id: a.session_id ?? null, created_at: a.created_at,
    attempt_number: a.attempt_number, status: a.analysis.status, overall_score: a.analysis.overall_score ?? null,
    rating: a.analysis.rating ?? null, confidence: a.analysis.confidence, has_recording: false,
    feedback_summary: a.feedback?.summary ?? null,
  };
}

function progress(): ProgressOut {
  const scored = attempts.filter((a) => a.analysis.overall_score != null);
  const scores = scored.map((a) => a.analysis.overall_score!);
  const today = new Date().toISOString().slice(0, 10);
  return {
    average_score: scores.length ? scores.reduce((a, b) => a + b, 0) / scores.length : null,
    total_attempts: attempts.length, assessed_attempts: scored.length,
    words_attempted: new Set(attempts.map((a) => a.word_id)).size, words_completed: new Set(scored.map((a) => a.word_id)).size,
    words_mastered: new Set(scored.filter((a) => a.analysis.rating === "mastered").map((a) => a.word_id)).size,
    total_sessions: sessions.size, improvement: null,
    score_over_time: scores.length ? [{ date: today, average_score: scores.reduce((a, b) => a + b, 0) / scores.length, attempts: scores.length }] : [],
    phoneme_stats: [], most_mispronounced: [], words_needing_practice: [], recent_sessions: [],
    recent_attempts: attempts.slice(-10).reverse().map(summary),
  };
}

export async function mockRequest<T>(path: string, opts: RequestOptions): Promise<T> {
  await delay(path.includes("analyze") ? 900 : 120);
  const method = opts.method ?? (opts.json !== undefined || opts.form ? "POST" : "GET");
  const body = (opts.json ?? {}) as Record<string, unknown>;
  const m = (re: RegExp) => path.match(re);
  let out: unknown;
  if (path === "/api/auth/login" || path === "/api/auth/register") {
    out = { access_token: "mock-token", token_type: "bearer", expires_in: 86400, user };
  } else if (path === "/api/users/me" && method === "PATCH") {
    user = { ...user, ...(body as Partial<User>) };
    out = user;
  } else if (path === "/api/users/me") out = user;
  else if (path === "/api/users/me/progress") out = progress();
  else if (path === "/api/words/phonemes") out = fx.phonemes;
  else if (path === "/api/words") out = { total: fx.words.length, items: fx.words };
  else if (m(/^\/api\/words\/(\d+)$/)) out = { ...word(Number(m(/(\d+)$/)![1])), variants: [], evaluation_features: [], arpabet: [], stress_pattern: [], syllable_breakdown: [] };
  else if (path === "/api/sessions" && method === "POST") {
    const size = Number(body.size ?? 10);
    let pool = fx.words;
    if (["easy", "medium", "hard"].includes(String(body.mode))) pool = pool.filter((w) => w.difficulty === body.mode);
    if (body.mode === "phoneme") pool = pool.filter((w) => w.phonemes.includes(String(body.phoneme)));
    const id = `mock-session-${sessions.size + 1}`;
    sessions.set(id, { id, mode: String(body.mode), word_ids: pool.slice(0, size).map((w) => w.id), current_index: 0, status: "active",
      started_at: new Date().toISOString(), completed_at: null, target_phoneme: (body.phoneme as string) ?? null });
    out = sessionOut(id);
  } else if (path === "/api/sessions") out = [];
  else if (m(/^\/api\/sessions\/([^/]+)\/advance$/)) {
    const s = sessions.get(m(/^\/api\/sessions\/([^/]+)/)![1])!;
    if (s.current_index + 1 >= s.word_ids.length) { s.status = "completed"; s.completed_at = new Date().toISOString(); }
    else s.current_index += 1;
    out = sessionOut(s.id);
  } else if (m(/^\/api\/sessions\/([^/]+)$/)) out = sessionOut(m(/^\/api\/sessions\/([^/]+)$/)![1]);
  else if (path === "/api/pronunciation/analyze") {
    const form = opts.form!;
    const w = word(Number(form.get("word_id")));
    const prev = attempts.filter((a) => a.word_id === w.id).length;
    const a: AttemptOut = {
      attempt_id: `mock-attempt-${attempts.length + 1}`, attempt_number: prev + 1, word_id: w.id,
      session_id: (form.get("session_id") as string) ?? null, created_at: new Date().toISOString(),
      analysis: mockAnalysis(w), feedback: null, has_recording: false, word_best_score: null,
    };
    attempts.push(a);
    out = a;
  } else if (path === "/api/feedback") {
    const a = attempts.find((x) => x.attempt_id === body.attempt_id);
    const base = fx.samples.rabbit_r_as_w.feedback;
    const issues = a?.analysis.identified_issues ?? [];
    out = {
      ...base,
      summary: `${a?.analysis.word ?? "This word"} scored ${a?.analysis.overall_score}/100. (mock feedback)`,
      recommendations: issues.map((i) => ({ issue_id: i.id, tip: i.message, articulation: base.recommendations?.[0]?.articulation ?? "" })),
    };
    if (a) a.feedback = out as FeedbackResponse;
  } else if (path === "/api/attempts") out = { total: attempts.length, items: attempts.slice().reverse().map(summary) };
  else if (m(/^\/api\/attempts\/([^/]+)$/)) {
    const a = attempts.find((x) => x.attempt_id === m(/^\/api\/attempts\/([^/]+)$/)![1]);
    if (!a) throw new ApiError(404, "Attempt not found");
    out = a;
  } else if (path === "/api/system/status") out = fx.status;
  else if (method === "DELETE") out = path.endsWith("recordings") ? { deleted: 0 } : undefined;
  else throw new ApiError(404, `Mock route not implemented: ${method} ${path}`);
  return out as T;
}
