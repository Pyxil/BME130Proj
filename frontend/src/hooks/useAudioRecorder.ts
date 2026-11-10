import { useCallback, useEffect, useRef, useState } from "react";
import { concatChunks, encodeWav, resample, rms, SilenceDetector, TARGET_RATE } from "../services/wav";

export type RecorderState = "idle" | "requesting" | "recording" | "processing" | "done" | "error";

export interface Recording {
  blob: Blob; // 16 kHz mono 16-bit PCM WAV
  url: string; // object URL for playback
  durationS: number;
  peak: number;
}

export interface RecorderOptions {
  maxDurationMs?: number;
  autoStopSilenceMs?: number;
  noSpeechTimeoutMs?: number;
}

/**
 * Captures raw PCM from the microphone (AudioWorklet, with a ScriptProcessor
 * fallback), shows live levels, auto-stops after a pause in speech, and
 * converts the result to 16 kHz mono WAV for the backend.
 *
 * Browser audio processing (noise suppression, auto gain, echo cancellation)
 * is disabled because it distorts speech sounds the analysis depends on.
 */
export function useAudioRecorder(opts: RecorderOptions = {}) {
  const { maxDurationMs = 8000, autoStopSilenceMs = 1300, noSpeechTimeoutMs = 6000 } = opts;
  const [state, setState] = useState<RecorderState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [recording, setRecording] = useState<Recording | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [analyser, setAnalyser] = useState<AnalyserNode | null>(null);

  const ctxRef = useRef<AudioContext | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const nodeRef = useRef<AudioNode | null>(null);
  const chunksRef = useRef<Float32Array[]>([]);
  const detectorRef = useRef<SilenceDetector | null>(null);
  const stopRequested = useRef(false);
  const startedAt = useRef(0);
  const urlRef = useRef<string | null>(null);

  const cleanup = useCallback(() => {
    nodeRef.current?.disconnect();
    nodeRef.current = null;
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    const ctx = ctxRef.current;
    ctxRef.current = null;
    if (ctx && ctx.state !== "closed") void ctx.close();
    setAnalyser(null);
  }, []);

  const finish = useCallback(async (reason: "manual" | "silence" | "max" | "nospeech") => {
    if (stopRequested.current) return;
    stopRequested.current = true;
    const ctx = ctxRef.current;
    const rate = ctx?.sampleRate ?? 48000;
    const heardSpeech = detectorRef.current?.speechStarted ?? false;
    cleanup();
    if (reason === "nospeech" && !heardSpeech) {
      setState("error");
      setError("We didn't hear anything. Check that your microphone is on, then try again.");
      return;
    }
    setState("processing");
    // let the event loop breathe before heavy work
    await new Promise((r) => setTimeout(r, 0));
    const raw = concatChunks(chunksRef.current);
    chunksRef.current = [];
    const samples = resample(raw, rate, TARGET_RATE);
    let peak = 0;
    for (let i = 0; i < samples.length; i++) peak = Math.max(peak, Math.abs(samples[i]));
    const blob = encodeWav(samples, TARGET_RATE);
    if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    const url = URL.createObjectURL(blob);
    urlRef.current = url;
    setRecording({ blob, url, durationS: samples.length / TARGET_RATE, peak });
    setState("done");
  }, [cleanup]);

  const start = useCallback(async () => {
    setError(null);
    setRecording(null);
    setElapsedMs(0);
    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
      setState("error");
      setError("Microphone access needs a secure connection (https or localhost) and a modern browser.");
      return;
    }
    setState("requesting");
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: false },
      });
    } catch (err) {
      const name = (err as DOMException).name;
      setState("error");
      setError(
        name === "NotAllowedError" || name === "SecurityError"
          ? "Microphone permission was denied. Allow microphone access in your browser's site settings, then try again."
          : name === "NotFoundError" || name === "OverconstrainedError"
            ? "No microphone was found. Connect a microphone and try again."
            : name === "NotReadableError"
              ? "The microphone is being used by another application. Close it and try again."
              : "Could not start the microphone. Please try again.",
      );
      return;
    }
    const AudioCtx = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    const ctx = new AudioCtx();
    ctxRef.current = ctx;
    streamRef.current = stream;
    chunksRef.current = [];
    stopRequested.current = false;
    detectorRef.current = new SilenceDetector(autoStopSilenceMs);
    const source = ctx.createMediaStreamSource(stream);
    const an = ctx.createAnalyser();
    an.fftSize = 2048;
    source.connect(an);
    setAnalyser(an);

    const onChunk = (data: Float32Array) => {
      if (stopRequested.current) return;
      chunksRef.current.push(data);
      const ms = (data.length / ctx.sampleRate) * 1000;
      const elapsed = performance.now() - startedAt.current;
      setElapsedMs(elapsed);
      const shouldStop = detectorRef.current?.push(rms(data), ms);
      if (shouldStop) void finish("silence");
      else if (elapsed >= maxDurationMs) void finish("max");
      else if (elapsed >= noSpeechTimeoutMs && !detectorRef.current?.speechStarted) void finish("nospeech");
    };

    try {
      if (ctx.audioWorklet) {
        const code = `
          class Capture extends AudioWorkletProcessor {
            constructor() { super(); this.buf = []; this.n = 0; }
            process(inputs) {
              const ch = inputs[0] && inputs[0][0];
              if (ch) { this.buf.push(new Float32Array(ch)); this.n += ch.length; }
              if (this.n >= 1024) {
                const out = new Float32Array(this.n); let o = 0;
                for (const b of this.buf) { out.set(b, o); o += b.length; }
                this.port.postMessage(out, [out.buffer]); this.buf = []; this.n = 0;
              }
              return true;
            }
          }
          registerProcessor('capture-processor', Capture);`;
        const url = URL.createObjectURL(new Blob([code], { type: "application/javascript" }));
        await ctx.audioWorklet.addModule(url);
        URL.revokeObjectURL(url);
        const node = new AudioWorkletNode(ctx, "capture-processor", { numberOfInputs: 1, numberOfOutputs: 0 });
        node.port.onmessage = (e: MessageEvent<Float32Array>) => onChunk(e.data);
        source.connect(node);
        nodeRef.current = node;
      } else {
        const sp = ctx.createScriptProcessor(2048, 1, 1);
        sp.onaudioprocess = (e) => onChunk(new Float32Array(e.inputBuffer.getChannelData(0)));
        source.connect(sp);
        sp.connect(ctx.destination);
        nodeRef.current = sp;
      }
    } catch {
      cleanup();
      setState("error");
      setError("Audio recording is not supported in this browser.");
      return;
    }
    if (ctx.state === "suspended") await ctx.resume();
    startedAt.current = performance.now();
    setState("recording");
  }, [autoStopSilenceMs, cleanup, finish, maxDurationMs, noSpeechTimeoutMs]);

  const stop = useCallback(() => void finish("manual"), [finish]);

  const reset = useCallback(() => {
    cleanup();
    stopRequested.current = true;
    setRecording(null);
    setError(null);
    setElapsedMs(0);
    setState("idle");
  }, [cleanup]);

  useEffect(() => () => {
    cleanup();
    if (urlRef.current) URL.revokeObjectURL(urlRef.current);
  }, [cleanup]);

  return { state, error, recording, elapsedMs, analyser, start, stop, reset, maxDurationMs };
}
