import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ResultsPanel } from "../components/ResultsPanel";
import { Alert, Button, Card, Spinner } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { useReferenceAudio } from "../hooks/useReferenceAudio";
import { ApiError } from "../services/api";
import { api } from "../services/endpoints";
import type { AttemptOut } from "../types";

export default function AttemptDetailPage() {
  const { attemptId = "" } = useParams();
  const { user } = useAuth();
  const [attempt, setAttempt] = useState<AttemptOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [recUrl, setRecUrl] = useState<string | null>(null);
  const reference = useReferenceAudio();

  useEffect(() => {
    api.attempt(attemptId).then(setAttempt).catch((e: ApiError) => setError(e.message));
  }, [attemptId]);

  useEffect(() => {
    if (!attempt?.has_recording) return;
    let url: string | null = null;
    api.recordingResponse(attempt.attempt_id)
      .then((r) => r.blob())
      .then((b) => { url = URL.createObjectURL(b); setRecUrl(url); })
      .catch(() => undefined);
    return () => { if (url) URL.revokeObjectURL(url); };
  }, [attempt]);

  const removeRecording = async () => {
    if (!attempt) return;
    await api.deleteRecording(attempt.attempt_id);
    setRecUrl(null);
    setAttempt({ ...attempt, has_recording: false });
  };

  if (error) return <Alert kind="error">{error}</Alert>;
  if (!attempt) return <Spinner label="Loading attempt…" />;
  const a = attempt.analysis;
  return (
    <div className="space-y-6">
      <Link to="/history" className="font-bold text-brand-800 underline dark:text-brand-200">← Back to history</Link>
      <h1 className="text-3xl font-bold">“{a.word}” · attempt {attempt.attempt_number}</h1>
      <p className="text-slate-600 dark:text-slate-400">{new Date(attempt.created_at).toLocaleString()}</p>
      <Card className="space-y-4">
        <div className="flex flex-wrap gap-3">
          <Button variant="secondary" onClick={() => reference.play(attempt.word_id, a.word, user?.preferred_accent ?? "us")}>🔊 Example</Button>
          {recUrl && <Button variant="secondary" onClick={() => reference.playUrl(recUrl)}>▶ My recording</Button>}
          {attempt.has_recording && <Button variant="ghost" onClick={() => void removeRecording()}>Delete this recording</Button>}
        </div>
        <ResultsPanel result={a} feedback={attempt.feedback ?? null} feedbackLoading={false} />
      </Card>
    </div>
  );
}
