import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { RecordButton } from "../components/RecordButton";
import { ResultsPanel } from "../components/ResultsPanel";
import { Alert, Badge, Button, Card, Spinner } from "../components/ui";
import { Waveform } from "../components/Waveform";
import { WordCard } from "../components/WordCard";
import { useAudioRecorder } from "../hooks/useAudioRecorder";
import { useAuth } from "../hooks/useAuth";
import { useReferenceAudio } from "../hooks/useReferenceAudio";
import { ApiError } from "../services/api";
import { api } from "../services/endpoints";
import type { AttemptOut, FeedbackResponse, SessionOut } from "../types";
import { SessionSummaryView } from "./SessionSummary";

type Phase = "ready" | "analyzing" | "results";

export default function ExercisePage() {
  const { sessionId = "" } = useParams();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [session, setSession] = useState<SessionOut | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>("ready");
  const [attempt, setAttempt] = useState<AttemptOut | null>(null);
  const [analyzeError, setAnalyzeError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<FeedbackResponse | null>(null);
  const [feedbackLoading, setFeedbackLoading] = useState(false);
  const [feedbackError, setFeedbackError] = useState<string | null>(null);
  const [advancing, setAdvancing] = useState(false);
  const recorder = useAudioRecorder();
  const reference = useReferenceAudio();
  const uploadedUrl = useRef<string | null>(null);
  const accent = user?.preferred_accent ?? "us";

  useEffect(() => {
    api.session(sessionId).then(setSession).catch((e: ApiError) => setLoadError(e.message));
  }, [sessionId]);

  const current = session ? session.words[Math.min(session.current_index, session.words.length - 1)] : null;
  const word = current?.word ?? null;

  const resetAttempt = useCallback(() => {
    recorder.reset();
    setAttempt(null);
    setFeedback(null);
    setFeedbackError(null);
    setAnalyzeError(null);
    setPhase("ready");
  }, [recorder]);

  // Upload automatically when a recording is ready.
  useEffect(() => {
    const rec = recorder.recording;
    if (recorder.state !== "done" || !rec || !word || !session || uploadedUrl.current === rec.url) return;
    uploadedUrl.current = rec.url;
    setPhase("analyzing");
    setAnalyzeError(null);
    api.analyze(rec.blob, word.id, session.id, !!user?.store_recordings_consent)
      .then(async (a) => {
        setAttempt(a);
        setPhase("results");
        api.session(session.id).then(setSession).catch(() => undefined);
        if (a.analysis.status === "assessed") {
          setFeedbackLoading(true);
          try {
            setFeedback(await api.feedback(a.attempt_id));
          } catch (e) {
            setFeedbackError((e as Error).message || "Could not load recommendations.");
          } finally {
            setFeedbackLoading(false);
          }
        }
      })
      .catch((e: ApiError) => {
        setAnalyzeError(e.message || "Analysis failed. Please try again.");
        setPhase("ready");
      });
  }, [recorder.state, recorder.recording, word, session, user?.store_recordings_consent]);

  const hear = useCallback((slow = false) => {
    if (word) reference.play(word.id, word.word, accent, slow);
  }, [word, reference, accent]);

  // Fetch the example audio as soon as the word appears so "Hear pronunciation" plays instantly.
  const { prefetch } = reference;
  useEffect(() => {
    if (word) prefetch(word.id, accent);
  }, [word, accent, prefetch]);

  const next = useCallback(async () => {
    if (!session) return;
    setAdvancing(true);
    try {
      const s = await api.advance(session.id);
      setSession(s);
      resetAttempt();
    } finally {
      setAdvancing(false);
    }
  }, [session, resetAttempt]);

  // Keyboard shortcuts: R record/stop, H hear, T try again, N next word.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t.closest("input, textarea, select, [contenteditable]") || e.metaKey || e.ctrlKey || e.altKey) return;
      const k = e.key.toLowerCase();
      if (k === "r" && phase === "ready") {
        if (recorder.state === "recording") recorder.stop();
        else void recorder.start();
      } else if (k === "h") hear(e.shiftKey);
      else if (k === "t" && phase === "results") resetAttempt();
      else if (k === "n" && phase === "results") void next();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [phase, recorder, hear, resetAttempt, next]);

  if (loadError) return <Alert kind="error" title="Could not load this session">{loadError} <Link className="underline" to="/practice">Start a new one</Link></Alert>;
  if (!session || !word) return <Spinner label="Loading session…" />;
  if (session.status === "completed") return <SessionSummaryView session={session} onNew={() => navigate("/practice")} />;

  const position = Math.min(session.current_index, session.total_words - 1) + 1;
  const recording = recorder.state === "recording";
  const seconds = (recorder.elapsedMs / 1000).toFixed(1);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-lg font-bold" aria-live="polite">Word {position} of {session.total_words}</p>
        {session.focus_phonemes && session.focus_phonemes.length > 0 && (
          <Badge tone="brand">Focusing on <span className="ipa ml-1">{session.focus_phonemes.map((p) => `/${p}/`).join(" ")}</span></Badge>
        )}
      </div>
      <div className="h-3 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800" role="progressbar"
        aria-valuemin={1} aria-valuemax={session.total_words} aria-valuenow={position} aria-label="Session progress">
        <div className="h-3 rounded-full bg-brand-600 transition-all" style={{ width: `${(position / session.total_words) * 100}%` }} />
      </div>

      <Card className="space-y-8">
        <WordCard word={word} />
        <div className="flex flex-wrap justify-center gap-3">
          <Button variant="secondary" size="lg" onClick={() => hear(false)} aria-keyshortcuts="h">
            🔊 Hear pronunciation
          </Button>
          <Button variant="ghost" size="lg" onClick={() => hear(true)} aria-keyshortcuts="Shift+h">
            🐢 Slowly
          </Button>
        </div>

        {phase !== "results" && (
          <div className="space-y-4">
            <RecordButton state={recorder.state} disabled={phase === "analyzing"}
              onStart={() => void recorder.start()} onStop={recorder.stop} />
            <Waveform analyser={recorder.analyser} active={recording} />
            <p className="text-center text-slate-700 dark:text-slate-300" aria-live="polite">
              {recorder.state === "requesting" && "Waiting for microphone permission…"}
              {recording && `Recording… say "${word.word}" (${seconds}s). Recording stops automatically when you pause.`}
              {recorder.state === "idle" && phase === "ready" && "Press Record, wait a moment, then say the word."}
            </p>
            {recorder.error && <Alert kind="error" title="Microphone problem">{recorder.error}</Alert>}
            {analyzeError && <Alert kind="error" title="Analysis failed">{analyzeError}</Alert>}
            {phase === "analyzing" && (
              <div className="flex justify-center"><Spinner label="Analysing your pronunciation…" /></div>
            )}
          </div>
        )}
      </Card>

      {phase === "results" && attempt && (
        <Card className="space-y-6">
          <ResultsPanel result={attempt.analysis} feedback={feedback} feedbackLoading={feedbackLoading}
            feedbackError={feedbackError} wordBest={attempt.word_best_score} />
          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-slate-100 pt-5 dark:border-slate-800">
            <div className="flex flex-wrap gap-2">
              {recorder.recording && (
                <Button variant="ghost" onClick={() => reference.playUrl(recorder.recording!.url)}>▶ My recording</Button>
              )}
              <Button variant="ghost" onClick={() => hear(false)}>▶ Example</Button>
            </div>
            <div className="flex flex-wrap gap-3">
              <Button variant="secondary" size="lg" onClick={resetAttempt} aria-keyshortcuts="t">↻ Try again</Button>
              <Button size="lg" onClick={() => void next()} disabled={advancing} aria-keyshortcuts="n">
                {position >= session.total_words ? "Finish session" : "Next word →"}
              </Button>
            </div>
          </div>
        </Card>
      )}

      <p className="hidden text-center text-sm text-slate-500 sm:block dark:text-slate-400">
        Keyboard: <kbd className="rounded border px-1">R</kbd> record/stop · <kbd className="rounded border px-1">H</kbd> hear ·{" "}
        <kbd className="rounded border px-1">T</kbd> try again · <kbd className="rounded border px-1">N</kbd> next word
      </p>
    </div>
  );
}
