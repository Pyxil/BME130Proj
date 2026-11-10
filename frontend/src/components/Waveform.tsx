import { useEffect, useRef } from "react";

/** Live time-domain waveform drawn from an AnalyserNode (decorative; status is announced as text). */
export function Waveform({ analyser, active }: { analyser: AnalyserNode | null; active: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    let raf = 0;
    const data = new Uint8Array(analyser?.fftSize ?? 2048);
    const draw = () => {
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      if (canvas.width !== w * dpr) {
        canvas.width = w * dpr;
        canvas.height = h * dpr;
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);
      ctx.lineWidth = 3;
      ctx.lineCap = "round";
      ctx.strokeStyle = active ? "#e11d48" : "#94a3b8";
      ctx.beginPath();
      if (analyser && active) {
        analyser.getByteTimeDomainData(data);
        const step = data.length / w;
        for (let x = 0; x < w; x++) {
          const v = (data[Math.floor(x * step)] - 128) / 128;
          const y = h / 2 + v * (h / 2) * 0.9;
          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
      } else {
        ctx.moveTo(0, h / 2);
        ctx.lineTo(w, h / 2);
      }
      ctx.stroke();
      raf = requestAnimationFrame(draw);
    };
    draw();
    return () => cancelAnimationFrame(raf);
  }, [analyser, active]);

  return <canvas ref={canvasRef} aria-hidden="true" className="h-24 w-full rounded-xl bg-slate-50 dark:bg-slate-950" />;
}
