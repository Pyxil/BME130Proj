import { useEffect, useState } from "react";
import { Card } from "../components/ui";
import { api } from "../services/endpoints";
import type { SystemStatus } from "../types";

export default function AboutPage() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  useEffect(() => { api.status().then(setStatus).catch(() => undefined); }, []);
  const eng = status?.analysis_engine as { name?: string; model?: string; phoneme_level?: boolean; calibration?: string } | undefined;
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">How your pronunciation is scored</h1>
      <Card className="space-y-3">
        <h2 className="text-xl font-bold">1. Recording check</h2>
        <p>Before scoring, the recording is checked for silence, low volume, distortion, background noise and cut-off words.
          If the recording is not good enough you are asked to record again instead of receiving a misleading score.</p>
        <h2 className="text-xl font-bold">2. Sound-by-sound analysis</h2>
        <p>A speech recognition model trained to recognise individual speech sounds estimates, for every expected sound,
          how likely it is that you produced that sound <em>rather than any other sound or nothing</em>. This catches cases where
          a word is recognisable but a sound is wrong (for example “wabbit” for “rabbit”). American, British and other accepted
          variants are compared and the closest one is used, so a regional accent is not marked as an error.</p>
        <h2 className="text-xl font-bold">3. Supporting measures</h2>
        <p>The overall score combines sound accuracy (60%), acoustic similarity to example recordings measured with dynamic
          time warping (20%), whether all syllables were present (10%) and timing (10%). Slow, careful speech is not penalised.</p>
        <h2 className="text-xl font-bold">4. Feedback</h2>
        <p>Tips are generated only from the problems the analysis actually measured. When an AI model writes the tips,
          every tip must refer to a measured problem; anything else is removed automatically.</p>
      </Card>
      <Card className="space-y-2">
        <h2 className="text-xl font-bold">How accurate is it?</h2>
        <p>We tested the sound scoring on <strong>speechocean762</strong>, a public dataset of 2,500 recordings by non-native
          English speakers that five experts scored sound by sound. On recordings the system never saw during development:</p>
        <ul className="list-disc space-y-1 pl-6">
          <li>Clearly mispronounced sounds were ranked below correct ones <strong>91%</strong> of the time (AUC 0.91).</li>
          <li>Sound scores correlate with the experts' ratings at <strong>r = 0.47</strong>; word scores at <strong>r = 0.48</strong>.</li>
          <li>When a sound scores below 70, experts judged it wrong in about <strong>35%</strong> of cases, which is why tips say “may”.</li>
        </ul>
        <p>That is a useful practice signal, but it is <strong>not</strong> a clinical assessment. The tool has not been clinically
          validated and must not be used to diagnose speech or language conditions.</p>
      </Card>
      <Card className="space-y-2">
        <h2 className="text-xl font-bold">Privacy</h2>
        <p>Recordings are only stored if you switch on “Save my recordings” in Settings. You can delete recordings, your practice
          history or your whole account at any time.</p>
      </Card>
      {status && (
        <Card className="text-sm text-slate-600 dark:text-slate-400">
          <p>System: analysis engine <strong>{eng?.name}</strong>{eng?.model ? ` (${eng.model})` : ""}
            {eng?.phoneme_level === false && " - acoustic baseline only, no sound-level scores"} · feedback mode{" "}
            <strong>{String((status.feedback as { mode?: string }).mode)}</strong> · {status.words} practice words · API contract {status.contract_version}</p>
        </Card>
      )}
    </div>
  );
}
