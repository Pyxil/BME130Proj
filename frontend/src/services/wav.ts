/** Audio helpers: resampling to 16 kHz mono and 16-bit PCM WAV encoding. */

export const TARGET_RATE = 16000;

/** Concatenate captured Float32 chunks. */
export function concatChunks(chunks: Float32Array[]): Float32Array {
  const total = chunks.reduce((n, c) => n + c.length, 0);
  const out = new Float32Array(total);
  let offset = 0;
  for (const c of chunks) {
    out.set(c, offset);
    offset += c.length;
  }
  return out;
}

/**
 * Resample with a windowed-sinc low-pass (anti-aliasing) followed by linear
 * interpolation. Pure TypeScript so it is unit-testable and works where
 * OfflineAudioContext is unavailable.
 */
export function resample(input: Float32Array, fromRate: number, toRate = TARGET_RATE): Float32Array {
  if (fromRate === toRate) return input;
  let src = input;
  if (toRate < fromRate) {
    const cutoff = (0.45 * toRate) / fromRate; // normalised cutoff (cycles/sample)
    const half = 16;
    const taps = new Float32Array(2 * half + 1);
    let sum = 0;
    for (let i = -half; i <= half; i++) {
      const x = i === 0 ? 2 * cutoff : Math.sin(2 * Math.PI * cutoff * i) / (Math.PI * i);
      const w = 0.54 + 0.46 * Math.cos((Math.PI * i) / half); // Hamming window
      taps[i + half] = x * w;
      sum += x * w;
    }
    for (let i = 0; i < taps.length; i++) taps[i] /= sum;
    src = new Float32Array(input.length);
    for (let n = 0; n < input.length; n++) {
      let acc = 0;
      for (let k = -half; k <= half; k++) {
        const idx = n + k;
        if (idx >= 0 && idx < input.length) acc += input[idx] * taps[k + half];
      }
      src[n] = acc;
    }
  }
  const ratio = fromRate / toRate;
  const outLen = Math.floor(src.length / ratio);
  const out = new Float32Array(outLen);
  for (let i = 0; i < outLen; i++) {
    const pos = i * ratio;
    const i0 = Math.floor(pos);
    const i1 = Math.min(i0 + 1, src.length - 1);
    const frac = pos - i0;
    out[i] = src[i0] * (1 - frac) + src[i1] * frac;
  }
  return out;
}

/** Encode mono float samples as a 16-bit PCM WAV blob. */
export function encodeWav(samples: Float32Array, sampleRate = TARGET_RATE): Blob {
  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const writeStr = (offset: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(offset + i, s.charCodeAt(i));
  };
  writeStr(0, "RIFF");
  view.setUint32(4, 36 + samples.length * 2, true);
  writeStr(8, "WAVE");
  writeStr(12, "fmt ");
  view.setUint32(16, 16, true); // PCM chunk size
  view.setUint16(20, 1, true); // PCM format
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // byte rate
  view.setUint16(32, 2, true); // block align
  view.setUint16(34, 16, true); // bits per sample
  writeStr(36, "data");
  view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([buffer], { type: "audio/wav" });
}

export function rms(samples: Float32Array): number {
  let s = 0;
  for (let i = 0; i < samples.length; i++) s += samples[i] * samples[i];
  return Math.sqrt(s / Math.max(1, samples.length));
}

/**
 * Silence detector used for auto-stop: speech starts when the level rises
 * well above the noise floor; recording stops after `silenceMs` of quiet.
 */
export class SilenceDetector {
  private floor = Infinity;
  private elapsedMs = 0;
  private quietMs = 0;
  speechStarted = false;

  constructor(private silenceMs = 1300, private calibrationMs = 250) {}

  /** Returns true when recording should stop. */
  push(level: number, chunkMs: number): boolean {
    this.elapsedMs += chunkMs;
    if (this.elapsedMs <= this.calibrationMs) {
      this.floor = Math.min(this.floor, Math.max(level, 1e-4));
      return false;
    }
    const threshold = Math.max(0.012, Math.min(this.floor, 0.05) * 3.5);
    if (level > threshold) {
      this.speechStarted = true;
      this.quietMs = 0;
    } else if (this.speechStarted) {
      this.quietMs += chunkMs;
    }
    return this.speechStarted && this.quietMs >= this.silenceMs;
  }
}
