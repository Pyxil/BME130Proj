import { useCallback, useEffect, useRef, useState } from "react";
import { getToken, USE_MOCKS } from "../services/api";
import { api } from "../services/endpoints";

/**
 * Plays the reference pronunciation from the backend (human recording or
 * neural TTS). If the backend has no audio engine, falls back to the
 * browser's built-in speech synthesis so the button always works.
 */
export function useReferenceAudio() {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const cache = useRef(new Map<string, string>());
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

  const play = useCallback(async (wordId: number, text: string, accent: string, slow = false) => {
    audioRef.current?.pause();
    if (USE_MOCKS) return speakFallback(text, accent, slow);
    const key = `${wordId}:${accent}:${slow}`;
    try {
      let url = cache.current.get(key);
      if (!url) {
        const res = await fetch(api.wordAudioUrl(wordId, accent, slow), {
          headers: getToken() ? { Authorization: `Bearer ${getToken()}` } : {},
        });
        if (!res.ok) throw new Error(String(res.status));
        setSource(res.headers.get("X-Reference-Source"));
        url = URL.createObjectURL(await res.blob());
        cache.current.set(key, url);
      }
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => setPlaying(false);
      setPlaying(true);
      await audio.play();
    } catch {
      setPlaying(false);
      speakFallback(text, accent, slow);
    }
  }, [speakFallback]);

  const playUrl = useCallback(async (url: string) => {
    audioRef.current?.pause();
    const audio = new Audio(url);
    audioRef.current = audio;
    audio.onended = () => setPlaying(false);
    setPlaying(true);
    try {
      await audio.play();
    } catch {
      setPlaying(false);
    }
  }, []);

  useEffect(() => {
    const urls = cache.current;
    return () => {
      audioRef.current?.pause();
      urls.forEach((u) => URL.revokeObjectURL(u));
    };
  }, []);

  return { play, playUrl, playing, source };
}
