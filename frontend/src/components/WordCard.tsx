import type { WordSummary } from "../types";
import { Badge } from "./ui";

export function WordCard({ word }: { word: WordSummary }) {
  return (
    <div className="text-center">
      <h1 className="text-5xl font-bold tracking-tight break-words text-slate-900 sm:text-7xl dark:text-white" lang="en">
        {word.word.charAt(0).toUpperCase() + word.word.slice(1)}
      </h1>
      <p className="ipa mt-3 text-2xl text-slate-600 dark:text-slate-300" aria-label={`Pronunciation: ${word.ipa}`}>
        {word.ipa}
      </p>
      <div className="mt-4 flex flex-wrap justify-center gap-2">
        <Badge tone="brand">{word.syllables} syllable{word.syllables === 1 ? "" : "s"}</Badge>
        <Badge>{word.difficulty}</Badge>
        {word.target_sounds.length > 0 && (
          <Badge>
            Focus:&nbsp;<span className="ipa">{word.target_sounds.map((s) => `/${s}/`).join(" ")}</span>
          </Badge>
        )}
      </div>
    </div>
  );
}
