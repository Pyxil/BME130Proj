import type { PhonemeScore } from "../types";

const STATUS = {
  good: { label: "clear", cls: "bg-emerald-50 ring-emerald-300 text-emerald-900 dark:bg-emerald-950 dark:ring-emerald-800 dark:text-emerald-100", bar: "bg-good" },
  fair: { label: "could be clearer", cls: "bg-amber-50 ring-amber-300 text-amber-950 dark:bg-amber-950 dark:ring-amber-800 dark:text-amber-100", bar: "bg-fair" },
  poor: { label: "needs work", cls: "bg-rose-50 ring-rose-300 text-rose-900 dark:bg-rose-950 dark:ring-rose-800 dark:text-rose-100", bar: "bg-poor" },
  missing: { label: "may be missing", cls: "bg-slate-100 ring-slate-300 text-slate-800 dark:bg-slate-800 dark:ring-slate-600 dark:text-slate-100", bar: "bg-slate-400" },
  unscored: { label: "not scored", cls: "bg-slate-50 ring-slate-200 text-slate-600", bar: "bg-slate-300" },
} as const;

/** One chip per expected sound, coloured by status, with the score and likely substitute. */
export function PhonemeBreakdown({ phonemes }: { phonemes: PhonemeScore[] }) {
  return (
    <ol className="flex flex-wrap gap-2" aria-label="Score for each sound">
      {phonemes.map((p) => {
        const s = STATUS[p.status] ?? STATUS.unscored;
        return (
          <li key={p.index} className={`min-w-20 rounded-xl px-3 py-2 ring-1 ${s.cls}`}>
            <div className="ipa text-2xl font-semibold leading-tight">/{p.phoneme}/</div>
            <div className="text-sm font-bold">{p.score ?? "–"}<span className="sr-only"> out of 100, {s.label}</span></div>
            <div className="mt-1 h-1.5 w-full rounded-full bg-black/10" aria-hidden="true">
              <div className={`h-1.5 rounded-full ${s.bar}`} style={{ width: `${p.score ?? 0}%` }} />
            </div>
            {p.likely_realization && (
              <div className="mt-1 text-xs">
                like <span className="ipa font-semibold">/{p.likely_realization}/</span>?
              </div>
            )}
            {p.accepted_variant && !p.likely_realization && (
              <div className="mt-1 text-xs opacity-80" title="An accepted accent or allophone variant was recognised">
                ✓ variant <span className="ipa">/{p.accepted_variant}/</span>
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}
