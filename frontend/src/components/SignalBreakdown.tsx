import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { SignalAnalysis, SignalPart } from "../types";
import { STATUS_STYLE, partShortLabel } from "./format";

const AXIS = { stroke: "var(--chart-grid)", tick: { fill: "var(--chart-axis)", fontSize: 13 } };

/** One chip per part of the word (syllable, or start / vowel / end), coloured by how well it matched. */
function PartChips({ parts }: { parts: SignalPart[] }) {
  return (
    <ol className="flex flex-wrap gap-2" aria-label="How closely each part of the word matched the example">
      {parts.map((p) => {
        const s = STATUS_STYLE[p.status] ?? STATUS_STYLE.unscored;
        return (
          <li key={p.index} className={`min-w-24 rounded-xl px-3 py-2 ring-1 ${s.cls}`}>
            <div className="text-xs font-semibold uppercase tracking-wide opacity-80">{partShortLabel(p.label)}</div>
            <div className="ipa text-2xl font-semibold leading-tight">/{p.phonemes.join("")}/</div>
            <div className="text-sm font-bold">{p.similarity}<span className="sr-only"> out of 100, {s.label}</span></div>
            <div className="mt-1 h-1.5 w-full rounded-full bg-black/10" aria-hidden="true">
              <div className={`h-1.5 rounded-full ${s.bar}`} style={{ width: `${p.similarity}%` }} />
            </div>
          </li>
        );
      })}
    </ol>
  );
}

type Point = { t: number; you: number; example: number };

function partAt(t: number, edges: number[], parts: SignalPart[]): string {
  const k = edges.filter((e) => t >= e).length;
  return parts[k] ? partShortLabel(parts[k].label) : "";
}

function CurveTooltip({ active, payload, edges, parts }: {
  active?: boolean; payload?: { payload: Point }[]; edges: number[]; parts: SignalPart[];
}) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="rounded-lg bg-white px-3 py-2 text-sm shadow-lg ring-1 ring-slate-200 dark:bg-slate-900 dark:ring-slate-700">
      <p className="font-bold">{partAt(p.t, edges, parts)} · {Math.round(p.t * 100)}% through the word</p>
      <p>You: {p.you} dB</p>
      <p>Example: {p.example} dB</p>
    </div>
  );
}

/** Direct label at the end of a line (text in axis ink, offset so the two labels never collide). */
function EndLabel({ x, y, index, count, text, dy }: {
  x?: number; y?: number; index?: number; count: number; text: string; dy: number;
}) {
  if (index !== count - 1 || x == null || y == null) return null;
  return <text x={x + 8} y={y} dy={dy} fontSize={12} fill="var(--chart-axis)">{text}</text>;
}

function LineSwatch({ dashed, color }: { dashed?: boolean; color: string }) {
  return (
    <svg width="28" height="10" aria-hidden="true" className="inline-block align-middle">
      <line x1="2" y1="5" x2="26" y2="5" stroke={color} strokeWidth="2" strokeLinecap="round" strokeDasharray={dashed ? "6 4" : undefined} />
    </svg>
  );
}

function LoudnessChart({ signal }: { signal: SignalAnalysis }) {
  const c = signal.curves;
  if (!c || c.t.length < 2) return null;
  const parts = signal.parts ?? [];
  const edges = c.part_edges ?? [];
  const data: Point[] = c.t.map((t, k) => ({ t, you: c.user_db[k], example: c.standard_db[k] }));
  const bounds = [0, ...edges, 1];
  const centers = parts.map((_, k) => (bounds[k] + bounds[k + 1]) / 2);
  const tickLabel = (v: number) => {
    const k = centers.findIndex((x) => Math.abs(x - v) < 1e-9);
    return k >= 0 ? partShortLabel(parts[k].label) : "";
  };
  const rows = data.filter((_, k) => k % Math.max(1, Math.round(data.length / 12)) === 0);
  return (
    <div>
      <div className="flex flex-wrap gap-4 text-sm text-slate-700 dark:text-slate-300">
        <span><LineSwatch color="var(--chart-you)" /> Your recording</span>
        <span><LineSwatch dashed color="var(--chart-standard)" /> Example (standard)</span>
      </div>
      <div className="mt-2 h-56" role="img"
        aria-label="Line chart of loudness over time for your recording and the example, lined up part by part">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 10, right: 72, bottom: 4, left: 0 }}>
            <CartesianGrid vertical={false} stroke="var(--chart-grid)" />
            <XAxis dataKey="t" type="number" domain={[0, 1]} ticks={centers} tickFormatter={tickLabel} interval={0}
              {...AXIS} tickLine={false} />
            <YAxis domain={[-60, 0]} ticks={[-60, -40, -20, 0]} unit=" dB" width={60} {...AXIS} tickLine={false} axisLine={false} />
            {edges.map((e) => <ReferenceLine key={e} x={e} stroke="var(--chart-axis)" strokeOpacity={0.35} strokeDasharray="3 3" />)}
            <Tooltip content={<CurveTooltip edges={edges} parts={parts} />} cursor={{ stroke: "var(--chart-axis)", strokeWidth: 1 }} />
            <Line type="monotone" dataKey="example" name="Example" stroke="var(--chart-standard)" strokeWidth={2}
              strokeDasharray="6 4" strokeLinecap="round" dot={false} isAnimationActive={false}
              activeDot={{ r: 4, stroke: "var(--chart-surface)", strokeWidth: 2 }}
              label={<EndLabel count={data.length} text="Example" dy={14} />} />
            <Line type="monotone" dataKey="you" name="You" stroke="var(--chart-you)" strokeWidth={2} strokeLinecap="round"
              dot={false} isAnimationActive={false} activeDot={{ r: 4, stroke: "var(--chart-surface)", strokeWidth: 2 }}
              label={<EndLabel count={data.length} text="You" dy={-6} />} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <details className="mt-2 text-sm">
        <summary className="cursor-pointer text-slate-600 dark:text-slate-400">Show the numbers</summary>
        <table className="mt-2 w-full max-w-md text-left tabular-nums">
          <thead><tr className="text-slate-500"><th className="py-1">Position</th><th>Part</th><th>You</th><th>Example</th></tr></thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.t} className="border-t border-slate-100 dark:border-slate-800">
                <td className="py-1">{Math.round(p.t * 100)}%</td><td>{partAt(p.t, edges, parts)}</td>
                <td>{p.you} dB</td><td>{p.example} dB</td>
              </tr>
            ))}
          </tbody>
        </table>
      </details>
    </div>
  );
}

/** Results of the signals-and-systems comparison: parts, loudness curves, mistakes checked, closest words. */
export function SignalBreakdown({ signal, word }: { signal: SignalAnalysis; word: string }) {
  const parts = signal.parts ?? [];
  const mistakes = signal.mistakes_checked ?? [];
  const closest = signal.closest_words ?? [];
  return (
    <section aria-labelledby="parts-h" className="space-y-4">
      <div>
        <h3 id="parts-h" className="mb-2 text-lg font-bold">Part by part</h3>
        <PartChips parts={parts} />
      </div>
      <div className="rounded-2xl bg-white p-4 ring-1 ring-slate-200 dark:bg-slate-900 dark:ring-slate-800">
        <h4 className="font-bold">Your recording vs. the example</h4>
        <p className="mb-2 text-sm text-slate-600 dark:text-slate-400">
          Loudness over time, lined up with dynamic time warping, so speaking faster or slower does not count as a difference.
        </p>
        <LoudnessChart signal={signal} />
        <div className="mt-4 grid gap-4 text-sm sm:grid-cols-2">
          {mistakes.length > 0 && (
            <div>
              <h5 className="font-bold">Common mistakes checked</h5>
              <p className="text-slate-600 dark:text-slate-400">Compared with generated recordings of each mistake (minimal pairs).</p>
              <ul className="mt-1 space-y-0.5">
                {mistakes.map((m) => (
                  <li key={`${m.kind}-${m.position}-${m.realized_as ?? ""}`}>
                    <span className="ipa">{m.description}</span>: <strong>{Math.round(m.probability * 100)}%</strong> likely
                  </li>
                ))}
              </ul>
            </div>
          )}
          {closest.length > 0 && (
            <div>
              <h5 className="font-bold">Closest words</h5>
              <p className="text-slate-600 dark:text-slate-400">
                {signal.target_rank === 1
                  ? `Of ${signal.words_compared} practice words, the recording matched "${word}" best.`
                  : signal.target_rank
                    ? `It matched "${closest[0].word}" more closely than "${word}" (rank ${signal.target_rank} of ${signal.words_compared}).`
                    : `Compared with ${signal.words_compared} practice words so far.`}
              </p>
              <ol className="mt-1 list-decimal pl-5">
                {closest.map((w) => <li key={w.word}>{w.word} <span className="text-slate-500">({w.similarity})</span></li>)}
              </ol>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
