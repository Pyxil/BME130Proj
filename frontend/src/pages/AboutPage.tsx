import { useEffect, useState } from "react";
import { Card } from "../components/ui";
import { api } from "../services/endpoints";
import type { SystemStatus } from "../types";

type Engine = { name?: string; model?: string; phoneme_level?: boolean; calibration?: string; validation?: Validation | null };
type Validation = {
  words?: number; correct_recordings?: number; error_recordings?: number;
  identification_top1?: number; identification_top3?: number;
  auc_correct_vs_covered?: number; auc_correct_vs_uncovered?: number;
  mistake_named_covered?: number; mistake_false_alarm_correct?: number;
  ratings_correct?: Record<string, number>;
};

const pct = (x?: number | null) => (x == null ? "–" : `${Math.round(x * 100)}%`);

function SignalHow() {
  return (
    <Card className="space-y-3">
      <h2 className="text-xl font-bold">1. Recording check</h2>
      <p>Before scoring, the recording is checked for silence, low volume, distortion, background noise and cut-off words.
        If the recording is not good enough you are asked to record again instead of receiving a misleading score.</p>
      <h2 className="text-xl font-bold">2. Turning sound into numbers</h2>
      <p>Your recording and the example recordings (the <em>standards</em>) go through the same signal processing: a
        filter removes hum, the sound is cut into 25-millisecond slices, and each slice is measured: its frequency content
        (FFT and mel-frequency cepstral coefficients), loudness, how hissy it is (zero-crossing rate and high-frequency
        energy) and its pitch (autocorrelation). A normalisation step cancels most of the colouring a microphone or room adds.</p>
      <h2 className="text-xl font-bold">3. Lining up and comparing</h2>
      <p>Dynamic time warping lines your recording up with each standard slice by slice, so speaking faster or slower does not
        count as a difference, and a small voice-size adjustment lets children's and adults' voices match. The app then measures
        how close the sound pattern, loudness pattern, pitch pattern, number of syllables and timing are. American, British and
        other accepted pronunciations each have standards, and the closest one is used.</p>
      <h2 className="text-xl font-bold">4. Part by part, and common mistakes</h2>
      <p>Each syllable (or the start, vowel and end of a short word) gets its own score, so feedback can say which part differed
        most. The app also generates recordings of common mistakes, such as “wabbit” for “rabbit”, in the same voices as the
        standards: if your recording is clearly closer to a mistake than to the word, that mistake is named.</p>
      <h2 className="text-xl font-bold">5. Which word was it?</h2>
      <p>Your recording is also compared with the standards of every practice word. If another word matches better, the result
        says so and the confidence goes down.</p>
      <h2 className="text-xl font-bold">6. Score and feedback</h2>
      <p>The score combines sound-pattern similarity (45%), the common-mistake check (20%), the loudness pattern (15%), the pitch
        pattern (5%, for words with two or more syllables), syllables (5%) and timing (10%). Slow, careful speech is not penalised.
        Tips are generated only from what was measured; when an AI model writes them, anything not backed by a measurement is
        removed automatically.</p>
    </Card>
  );
}

function SignalAccuracy({ v }: { v?: Validation | null }) {
  if (!v) {
    return <p>The signal scorer has not been calibrated on this installation yet (run <code>scripts/calibrate_signal.py</code>).</p>;
  }
  return (
    <>
      <p>We do not have recordings of real learners yet, so we tested with <strong>generated voices the app never uses as
        standards</strong>: {v.correct_recordings} correct and {v.error_recordings} mispronounced recordings of all {v.words} words.</p>
      <ul className="list-disc space-y-1 pl-6">
        <li>A recording matched its own word first <strong>{pct(v.identification_top1)}</strong> of the time
          (top three: {pct(v.identification_top3)}).</li>
        <li>For common mistakes such as /w/ for /r/, a correct recording scored higher than a mistaken one
          <strong> {pct(v.auc_correct_vs_covered)}</strong> of the time; the mistake was named in {pct(v.mistake_named_covered)} of
          mistaken recordings and wrongly named for {pct(v.mistake_false_alarm_correct)} of correct ones.</li>
        <li>Other mistakes (vowel changes, dropped weak syllables) are harder to catch: correct recordings scored higher
          {" "}{pct(v.auc_correct_vs_uncovered)} of the time.</li>
      </ul>
      <p>Real voices, microphones and rooms vary more than generated voices, so expect lower accuracy in practice. That is
        why tips say “may”. The tool is <strong>not</strong> a clinical assessment, has not been clinically validated and must
        not be used to diagnose speech or language conditions.</p>
    </>
  );
}

function PhonemeHow() {
  return (
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
  );
}

function PhonemeAccuracy() {
  return (
    <>
      <p>We tested the sound scoring on <strong>speechocean762</strong>, a public dataset of 2,500 recordings by non-native
        English speakers that five experts scored sound by sound. On recordings the system never saw during development:</p>
      <ul className="list-disc space-y-1 pl-6">
        <li>Clearly mispronounced sounds were ranked below correct ones <strong>91%</strong> of the time (AUC 0.91).</li>
        <li>Sound scores correlate with the experts' ratings at <strong>r = 0.47</strong>; word scores at <strong>r = 0.48</strong>.</li>
        <li>When a sound scores below 70, experts judged it wrong in about <strong>35%</strong> of cases, which is why tips say “may”.</li>
      </ul>
      <p>That is a useful practice signal, but it is <strong>not</strong> a clinical assessment. The tool has not been clinically
        validated and must not be used to diagnose speech or language conditions.</p>
    </>
  );
}

export default function AboutPage() {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  useEffect(() => { api.status().then(setStatus).catch(() => undefined); }, []);
  const eng = status?.analysis_engine as Engine | undefined;
  const signal = !eng || eng.name === "signal-analysis";
  return (
    <div className="space-y-6">
      <h1 className="text-3xl font-bold">How your pronunciation is scored</h1>
      {signal ? <SignalHow /> : <PhonemeHow />}
      <Card className="space-y-2">
        <h2 className="text-xl font-bold">How accurate is it?</h2>
        {signal ? <SignalAccuracy v={eng?.validation} /> : <PhonemeAccuracy />}
      </Card>
      <Card className="space-y-2">
        <h2 className="text-xl font-bold">Privacy</h2>
        <p>Recordings are only stored if you switch on “Save my recordings” in Settings. You can delete recordings, your practice
          history or your whole account at any time.</p>
      </Card>
      {status && (
        <Card className="text-sm text-slate-600 dark:text-slate-400">
          <p>System: analysis engine <strong>{eng?.name}</strong>{eng?.model ? ` (${eng.model})` : ""}
            {signal ? " - signal comparison with standard recordings, no speech-recognition model"
              : eng?.phoneme_level === false ? " - acoustic baseline only, no sound-level scores" : ""} · feedback mode{" "}
            <strong>{String((status.feedback as { mode?: string }).mode)}</strong> · {status.words} practice words · API contract {status.contract_version}</p>
        </Card>
      )}
    </div>
  );
}
