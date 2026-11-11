/** Shared display helpers (kept out of component files so React Fast Refresh works). */

export const RATING_LABEL: Record<string, string> = {
  mastered: "Mastered",
  satisfactory: "Good - keep practising",
  needs_practice: "Needs more practice",
};

export function ratingTone(rating?: string | null): "good" | "fair" | "poor" | "slate" {
  return rating === "mastered" ? "good" : rating === "satisfactory" ? "fair" : rating === "needs_practice" ? "poor" : "slate";
}

/** Chip styles for sound / word-part statuses. */
export const STATUS_STYLE = {
  good: { label: "clear", cls: "bg-emerald-50 ring-emerald-300 text-emerald-900 dark:bg-emerald-950 dark:ring-emerald-800 dark:text-emerald-100", bar: "bg-good" },
  fair: { label: "could be clearer", cls: "bg-amber-50 ring-amber-300 text-amber-950 dark:bg-amber-950 dark:ring-amber-800 dark:text-amber-100", bar: "bg-fair" },
  poor: { label: "needs work", cls: "bg-rose-50 ring-rose-300 text-rose-900 dark:bg-rose-950 dark:ring-rose-800 dark:text-rose-100", bar: "bg-poor" },
  missing: { label: "may be missing", cls: "bg-slate-100 ring-slate-300 text-slate-800 dark:bg-slate-800 dark:ring-slate-600 dark:text-slate-100", bar: "bg-slate-400" },
  unscored: { label: "not scored", cls: "bg-slate-50 ring-slate-200 text-slate-600", bar: "bg-slate-300" },
} as const;

/** "the first syllable" -> "Syllable 1", "the start of the word" -> "Start". */
export function partShortLabel(label: string): string {
  const ord = ["first", "second", "third", "fourth", "fifth", "sixth"];
  const m = /^the (\w+) syllable$/.exec(label);
  if (m) return `Syllable ${ord.indexOf(m[1]) + 1 || m[1]}`;
  return ({ "the start of the word": "Start", "the vowel": "Vowel", "the end of the word": "End" } as Record<string, string>)[label] ?? label;
}

export function scoreColor(score: number | null | undefined): string {
  if (score === null || score === undefined) return "#94a3b8";
  return score >= 90 ? "#047857" : score >= 70 ? "#b45309" : "#be123c";
}
