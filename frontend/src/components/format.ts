/** Shared display helpers (kept out of component files so React Fast Refresh works). */

export const RATING_LABEL: Record<string, string> = {
  mastered: "Mastered",
  satisfactory: "Good - keep practising",
  needs_practice: "Needs more practice",
};

export function ratingTone(rating?: string | null): "good" | "fair" | "poor" | "slate" {
  return rating === "mastered" ? "good" : rating === "satisfactory" ? "fair" : rating === "needs_practice" ? "poor" : "slate";
}

export function scoreColor(score: number | null | undefined): string {
  if (score === null || score === undefined) return "#94a3b8";
  return score >= 90 ? "#047857" : score >= 70 ? "#b45309" : "#be123c";
}
