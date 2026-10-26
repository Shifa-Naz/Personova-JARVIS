import { PHASES, phaseColor } from "@/features/assistant/phase";
import type { AssistantPhase } from "@/features/assistant/types";

/** The core's caption: what JARVIS is doing right now, in plain words. */
const StatusReadout = ({ phase, detail }: { phase: AssistantPhase; detail?: string | null }) => {
  const meta = PHASES[phase];
  return (
    <div className="text-center" role="status" aria-live="polite">
      <p className="font-display text-xl font-semibold transition-colors" style={{ color: phaseColor(phase) }}>
        {meta.label}
      </p>
      <p className="mx-auto mt-1 min-h-6 max-w-xs text-sm text-muted-foreground">{detail || meta.hint}</p>
    </div>
  );
};

export default StatusReadout;
