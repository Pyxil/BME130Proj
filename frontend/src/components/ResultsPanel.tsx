import type { AnalysisResult, FeedbackResponse } from "../types";
import { RATING_LABEL, ratingTone } from "./format";
import { FeedbackCard } from "./FeedbackCard";
import { PhonemeBreakdown } from "./PhonemeBreakdown";
import { ScoreRing } from "./ScoreRing";
import {Alert, Badge} from "./ui";

const COMPONENT_LABEL: Record<string, string> = {
  phoneme_accuracy: "Sounds (phoneme accuracy)",
  acoustic_similarity: "Similarity to example",
  syllable_completeness: "All syllables present",
  temporal: "Timing and pace",
};

export function ResultsPanel({ result, feedback, feedbackLoading, feedbackError, wordBest }: {
  result: AnalysisResult; feedback: FeedbackResponse | null; feedbackLoading: boolean; feedbackError?: string | null; wordBest?: number | null;
}) {
  if (result.status !== "assessed") {
    return (
      <Alert kind="warning" title={result.status === "inconclusive" ? "We couldn't assess this attempt reliably" : "Please record again"}>
        <p>{result.retry_reason}</p>
        {(result.quality.issues ?? []).filter((i) => !i.blocking).map((i) => <p key={i.code}>{i.message}</p>)}
      </Alert>
    );
  }
  const issues = result.identified_issues ?? [];
  const strengths = result.strengths ?? [];
  return (
    <div className="space-y-6" aria-live="polite">
      <div className="flex flex-col items-center gap-6 sm:flex-row sm:items-center">
        <ScoreRing score={result.overall_score ?? null} />
        <div className="flex-1 space-y-2 text-center sm:text-left">
          <h2 className="text-2xl font-bold">Pronunciation score: {result.overall_score}/100</h2>
          <div className="flex flex-wrap justify-center gap-2 sm:justify-start">
            {result.rating && <Badge tone={ratingTone(result.rating)}>{RATING_LABEL[result.rating]}</Badge>}
            <Badge tone={result.word_recognized ? "good" : "slate"}>
              {result.word_recognized ? "Word recognised ✓" : `Heard as "${result.recognized_word ?? "?"}"`}
            </Badge>
            {result.phonetically_accurate && <Badge tone="good">All sounds clear</Badge>}
            <Badge tone={result.confidence_label === "high" ? "brand" : "slate"}>
              {result.confidence_label === "high" ? "High confidence" : result.confidence_label === "medium" ? "Medium confidence" : "Low confidence"}
            </Badge>
          </div>
          {result.matched_variant && (
            <p className="text-sm text-slate-600 dark:text-slate-400">
              Compared with the <strong>{result.matched_variant.accent}</strong> pronunciation <span className="ipa">{result.matched_variant.ipa}</span>
              {wordBest != null && <> · your best on this word: <strong>{wordBest}</strong></>}
            </p>
          )}
        </div>
      </div>

      {result.phoneme_scores && (
        <section aria-labelledby="sounds-h">
          <h3 id="sounds-h" className="mb-2 text-lg font-bold">Sound by sound</h3>
          <PhonemeBreakdown phonemes={result.phoneme_scores} />
        </section>
      )}

      <div className="grid gap-4 md:grid-cols-2">
        <section aria-labelledby="improve-h" className="rounded-2xl bg-slate-50 p-5 ring-1 ring-slate-200 dark:bg-slate-950 dark:ring-slate-800">
          <h3 id="improve-h" className="text-lg font-bold">Areas to improve</h3>
          {issues.length === 0 ? (
            <p className="mt-2">No problems were detected in this attempt. 🎉</p>
          ) : (
            <ul className="mt-2 list-disc space-y-1 pl-5">
              {issues.map((i) => <li key={i.id}>{i.message}</li>)}
            </ul>
          )}
          {strengths.length > 0 && (
            <>
              <h4 className="mt-4 font-bold text-good">What went well</h4>
              <ul className="mt-1 list-disc space-y-1 pl-5">
                {strengths.map((s) => <li key={s.id}>{s.message}</li>)}
              </ul>
            </>
          )}
        </section>
        <FeedbackCard feedback={feedback} loading={feedbackLoading} error={feedbackError} />
      </div>

      <details className="rounded-2xl bg-white p-4 ring-1 ring-slate-200 dark:bg-slate-900 dark:ring-slate-800">
        <summary className="cursor-pointer font-bold">How this score was calculated</summary>
        <table className="mt-3 w-full text-left text-sm">
          <thead>
            <tr className="text-slate-500"><th className="py-1">Component</th><th>Score</th><th>Weight</th></tr>
          </thead>
          <tbody>
            {(result.components ?? []).map((c) => (
              <tr key={c.name} className="border-t border-slate-100 dark:border-slate-800">
                <td className="py-1.5">{COMPONENT_LABEL[c.name] ?? c.name}</td>
                <td>{c.available && c.score != null ? Math.round(c.score) : "not available"}</td>
                <td>{Math.round(c.weight * 100)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="mt-3 text-sm text-slate-600 dark:text-slate-400">
          Engine: {result.engine.name}{result.engine.model ? ` (${result.engine.model})` : ""} ·{" "}
          {result.engine.phoneme_level ? "phoneme-level scoring" : "acoustic-only baseline (no phoneme scores)"} ·
          analysed in {(result.processing_ms / 1000).toFixed(1)} s
        </p>
        <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">{result.disclaimer}</p>
      </details>
    </div>
  );
}
