import type { RecorderState } from "../hooks/useAudioRecorder";

function MicIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-10 w-10" fill="currentColor" aria-hidden="true">
      <path d="M12 3a3.5 3.5 0 0 0-3.5 3.5v5a3.5 3.5 0 0 0 7 0v-5A3.5 3.5 0 0 0 12 3zm6 8.5a6 6 0 0 1-5.25 5.95V20H16v1.5H8V20h3.25v-2.55A6 6 0 0 1 6 11.5h1.5a4.5 4.5 0 0 0 9 0z" />
    </svg>
  );
}

function StopIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-9 w-9" fill="currentColor" aria-hidden="true">
      <rect x="6" y="6" width="12" height="12" rx="2.5" />
    </svg>
  );
}

/** Large, keyboard-accessible record / stop control. */
export function RecordButton({ state, onStart, onStop, disabled }: {
  state: RecorderState; onStart: () => void; onStop: () => void; disabled?: boolean;
}) {
  const recording = state === "recording";
  const busy = state === "requesting" || state === "processing";
  const label = recording ? "Stop recording" : state === "requesting" ? "Starting microphone…" : "Record";
  return (
    <div className="flex flex-col items-center gap-3">
      <div className="relative">
        {recording && <span className="animate-pulse-ring absolute inset-0 rounded-full bg-record" aria-hidden="true" />}
        <button
          type="button"
          onClick={recording ? onStop : onStart}
          disabled={disabled || busy}
          aria-pressed={recording}
          aria-label={label}
          className={`relative flex h-28 w-28 items-center justify-center rounded-full text-white shadow-lg transition-transform focus-visible:scale-105 disabled:opacity-50 sm:h-32 sm:w-32 ${
            recording ? "bg-slate-800 hover:bg-slate-900" : "bg-record hover:bg-rose-700"
          }`}
        >
          {recording ? <StopIcon /> : <MicIcon />}
        </button>
      </div>
      <span className="text-lg font-bold">{recording ? "Stop" : "Record"}</span>
    </div>
  );
}
