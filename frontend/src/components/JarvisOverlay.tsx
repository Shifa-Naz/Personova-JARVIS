import { useLocation } from "react-router-dom";
import CoreVisualizer from "@/components/hud/CoreVisualizer";
import { useAssistant } from "@/features/assistant/context";
import { PHASES } from "@/features/assistant/phase";

/** A small core in the corner of the Tasks, Calendar, Notes and About pages: click it (or press Space) to talk. */
const JarvisOverlay = () => {
  const { state, levelRef, toggleListening, activeStt } = useAssistant();
  const location = useLocation();

  if (["/", "/assistant", "/startup"].includes(location.pathname)) return null;
  const lastReply = [...state.messages].reverse().find((m) => m.role === "jarvis");
  const active = !["IDLE", "OFFLINE"].includes(state.phase);

  return (
    <div className="fixed bottom-4 right-4 z-40 flex items-end gap-3">
      {state.phase === "SPEAKING" && lastReply && (
        <p className="panel hidden max-w-xs px-4 py-3 text-sm text-foreground shadow-2xl sm:block">{lastReply.text.slice(0, 220)}</p>
      )}
      <button
        type="button"
        onClick={toggleListening}
        disabled={!activeStt || !state.connected}
        aria-label={state.phase === "LISTENING" ? "Stop listening" : "Talk to JARVIS"}
        title={PHASES[state.phase].label}
        className="rounded-full border border-border bg-card/90 p-1 shadow-xl backdrop-blur disabled:cursor-not-allowed disabled:opacity-60"
      >
        <CoreVisualizer phase={state.phase} levelRef={levelRef} size={active ? 76 : 60} />
      </button>
    </div>
  );
};

export default JarvisOverlay;
