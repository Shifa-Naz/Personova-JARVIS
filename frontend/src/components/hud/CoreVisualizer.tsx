import { useEffect, useRef, type MutableRefObject } from "react";
import { PHASES, phaseColor } from "@/features/assistant/phase";
import type { AssistantPhase } from "@/features/assistant/types";

interface CoreVisualizerProps {
  phase: AssistantPhase;
  levelRef?: MutableRefObject<number>;
  size?: number;
  className?: string;
}

const TICKS = Array.from({ length: 72 }, (_, i) => i);
const BARS = Array.from({ length: 32 }, (_, i) => i);

/**
 * JARVIS's original "core": concentric telemetry rings around a reactive nucleus.
 * Ring speed and color follow the assistant phase; the nucleus and radial bars
 * follow the live microphone level (read in an rAF loop — no React re-renders).
 */
const CoreVisualizer = ({ phase, levelRef, size = 280, className = "" }: CoreVisualizerProps) => {
  const coreRef = useRef<SVGCircleElement>(null);
  const barsRef = useRef<SVGGElement>(null);
  const meta = PHASES[phase];
  const color = phaseColor(phase);
  const active = phase === "LISTENING" || phase === "SPEAKING";

  useEffect(() => {
    let raf = 0;
    let smooth = 0;
    let t = 0;
    const loop = () => {
      t += 1;
      const mic = levelRef?.current ?? 0;
      // While speaking, follow the real voice output; the browser voice exposes no level,
      // so fall back to a gentle synthetic envelope.
      const synthetic = 0.25 + 0.2 * Math.abs(Math.sin(t / 7)) * Math.abs(Math.sin(t / 3.1));
      const target = phase === "SPEAKING" && mic < 0.01 ? synthetic : mic;
      smooth += (target - smooth) * 0.25;
      if (coreRef.current) coreRef.current.setAttribute("r", String(30 + smooth * 14));
      const bars = barsRef.current?.children;
      if (bars) {
        for (let i = 0; i < bars.length; i++) {
          const wobble = active ? 0.55 + 0.45 * Math.sin(t / 5 + i * 0.9) : 0.2;
          const len = 3 + smooth * 26 * wobble;
          (bars[i] as SVGLineElement).setAttribute("y2", String(52 - len));
        }
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, [phase, levelRef, active]);

  const spin = (seconds: number, reverse = false) =>
    seconds > 0 ? { animation: `jarvis-spin ${seconds}s linear infinite${reverse ? " reverse" : ""}` } : undefined;

  return (
    <div
      className={`relative inline-flex aspect-square items-center justify-center ${className}`}
      style={className.includes("w-full") ? undefined : { width: size, height: size }}
    >
      <div
        className="absolute inset-[12%] rounded-full blur-2xl transition-colors duration-700"
        style={{ background: phaseColor(phase, phase === "OFFLINE" ? 0.04 : 0.1) }}
      />
      <svg viewBox="0 0 200 200" width="100%" height="100%" role="img" aria-label={`JARVIS core: ${meta.label}`} className="relative">
        {/* outer telemetry ticks */}
        <g className="jarvis-ring" style={spin(meta.spin)}>
          {TICKS.map((i) => (
            <line
              key={i}
              x1="100"
              y1={i % 6 === 0 ? 3 : 6}
              x2="100"
              y2="10"
              stroke={color}
              strokeOpacity={i % 6 === 0 ? 0.9 : 0.35}
              strokeWidth={i % 6 === 0 ? 1.4 : 0.8}
              transform={`rotate(${i * 5} 100 100)`}
            />
          ))}
        </g>

        {/* segmented arc ring (counter-rotating) */}
        <g className="jarvis-ring" style={spin(meta.spin ? meta.spin * 0.6 : 0, true)}>
          <circle cx="100" cy="100" r="80" fill="none" stroke={color} strokeOpacity="0.55" strokeWidth="2.5"
            strokeDasharray="38 14 8 14" strokeLinecap="round" />
        </g>

        {/* thin inner ring + phase arc */}
        <circle cx="100" cy="100" r="66" fill="none" stroke={color} strokeOpacity="0.25" strokeWidth="0.8" />
        <g className="jarvis-ring" style={spin(meta.spin ? Math.max(2, meta.spin / 4) : 0)}>
          <circle cx="100" cy="100" r="66" fill="none" stroke={color} strokeWidth="2" strokeDasharray="60 355" strokeLinecap="round" />
          {(phase === "THINKING" || phase === "PROCESSING" || phase === "EXECUTING") && (
            <circle cx="100" cy="34" r="3" fill={color} />
          )}
        </g>

        {/* radial level bars */}
        <g ref={barsRef}>
          {BARS.map((i) => (
            <line key={i} x1="100" y1="52" x2="100" y2="49" stroke={color} strokeOpacity="0.8" strokeWidth="2"
              strokeLinecap="round" transform={`rotate(${(i * 360) / BARS.length} 100 100)`} />
          ))}
        </g>

        {/* nucleus */}
        <circle cx="100" cy="100" r="40" fill="none" stroke={color} strokeOpacity="0.4" strokeWidth="1" />
        <circle ref={coreRef} cx="100" cy="100" r="30" fill={phaseColor(phase, 0.18)} stroke={color} strokeWidth="1.5" />
        <circle cx="100" cy="100" r="9" fill={color} fillOpacity={phase === "OFFLINE" ? 0.3 : 0.9}>
          {phase !== "OFFLINE" && phase !== "ERROR" && (
            <animate attributeName="fill-opacity" values="0.95;0.45;0.95" dur={active ? "1.2s" : "3s"} repeatCount="indefinite" />
          )}
        </circle>
      </svg>
    </div>
  );
};

export default CoreVisualizer;
