import type { AssistantPhase, Capabilities, ChatMessage, ConfirmationInfo, ExecResponse, StepView } from "./types";

export interface AssistantState {
  phase: AssistantPhase;
  connected: boolean;
  capabilities: Capabilities | null;
  messages: ChatMessage[];
  plan: StepView[];
  planSource: "rules" | "llm" | null;
  planConfidence: number | null;
  /** Answer text arriving from the model before the turn finishes. */
  streamText: string;
  confirmation: ConfirmationInfo | null;
  lastError: string | null;
  lastDetail: string | null;
  interim: string;
}

export const initialState: AssistantState = {
  phase: "OFFLINE",
  connected: false,
  capabilities: null,
  messages: [],
  plan: [],
  planSource: null,
  planConfidence: null,
  streamText: "",
  confirmation: null,
  lastError: null,
  lastDetail: null,
  interim: "",
};

export type AssistantEvent =
  | { type: "CONNECTED"; capabilities: Capabilities }
  | { type: "DISCONNECTED" }
  | { type: "LISTEN_START" }
  | { type: "LISTEN_END" }
  | { type: "TRANSCRIBING" }
  | { type: "UTTERANCE"; text: string }
  | { type: "PLAN_READY"; steps: StepView[]; source: "rules" | "llm"; confidence?: number }
  | { type: "STREAM_DELTA"; text: string }
  | { type: "REPLY"; text: string; tone?: ChatMessage["tone"] }
  | { type: "RESULT"; response: ExecResponse }
  | { type: "SPEAK_START" }
  | { type: "SPEAK_END" }
  | { type: "SETTLE" }
  | { type: "FAIL"; message: string; detail?: string | null }
  | { type: "DISMISS_CONFIRMATION" };

let counter = 0;
const msg = (role: ChatMessage["role"], text: string, tone: ChatMessage["tone"] = "normal"): ChatMessage => ({
  id: `${Date.now()}-${++counter}`,
  role,
  text,
  tone,
  ts: Date.now(),
});

const MAX_MESSAGES = 60;
const push = (list: ChatMessage[], m: ChatMessage) => [...list, m].slice(-MAX_MESSAGES);

/** Where the UI rests when nothing is happening. */
const restPhase = (s: AssistantState): AssistantPhase =>
  !s.connected ? "OFFLINE" : s.confirmation ? "CONFIRMATION_REQUIRED" : "IDLE";

export function assistantReducer(state: AssistantState, event: AssistantEvent): AssistantState {
  switch (event.type) {
    case "CONNECTED": {
      const next = { ...state, connected: true, capabilities: event.capabilities };
      return state.phase === "OFFLINE" ? { ...next, phase: restPhase(next) } : next;
    }
    case "DISCONNECTED":
      return { ...state, connected: false, phase: "OFFLINE", confirmation: null };
    case "LISTEN_START":
      return { ...state, phase: "LISTENING", lastError: null, interim: "" };
    case "LISTEN_END":
      return state.phase === "LISTENING" || state.phase === "PROCESSING" ? { ...state, phase: restPhase(state) } : state;
    case "TRANSCRIBING":
      return { ...state, phase: "PROCESSING" };
    case "UTTERANCE":
      return {
        ...state,
        streamText: "",
        phase: "THINKING",
        messages: push(state.messages, msg("user", event.text)),
        plan: [],
        planSource: null,
        lastError: null,
        lastDetail: null,
      };
    case "PLAN_READY":
      return { ...state, phase: "EXECUTING", plan: event.steps, planSource: event.source, planConfidence: event.confidence ?? null };
    case "REPLY":
      return {
        ...state,
        phase: event.tone === "error" ? "ERROR" : event.tone === "question" ? "IDLE" : "SUCCESS",
        messages: push(state.messages, msg("jarvis", event.text, event.tone)),
      };
    case "STREAM_DELTA":
      return { ...state, streamText: state.streamText + event.text };
    case "RESULT": {
      const r = event.response;
      const confirmation = r.status === "needs_confirmation" ? r.confirmation : null;
      const isError = r.status === "error";
      const asks = Boolean(confirmation) || r.status === "needs_clarification";
      const tone: ChatMessage["tone"] = isError ? "error" : asks ? "question" : "normal";
      const detail = r.results.map((x) => (x.data?.detail as string | undefined) ?? null).find(Boolean) ?? null;
      const next: AssistantState = {
        ...state,
        streamText: "",
        confirmation,
        messages: r.reply
          ? push(state.messages, {
              ...msg("jarvis", r.reply, tone),
              plan: state.plan.length ? state.plan : undefined,
              results: r.results.length ? r.results : undefined,
              confidence: state.planConfidence ?? undefined,
              source: state.planSource,
            })
          : state.messages,
        lastError: isError ? r.reply || "Something went wrong." : null,
        lastDetail: detail,
      };
      next.phase = confirmation
        ? "CONFIRMATION_REQUIRED"
        : isError
          ? "ERROR"
          : r.status === "cancelled" || r.status === "needs_clarification"
            ? restPhase(next)
            : "SUCCESS";
      return next;
    }
    case "SPEAK_START":
      return { ...state, phase: "SPEAKING" };
    case "SPEAK_END":
    case "SETTLE":
      if (["SPEAKING", "SUCCESS", "ERROR"].includes(state.phase)) return { ...state, phase: restPhase(state) };
      return state;
    case "FAIL": {
      const next = {
        ...state,
        lastError: event.message,
        lastDetail: event.detail ?? null,
        messages: push(state.messages, msg("jarvis", event.message, "error")),
      };
      return { ...next, phase: state.connected ? "ERROR" : "OFFLINE" };
    }
    case "DISMISS_CONFIRMATION":
      return { ...state, confirmation: null, phase: state.phase === "CONFIRMATION_REQUIRED" ? restPhase({ ...state, confirmation: null }) : state.phase };
    default:
      return state;
  }
}
