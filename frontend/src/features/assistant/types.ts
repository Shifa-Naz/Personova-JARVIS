// Mirrors the backend response models in backend/jarvis/core/pipeline.py.

export type Permission = "READ_ONLY" | "SAFE" | "SENSITIVE" | "DESTRUCTIVE" | "BLOCKED";

export interface StepView {
  action: string;
  params: Record<string, unknown>;
  permission: Permission;
  requires_confirmation: boolean;
  description: string;
}

export interface PlanResponse {
  request_id: string;
  status: "ready" | "needs_clarification" | "confirmation_decision" | "empty" | "error";
  intent: string;
  source: "rules" | "llm";
  text: string;
  plan_id: string | null;
  steps: StepView[];
  reply: string | null;
  error_code: string | null;
  confirmation_id: string | null;
  decision: "confirm" | "cancel" | null;
  confidence: number;
  entities: Record<string, unknown>;
  risk: Permission;
}

export interface StepResult {
  action: string;
  ok: boolean;
  message: string;
  error_code: string | null;
  data: Record<string, unknown> | null;
  latency_ms: number;
}

export interface ConfirmationInfo {
  id: string;
  kind: "confirm" | "offer";
  summary: string;
  permission: Permission;
  expires_at: number;
  action: string | null;
}

export interface ExecResponse {
  request_id: string;
  status: "done" | "needs_confirmation" | "needs_clarification" | "cancelled" | "error" | "empty";
  intent: string;
  reply: string;
  results: StepResult[];
  confirmation: ConfirmationInfo | null;
  error_code: string | null;
  success: boolean;
  response_type: "conversation" | "action" | "confirmation" | "clarification" | "error";
  /** Shorter, plain-text version of `reply` for the voice (no code, no links). */
  speech: string;
  /** True when the answer was already spoken sentence by sentence while it streamed; `speech` holds what's left. */
  spoken_live?: boolean;
}

export interface Capabilities {
  llm: boolean;
  llm_model: string | null;
  llm_error: string | null;
  stt: boolean;
  stt_model: string;
  tts: boolean;
  tts_voice: string;
  screen_ocr: string | null;
  vision_model: string | null;
  online: boolean;
  automation: boolean;
}

export interface SessionInfo {
  token: string;
  platform: string;
  version: string;
  capabilities: Capabilities;
}

export interface Telemetry {
  cpu_percent: number;
  cpu_count: number;
  memory: { total: number; used: number; percent: number };
  disk: { total: number; used: number; free: number; percent: number } | null;
  battery: { percent: number; plugged: boolean; secs_left: number | null } | null;
  online: boolean;
  uptime_s: number;
  os: string;
  hostname: string;
  /** Busiest apps, when requested with ?processes=1. */
  processes?: ProcessInfo[];
}

export interface ProcessInfo {
  name: string;
  cpu_percent: number;
  memory: number;
  count: number;
}

export interface Headline {
  title: string;
  source: string;
  url: string;
  published: string;
}

export interface Briefing {
  reply: string;
  speech: string;
  data: { schedule: unknown; news: Headline[] };
}

/** Pushed by the backend (long-poll). `briefing` arrives when the laptop wakes up or the screen is unlocked. */
export interface JarvisEvent extends Briefing {
  type: "briefing";
  reason: "wake" | "unlock" | "start";
  seq: number;
  ts: number;
}

export interface LogEvent {
  ts: number;
  msg: string;
  [key: string]: unknown;
}

/** The ten UI states from CLAUDE.md §21. */
export type AssistantPhase =
  | "IDLE"
  | "LISTENING"
  | "PROCESSING"
  | "THINKING"
  | "EXECUTING"
  | "SPEAKING"
  | "SUCCESS"
  | "ERROR"
  | "CONFIRMATION_REQUIRED"
  | "OFFLINE";

export interface ChatMessage {
  id: string;
  role: "user" | "jarvis";
  text: string;
  ts: number;
  tone?: "normal" | "error" | "question";
  /** The action plan JARVIS ran for this turn, with per-step outcomes. */
  plan?: StepView[];
  results?: StepResult[];
  confidence?: number;
  source?: "rules" | "llm" | null;
}

export type ItemKind = "notes" | "tasks" | "events";
