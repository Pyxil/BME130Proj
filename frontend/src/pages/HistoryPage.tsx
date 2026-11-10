import { useEffect, useState } from "react";
import { RATING_LABEL, ratingTone } from "../components/format";
import { Link } from "react-router-dom";
import {Alert, Badge, Card, Spinner} from "../components/ui";
import { ApiError } from "../services/api";
import { api } from "../services/endpoints";
import type { AttemptList } from "../types";

export default function HistoryPage() {
  const [data, setData] = useState<AttemptList | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.attempts({ limit: 100 }).then(setData).catch((e: ApiError) => setError(e.message));
  }, []);
  if (error) return <Alert kind="error">{error}</Alert>;
  if (!data) return <Spinner label="Loading history…" />;
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Your attempts</h1>
      {data.items.length === 0 ? (
        <Alert>No attempts yet. <Link className="font-bold underline" to="/practice">Start practising</Link>.</Alert>
      ) : (
        <Card className="overflow-x-auto p-0 sm:p-0">
          <table className="w-full text-left">
            <caption className="sr-only">Previous attempts, newest first</caption>
            <thead className="bg-slate-50 text-sm text-slate-600 dark:bg-slate-950 dark:text-slate-400">
              <tr>
                <th scope="col" className="px-4 py-3">When</th>
                <th scope="col" className="px-4 py-3">Word</th>
                <th scope="col" className="px-4 py-3">Score</th>
                <th scope="col" className="px-4 py-3">Result</th>
                <th scope="col" className="px-4 py-3"><span className="sr-only">Details</span></th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((a) => (
                <tr key={a.id} className="border-t border-slate-100 dark:border-slate-800">
                  <td className="px-4 py-3 text-sm">{new Date(a.created_at).toLocaleString()}</td>
                  <td className="px-4 py-3 text-lg font-bold">{a.word} <span className="text-sm font-normal text-slate-500">#{a.attempt_number}</span></td>
                  <td className="px-4 py-3 text-lg">{a.overall_score ?? "–"}</td>
                  <td className="px-4 py-3">
                    {a.status === "assessed" && a.rating ? <Badge tone={ratingTone(a.rating)}>{RATING_LABEL[a.rating]}</Badge>
                      : <Badge>{a.status === "retry_required" ? "Re-record needed" : "Inconclusive"}</Badge>}
                    {a.has_recording && <span className="ml-2" title="Recording stored">🎧</span>}
                  </td>
                  <td className="px-4 py-3"><Link className="font-bold text-brand-800 underline dark:text-brand-200" to={`/history/${a.id}`}>Details</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
