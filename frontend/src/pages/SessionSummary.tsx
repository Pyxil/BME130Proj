import { useState } from "react";
import { RATING_LABEL, ratingTone } from "../components/format";
import { useNavigate } from "react-router-dom";
import { ScoreRing } from "../components/ScoreRing";
import {Badge, Button, Card} from "../components/ui";
import { api } from "../services/endpoints";
import type { SessionOut } from "../types";

export function SessionSummaryView({ session, onNew }: { session: SessionOut; onNew: () => void }) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const practiseMissed = async () => {
    setBusy(true);
    try {
      const s = await api.createSession({ mode: "missed", size: 10 });
      navigate(`/practice/${s.id}`);
    } finally {
      setBusy(false);
    }
  };
  const mastered = session.words.filter((w) => w.status === "mastered").length;
  return (
    <Card className="space-y-6">
      <div className="flex flex-col items-center gap-4 text-center">
        <h1 className="text-3xl font-bold">Session complete 🎉</h1>
        <ScoreRing score={session.average_score != null ? Math.round(session.average_score) : null} label="Average best score" />
        <p className="text-lg">
          You practised {session.words_attempted} of {session.total_words} words and mastered {mastered}.
        </p>
      </div>
      <ul className="divide-y divide-slate-100 dark:divide-slate-800">
        {session.words.map((w) => (
          <li key={w.position} className="flex items-center justify-between gap-3 py-3">
            <span className="text-lg font-bold">{w.word.word}</span>
            <span className="flex items-center gap-3">
              <span>{w.best_score ?? "–"}</span>
              {w.last_rating ? <Badge tone={ratingTone(w.last_rating)}>{RATING_LABEL[w.last_rating]}</Badge> : <Badge>skipped</Badge>}
            </span>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap justify-center gap-3">
        <Button size="lg" onClick={onNew}>Start a new session</Button>
        <Button size="lg" variant="secondary" onClick={() => void practiseMissed()} disabled={busy}>Practise words to improve</Button>
        <Button size="lg" variant="ghost" onClick={() => navigate("/dashboard")}>View progress</Button>
      </div>
    </Card>
  );
}
