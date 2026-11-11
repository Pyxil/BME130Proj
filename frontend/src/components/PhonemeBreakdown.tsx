import type { PhonemeScore } from "../types";
import { STATUS_STYLE as STATUS } from "./format";

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
