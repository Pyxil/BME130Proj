import { useEffect, useState } from "react";
import { RATING_LABEL, ratingTone } from "../components/format";
import { Link, useNavigate } from "react-router-dom";
import {
  Area, Bar, BarChart, CartesianGrid, Cell, ComposedChart, LabelList, Line, ReferenceLine, ResponsiveContainer,
  Tooltip, XAxis, YAxis,
} from "recharts";
import {Alert, Badge, Button, Card, Spinner} from "../components/ui";
import { ApiError } from "../services/api";
import { api } from "../services/endpoints";
import type { ProgressOut } from "../types";

const AXIS = { stroke: "var(--chart-grid)", tick: { fill: "var(--chart-axis)", fontSize: 13 } };
const NEEDS_WORK_BELOW = 85;

function StatTile({ label, value, sub }: { label: string; value: string; sub?: React.ReactNode }) {
  return (
    <Card as="div" className="p-4 sm:p-5">
      <p className="text-sm font-bold text-slate-600 dark:text-slate-400">{label}</p>
      <p className="mt-1 text-4xl font-semibold tabular-nums">{value}</p>
      {sub && <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">{sub}</p>}
    </Card>
  );
}

function ChartTooltip({ active, payload, label, unit }: {
  active?: boolean; payload?: { value: number; payload: Record<string, unknown> }[]; label?: string | number; unit: string;
}) {
  if (!active || !payload?.length) return null;
  const p = payload[0];
  return (
    <div className="rounded-lg bg-white px-3 py-2 text-sm shadow-lg ring-1 ring-slate-200 dark:bg-slate-900 dark:ring-slate-700">
      <p className="font-bold">{String(label)}</p>
      <p>{p.value} {unit}{"attempts" in p.payload ? ` · ${String(p.payload.attempts)} attempts` : ""}</p>
    </div>
  );
}

export default function DashboardPage() {
  const navigate = useNavigate();
  const [data, setData] = useState<ProgressOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.progress().then(setData).catch((e: ApiError) => setError(e.message));
  }, []);
  if (error) return <Alert kind="error">{error}</Alert>;
  if (!data) return <Spinner label="Loading your progress…" />;

  const practiceMissed = async () => {
    const s = await api.createSession({ mode: "missed", size: 10 });
    navigate(`/practice/${s.id}`);
  };
  const improvement = data.improvement;
  const sounds = data.phoneme_stats.slice(0, 12).map((s) => ({ ...s, label: `/${s.phoneme}/` }));
  const trend = data.score_over_time.map((p) => ({ ...p, date: new Date(p.date + "T00:00:00").toLocaleDateString(undefined, { month: "short", day: "numeric" }) }));

  if (data.total_attempts === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-3xl font-bold">Your progress</h1>
        <Alert title="Nothing to show yet">Practise a few words and your progress will appear here. <Link className="font-bold underline" to="/practice">Start practising</Link></Alert>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">Your progress</h1>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Average accuracy" value={data.average_score != null ? `${Math.round(data.average_score)}` : "–"} sub="out of 100, scored attempts" />
        <StatTile label="Words completed" value={String(data.words_completed)} sub={`${data.words_mastered} mastered`} />
        <StatTile label="Practice sessions" value={String(data.total_sessions)} sub={`${data.total_attempts} attempts`} />
        <StatTile label="Improvement" value={improvement == null ? "–" : `${improvement > 0 ? "▲ +" : improvement < 0 ? "▼ " : ""}${improvement}`}
          sub={improvement == null ? "needs 6+ scored attempts" : "last 10 vs first 10 attempts"} />
      </div>

      <Card aria-labelledby="trend-h">
        <h2 id="trend-h" className="text-xl font-bold">Pronunciation score over time</h2>
        <p className="text-sm text-slate-600 dark:text-slate-400">Daily average of scored attempts. Lines mark the mastery (90) and satisfactory (70) levels.</p>
        <div className="mt-4 h-72" role="img" aria-label={`Line chart of daily average scores across ${trend.length} days`}>
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={trend} margin={{ top: 10, right: 16, bottom: 0, left: -12 }}>
              <CartesianGrid vertical={false} stroke="var(--chart-grid)" strokeWidth={1} />
              <XAxis dataKey="date" {...AXIS} tickLine={false} />
              <YAxis domain={[0, 100]} ticks={[0, 25, 50, 70, 90, 100]} {...AXIS} tickLine={false} axisLine={false} />
              <ReferenceLine y={90} stroke="var(--chart-axis)" strokeOpacity={0.5} label={{ value: "Mastered", position: "insideTopRight", fill: "var(--chart-axis)", fontSize: 12 }} />
              <ReferenceLine y={70} stroke="var(--chart-axis)" strokeOpacity={0.35} label={{ value: "Satisfactory", position: "insideBottomRight", fill: "var(--chart-axis)", fontSize: 12 }} />
              <Tooltip content={<ChartTooltip unit="/ 100" />} cursor={{ stroke: "var(--chart-axis)", strokeWidth: 1 }} />
              <Area type="monotone" dataKey="average_score" fill="var(--chart-accent)" fillOpacity={0.1} stroke="none" isAnimationActive={false} />
              <Line type="monotone" dataKey="average_score" stroke="var(--chart-accent)" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"
                dot={{ r: 4, fill: "var(--chart-accent)", stroke: "var(--chart-surface)", strokeWidth: 2 }}
                activeDot={{ r: 6, stroke: "var(--chart-surface)", strokeWidth: 2 }} isAnimationActive={false} />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
        <details className="mt-3">
          <summary className="cursor-pointer font-bold">Show as table</summary>
          <table className="mt-2 text-left text-sm">
            <thead><tr><th className="pr-6">Day</th><th className="pr-6">Average score</th><th>Attempts</th></tr></thead>
            <tbody>{data.score_over_time.map((p) => <tr key={p.date}><td className="pr-6">{p.date}</td><td className="pr-6">{p.average_score}</td><td>{p.attempts}</td></tr>)}</tbody>
          </table>
        </details>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card aria-labelledby="sounds-h">
          <h2 id="sounds-h" className="text-xl font-bold">Sounds by accuracy</h2>
          <p className="text-sm text-slate-600 dark:text-slate-400">Your weakest sounds first. Highlighted bars are below {NEEDS_WORK_BELOW} and worth practising.</p>
          <div className="mt-4" style={{ height: Math.max(160, sounds.length * 30 + 30) }} role="img"
            aria-label={`Bar chart of average score per sound for ${sounds.length} sounds`}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={sounds} layout="vertical" margin={{ top: 0, right: 40, bottom: 0, left: 0 }} barCategoryGap={2}>
                <CartesianGrid horizontal={false} stroke="var(--chart-grid)" />
                <XAxis type="number" domain={[0, 100]} {...AXIS} tickLine={false} />
                <YAxis type="category" dataKey="label" width={52} {...AXIS} tickLine={false} axisLine={false} tick={{ fill: "var(--chart-axis)", fontSize: 15 }} />
                <Tooltip content={<ChartTooltip unit="average score" />} cursor={{ fill: "var(--chart-grid)", opacity: 0.5 }} />
                <Bar dataKey="average_score" barSize={18} radius={[0, 4, 4, 0]} isAnimationActive={false}>
                  {sounds.map((s) => <Cell key={s.phoneme} fill={s.average_score < NEEDS_WORK_BELOW ? "var(--chart-accent)" : "var(--chart-muted)"} />)}
                  <LabelList dataKey="average_score" position="right" fill="var(--chart-axis)" fontSize={12}
                    formatter={(v: unknown) => (typeof v === "number" && v < NEEDS_WORK_BELOW ? Math.round(v) : "")} />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <details className="mt-3">
            <summary className="cursor-pointer font-bold">Show all sounds as a table</summary>
            <table className="mt-2 text-left text-sm">
              <thead><tr><th className="pr-6">Sound</th><th className="pr-6">Average</th><th className="pr-6">Attempts</th><th>Needs work</th></tr></thead>
              <tbody>{data.phoneme_stats.map((s) => <tr key={s.phoneme}><td className="ipa pr-6">/{s.phoneme}/</td><td className="pr-6">{s.average_score}</td><td className="pr-6">{s.attempts}</td><td>{Math.round(s.poor_rate * 100)}%</td></tr>)}</tbody>
            </table>
          </details>
        </Card>

        <Card aria-labelledby="mis-h">
          <h2 id="mis-h" className="text-xl font-bold">Most frequently mispronounced sounds</h2>
          {data.most_mispronounced.length === 0 ? <p className="mt-2">No sound has been flagged yet. 👏</p> : (
            <ul className="mt-3 space-y-3">
              {data.most_mispronounced.map((s) => (
                <li key={s.phoneme} className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-slate-50 p-3 dark:bg-slate-950">
                  <span className="ipa text-2xl font-semibold">/{s.phoneme}/</span>
                  <span className="text-sm">
                    flagged in {s.poor_count} of {s.attempts} attempts ({Math.round(s.poor_rate * 100)}%)
                    {s.common_substitution && <> · often sounded like <span className="ipa font-bold">/{s.common_substitution}/</span></>}
                  </span>
                  <Button variant="secondary" onClick={() => void api.createSession({ mode: "phoneme", phoneme: s.phoneme, size: 8 }).then((x) => navigate(`/practice/${x.id}`))}>
                    Practise /{s.phoneme}/
                  </Button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card aria-labelledby="needs-h">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 id="needs-h" className="text-xl font-bold">Words that need more practice</h2>
            {data.words_needing_practice.length > 0 && <Button onClick={() => void practiceMissed()}>Practise these</Button>}
          </div>
          {data.words_needing_practice.length === 0 ? <p className="mt-2">Every word you've tried is mastered. 🎉</p> : (
            <table className="mt-3 w-full text-left">
              <thead className="text-sm text-slate-600 dark:text-slate-400"><tr><th className="py-1">Word</th><th>Last</th><th>Best</th><th>Tries</th></tr></thead>
              <tbody>
                {data.words_needing_practice.map((w) => (
                  <tr key={w.word_id} className="border-t border-slate-100 dark:border-slate-800">
                    <td className="py-2 font-bold">{w.word}</td><td>{w.last_score ?? "–"}</td><td>{w.best_score ?? "–"}</td><td>{w.attempts}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Card>
        <Card aria-labelledby="recent-h">
          <h2 id="recent-h" className="text-xl font-bold">Recent practice sessions</h2>
          <ul className="mt-3 divide-y divide-slate-100 dark:divide-slate-800">
            {data.recent_sessions.map((s) => (
              <li key={s.id} className="flex flex-wrap items-center justify-between gap-2 py-2">
                <span>
                  <span className="font-bold capitalize">{s.mode}</span>{" "}
                  <span className="text-sm text-slate-600 dark:text-slate-400">{new Date(s.started_at).toLocaleDateString()}</span>
                </span>
                <span className="flex items-center gap-2 text-sm">
                  {s.words_attempted}/{s.total_words} words · avg {s.average_score ?? "–"}
                  <Badge tone={s.status === "completed" ? "good" : "slate"}>{s.status}</Badge>
                </span>
              </li>
            ))}
          </ul>
          <h3 className="mt-4 font-bold">Latest attempts</h3>
          <ul className="mt-1 space-y-1">
            {data.recent_attempts.slice(0, 5).map((a) => (
              <li key={a.id} className="flex justify-between gap-2">
                <Link to={`/history/${a.id}`} className="underline">{a.word}</Link>
                <span>{a.overall_score ?? "–"} {a.rating && <Badge tone={ratingTone(a.rating)}>{RATING_LABEL[a.rating]}</Badge>}</span>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </div>
  );
}
