import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Wordmark } from "@/components/JarvisNavbar";
import CoreVisualizer from "@/components/hud/CoreVisualizer";
import { useAssistant } from "@/features/assistant/context";

/** Boot screen. Each line reflects a real capability check from the backend. */
const StartupPage = () => {
  const navigate = useNavigate();
  const { state, levelRef, say } = useAssistant();
  const [started, setStarted] = useState(false);
  const caps = state.capabilities;

  const checks: [string, boolean | null][] = [
    ["Connected to the assistant", state.connected ? true : started ? false : null],
    ["Language model", caps ? caps.llm : null],
    ["Listening on this computer", caps ? caps.stt : null],
    ["JARVIS voice", caps ? caps.tts : null],
    ["Reading the screen", caps ? Boolean(caps.screen_ocr) : null],
    ["Internet", caps ? caps.online : null],
  ];

  const begin = () => {
    if (started) return;
    setStarted(true);
    const audio = new Audio("/sounds/boot.mp3");
    audio.volume = 0.5;
    audio.play().catch(() => undefined);
    void say(state.connected ? "JARVIS online. All core systems ready." : "Interface online. Waiting for the assistant.");
  };

  useEffect(() => {
    if (!started || !state.connected) return;
    const t = setTimeout(() => navigate("/"), 2800);
    return () => clearTimeout(t);
  }, [started, state.connected, navigate]);

  return (
    <div className="fixed inset-0 z-[60] flex flex-col items-center justify-center gap-8 bg-background px-6">
      <div className={`w-[min(60vw,240px)] ${started ? "core-boot" : "opacity-60"}`}>
        <CoreVisualizer phase={started ? state.phase : "OFFLINE"} levelRef={levelRef} size={240} className="h-auto w-full" />
      </div>
      <Wordmark />
      {started ? (
        <ul className="w-full max-w-xs space-y-2" aria-live="polite">
          {checks.map(([label, ok]) => (
            <li key={label} className="flex items-center justify-between gap-4 text-sm">
              <span className="text-foreground/90">{label}</span>
              <span className={ok === null ? "text-muted-foreground" : ok ? "text-jarvis-green" : "text-jarvis-ember"}>
                {ok === null ? "Checking" : ok ? "Ready" : "Not available"}
              </span>
            </li>
          ))}
        </ul>
      ) : (
        <button
          type="button"
          onClick={begin}
          className="min-h-12 rounded-xl bg-primary px-8 font-medium text-primary-foreground hover:bg-primary/90"
          autoFocus
        >
          Start JARVIS
        </button>
      )}
    </div>
  );
};

export default StartupPage;
