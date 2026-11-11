import { useCallback, useEffect, useRef, useState } from "react";
import { getToken, USE_MOCKS } from "../services/api";
import { api } from "../services/endpoints";

/**
 * Plays the reference pronunciation from the backend (human recording or
 * neural TTS). If the backend has no audio engine, falls back to the
 * browser's built-in speech synthesis so the button always works.
 *
 * Call `prefetch` when a word appears: playback can then start synchronously
 * inside the click handler, which Safari's autoplay policy requires.
 */
export function useReferenceAudio() {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const cache = useRef(new Map<string, { url: string; source: string | null }>());
  const pending = useRef(new Map<string, Promise<{ url: string; source: string | null } | null>>());
  const [playing, setPlaying] = useState(false);
  const [source, setSource] = useState<string | null>(null);

  const speakFallback = useCallback((text: string, accent: string, slow: boolean) => {
    if (!("speechSynthesis" in window)) return;
    const u = new SpeechSynthesisUtterance(text);
    u.lang = accent === "gb" ? "en-GB" : "en-US";
    u.rate = slow ? 0.6 : 0.85;
    u.onend = () => setPlaying(false);
    window.speechSynthesis.cancel();
    setPlaying(true);
    setSource("browser speech synthesis");
    window.speechSynthesis.speak(u);
  }, []);

  const fetchAudio = useCallback((wordId: number, accent: string, slow: boolean) => {
    const key = `${wordId}:${accent}:${slow}`;
    const hit = cache.current.get(key);
    if (hit) return Promise.resolve(hit);
    let p = pending.current.get(key);
    if (!p) {
      p = fetch(api.wordAudioUrl(wordId, accent, slow), {
        headers: getToken() ? { Authorization: `Bearer ${getToken()}` } : {},
      })
        .then(async (res) => {
          if (!res.ok) return null;
          const entry = { url: URL.createObjectURL(await res.blob()), source: res.headers.get("X-Reference-Source") };
          cache.current.set(key, entry);
          return entry;
        })
        .catch(() => null)
        .finally(() => pending.current.delete(key));
      pending.current.set(key, p);
    }
    return p;
  }, []);

  const prefetch = useCallback((wordId: number, accent: string) => {
    if (!USE_MOCKS) void fetchAudio(wordId, accent, false);
  }, [fetchAudio]);

  const startAudio = useCallback((url: string, onFail: () => void) => {
    const audio = new Audio(url);
    audioRef.current = audio;
    audio.onended = () => setPlaying(false);
    setPlaying(true);
    audio.play().catch(() => {
      setPlaying(false);
      onFail();
    });
  }, []);

  const play = useCallback((wordId: number, text: string, accent: string, slow = false) => {
    audioRef.current?.pause();
    if (USE_MOCKS) return speakFallback(text, accent, slow);
    const fallback = () => speakFallback(text, accent, slow);
    const hit = cache.current.get(`${wordId}:${accent}:${slow}`);
    if (hit) {
      setSource(hit.source);
      startAudio(hit.url, fallback); // synchronous: still inside the user gesture
      return;
    }
    void fetchAudio(wordId, accent, slow).then((entry) => {
      if (!entry) return fallback();
      setSource(entry.source);
      startAudio(entry.url, fallback);
    });
  }, [fetchAudio, speakFallback, startAudio]);

  const playUrl = useCallback((url: string) => {
    audioRef.current?.pause();
    startAudio(url, () => undefined);
  }, [startAudio]);

  useEffect(() => {
    const entries = cache.current;
    return () => {
      audioRef.current?.pause();
      entries.forEach((e) => URL.revokeObjectURL(e.url));
    };
  }, []);

  return { play, playUrl, prefetch, playing, source };
}
