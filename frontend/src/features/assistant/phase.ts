import type { AssistantPhase } from "./types";

export interface PhaseMeta {
  label: string;
  /** CSS color token (HSL triplet variable) */
  color: string;
  /** Seconds per revolution for the outer ring; 0 = still. */
  spin: number;
  hint: string;
}

/** Ice = JARVIS listening/speaking; violet = thinking; ember = acting on the computer or waiting for you. */
export const PHASES: Record<AssistantPhase, PhaseMeta> = {
  IDLE: { label: "Ready", color: "--jarvis-cyan", spin: 70, hint: "Press Space or the mic, then speak" },
  LISTENING: { label: "Listening", color: "--jarvis-cyan", spin: 16, hint: "Speak now. Press Space when you're done." },
  PROCESSING: { label: "Hearing you", color: "--jarvis-violet", spin: 8, hint: "Turning your speech into text" },
  THINKING: { label: "Thinking", color: "--jarvis-violet", spin: 5, hint: "Working out what you want" },
  EXECUTING: { label: "Working", color: "--jarvis-amber", spin: 4, hint: "Carrying out the plan" },
  SPEAKING: { label: "Speaking", color: "--jarvis-cyan", spin: 24, hint: "Press Space to interrupt" },
  SUCCESS: { label: "Done", color: "--jarvis-green", spin: 30, hint: "" },
  ERROR: { label: "Something went wrong", color: "--jarvis-red", spin: 0, hint: "" },
  CONFIRMATION_REQUIRED: {
    label: "Waiting for you",
    color: "--jarvis-amber",
    spin: 40,
    hint: "Say yes or no, or use the buttons",
  },
  OFFLINE: { label: "Offline", color: "--jarvis-grey", spin: 0, hint: "Start the backend with: python run.py" },
};

export const phaseColor = (phase: AssistantPhase, alpha = 1) => `hsl(var(${PHASES[phase].color}) / ${alpha})`;
