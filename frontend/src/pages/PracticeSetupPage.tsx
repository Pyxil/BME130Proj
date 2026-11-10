import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Alert, Button, Card } from "../components/ui";
import { ApiError } from "../services/api";
import { api } from "../services/endpoints";
import type { PhonemeOption, SessionMode, SessionSummary } from "../types";

const MODES: { mode: SessionMode; title: string; text: string; icon: string }[] = [
  { mode: "adaptive", title: "Smart practice", text: "Picks words with the sounds you find hardest. Recommended.", icon: "🎯" },
  { mode: "random", title: "Random words", text: "A mix of words from every level.", icon: "🎲" },
  { mode: "easy", title: "Easy words", text: "Short, simple words to warm up.", icon: "🌱" },
  { mode: "medium", title: "Medium words", text: "Clusters, R, L, S and TH sounds.", icon: "🌿" },
  { mode: "hard", title: "Difficult words", text: "Long words and tricky clusters.", icon: "🏔" },
  { mode: "phoneme", title: "One sound", text: "Choose a specific sound to practise.", icon: "🔤" },
  { mode: "missed", title: "Words to improve", text: "Words you haven't mastered yet.", icon: "↻" },
];

export default function PracticeSetupPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<SessionMode>("adaptive");
  const [phoneme, setPhoneme] = useState("r");
  const [size, setSize] = useState(10);
  const [phonemes, setPhonemes] = useState<PhonemeOption[]>([]);
  const [active, setActive] = useState<SessionSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.phonemes().then(setPhonemes).catch(() => undefined);
    api.sessions().then((s) => setActive(s.find((x) => x.status === "active" && x.words_attempted < x.total_words) ?? null)).catch(() => undefined);
  }, []);

  const start = async () => {
    setBusy(true);
    setError(null);
    try {
      const s = await api.createSession({ mode, size, phoneme: mode === "phoneme" ? phoneme : null });
      navigate(`/practice/${s.id}`);
    } catch (e) {
      setError((e as ApiError).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Practise your pronunciation</h1>
        <p className="mt-1 text-lg text-slate-700 dark:text-slate-300">Listen to a word, say it, and get feedback on every sound.</p>
      </div>
      {active && (
        <Alert kind="info" title="You have a session in progress">
          <div className="mt-2 flex flex-wrap items-center gap-3">
            <span>{active.words_attempted} of {active.total_words} words done.</span>
            <Button variant="secondary" onClick={() => navigate(`/practice/${active.id}`)}>Continue session</Button>
          </div>
        </Alert>
      )}
      <Card>
        <fieldset>
          <legend className="text-xl font-bold">1. Choose what to practise</legend>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {MODES.map((m) => (
              <label key={m.mode}
                className={`flex cursor-pointer gap-3 rounded-xl p-4 ring-2 transition ${mode === m.mode ? "bg-brand-50 ring-brand-600 dark:bg-brand-900/40" : "ring-slate-200 hover:ring-brand-300 dark:ring-slate-700"}`}>
                <input type="radio" name="mode" value={m.mode} checked={mode === m.mode} onChange={() => setMode(m.mode)} className="mt-1.5 h-5 w-5 accent-brand-700" />
                <span>
                  <span className="block text-lg font-bold"><span aria-hidden="true">{m.icon} </span>{m.title}</span>
                  <span className="text-slate-600 dark:text-slate-400">{m.text}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>
        {mode === "phoneme" && (
          <div className="mt-5">
            <label htmlFor="phoneme" className="block font-bold">Sound to practise</label>
            <select id="phoneme" value={phoneme} onChange={(e) => setPhoneme(e.target.value)}
              className="mt-2 min-h-12 w-full rounded-xl border border-slate-300 bg-white px-3 text-lg sm:w-96 dark:border-slate-700 dark:bg-slate-900">
              {phonemes.map((p) => (
                <option key={p.phoneme} value={p.phoneme}>/{p.phoneme}/ - {p.label} ({p.word_count} words)</option>
              ))}
            </select>
          </div>
        )}
        <fieldset className="mt-6">
          <legend className="text-xl font-bold">2. How many words?</legend>
          <div className="mt-3 flex gap-3">
            {[5, 10, 20].map((n) => (
              <label key={n} className={`flex min-h-12 cursor-pointer items-center rounded-xl px-5 ring-2 ${size === n ? "bg-brand-50 ring-brand-600 dark:bg-brand-900/40" : "ring-slate-200 dark:ring-slate-700"}`}>
                <input type="radio" name="size" className="sr-only" checked={size === n} onChange={() => setSize(n)} />
                <span className="text-lg font-bold">{n}</span>
              </label>
            ))}
          </div>
        </fieldset>
        {error && <div className="mt-4"><Alert kind="error">{error}</Alert></div>}
        <div className="mt-6">
          <Button size="lg" onClick={() => void start()} disabled={busy}>{busy ? "Preparing…" : "Start practising →"}</Button>
        </div>
      </Card>
    </div>
  );
}
