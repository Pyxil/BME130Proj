import { describe, expect, it } from "vitest";
import { concatChunks, encodeWav, resample, SilenceDetector } from "../services/wav";

const tone = (freq: number, rate: number, seconds: number, amp = 0.5) =>
  Float32Array.from({ length: Math.round(rate * seconds) }, (_, i) => amp * Math.sin((2 * Math.PI * freq * i) / rate));

function zeroCrossings(x: Float32Array): number {
  let n = 0;
  for (let i = 1; i < x.length; i++) if ((x[i - 1] < 0) !== (x[i] < 0)) n++;
  return n;
}

describe("wav encoding", () => {
  it("writes a valid 16 kHz mono PCM header", async () => {
    const blob = encodeWav(new Float32Array(1600), 16000);
    const view = new DataView(await blob.arrayBuffer());
    const str = (o: number) => String.fromCharCode(...[0, 1, 2, 3].map((i) => view.getUint8(o + i)));
    expect(str(0)).toBe("RIFF");
    expect(str(8)).toBe("WAVE");
    expect(view.getUint16(22, true)).toBe(1); // mono
    expect(view.getUint32(24, true)).toBe(16000);
    expect(view.getUint16(34, true)).toBe(16);
    expect(view.getUint32(40, true)).toBe(3200);
    expect(blob.size).toBe(44 + 3200);
  });

  it("clips out-of-range samples instead of wrapping", async () => {
    const view = new DataView(await encodeWav(Float32Array.from([2, -2]), 16000).arrayBuffer());
    expect(view.getInt16(44, true)).toBe(32767);
    expect(view.getInt16(46, true)).toBe(-32768);
  });
});

describe("resampling", () => {
  it("downsamples 48 kHz to 16 kHz and preserves frequency", () => {
    const x = tone(440, 48000, 1);
    const y = resample(x, 48000, 16000);
    expect(y.length).toBe(16000);
    expect(zeroCrossings(y)).toBeGreaterThan(870);
    expect(zeroCrossings(y)).toBeLessThan(890);
  });

  it("attenuates content above the new Nyquist frequency (anti-aliasing)", () => {
    const y = resample(tone(12000, 48000, 0.5), 48000, 16000);
    const peak = Math.max(...Array.from(y.slice(100, -100), Math.abs));
    expect(peak).toBeLessThan(0.1);
  });

  it("concatenates chunks in order", () => {
    expect(Array.from(concatChunks([Float32Array.from([1, 2]), Float32Array.from([3])]))).toEqual([1, 2, 3]);
  });
});

describe("SilenceDetector (auto-stop)", () => {
  it("does not stop on silence before speech", () => {
    const d = new SilenceDetector(1000);
    for (let i = 0; i < 200; i++) expect(d.push(0.001, 20)).toBe(false);
    expect(d.speechStarted).toBe(false);
  });

  it("stops after the configured pause following speech", () => {
    const d = new SilenceDetector(1000);
    for (let i = 0; i < 15; i++) d.push(0.001, 20); // calibration (300 ms)
    for (let i = 0; i < 20; i++) expect(d.push(0.2, 20)).toBe(false); // speech
    let stoppedAt = -1;
    for (let i = 0; i < 100; i++) {
      if (d.push(0.001, 20)) { stoppedAt = i; break; }
    }
    expect(d.speechStarted).toBe(true);
    expect(stoppedAt).toBe(49); // 50 chunks x 20 ms = 1000 ms
  });
});
