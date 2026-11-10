import { scoreColor } from "./format";

/** Circular score display (value is always given as text for screen readers). */
export function ScoreRing({ score, size = 148, label = "Pronunciation score" }: { score: number | null; size?: number; label?: string }) {
  const r = size / 2 - 10;
  const c = 2 * Math.PI * r;
  const pct = score === null ? 0 : Math.max(0, Math.min(100, score)) / 100;
  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} aria-hidden="true" className="-rotate-90">
        <circle cx={size / 2} cy={size / 2} r={r} stroke="currentColor" className="text-slate-200 dark:text-slate-800" strokeWidth="12" fill="none" />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none" strokeWidth="12" strokeLinecap="round"
          stroke={scoreColor(score)} strokeDasharray={`${c * pct} ${c}`}
          style={{ transition: "stroke-dasharray 0.8s ease" }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="text-4xl font-bold" aria-label={`${label}: ${score ?? "not available"} out of 100`}>
          {score ?? "—"}
        </span>
        <span className="text-sm text-slate-500 dark:text-slate-400" aria-hidden="true">/ 100</span>
      </div>
    </div>
  );
}
