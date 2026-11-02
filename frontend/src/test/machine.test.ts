import { describe, expect, it } from "vitest";
import { assistantReducer, initialState, type AssistantState } from "@/features/assistant/machine";
import type { Capabilities, ExecResponse } from "@/features/assistant/types";

const caps: Capabilities = {
  llm: true,
  llm_model: "m",
  llm_error: null,
  stt: true,
  stt_model: "base.en",
  tts: true,
  tts_voice: "en_GB-alan-medium",
  screen_ocr: "rapidocr",
  vision_model: null,
  online: true,
  automation: false,
};

const exec = (over: Partial<ExecResponse>): ExecResponse => ({
  request_id: "r",
  status: "done",
  intent: "COMMAND",
  reply: "Opening Chrome.",
  results: [],
  confirmation: null,
  error_code: null,
  success: true,
  response_type: "action",
  speech: "",
  ...over,
});

const connected = (): AssistantState => assistantReducer(initialState, { type: "CONNECTED", capabilities: caps });

describe("assistant state machine", () => {
  it("starts OFFLINE and goes IDLE when the backend connects", () => {
    expect(initialState.phase).toBe("OFFLINE");
    expect(connected().phase).toBe("IDLE");
  });

  it("walks LISTENING → THINKING → EXECUTING → SUCCESS → SPEAKING → IDLE", () => {
    let s = connected();
    s = assistantReducer(s, { type: "LISTEN_START" });
    expect(s.phase).toBe("LISTENING");
    s = assistantReducer(s, { type: "UTTERANCE", text: "open chrome" });
    expect(s.phase).toBe("THINKING");
    expect(s.messages.at(-1)).toMatchObject({ role: "user", text: "open chrome" });
    s = assistantReducer(s, {
      type: "PLAN_READY",
      source: "rules",
      steps: [{ action: "open_application", params: { app: "chrome" }, permission: "SAFE", requires_confirmation: false, description: "" }],
    });
    expect(s.phase).toBe("EXECUTING");
    s = assistantReducer(s, { type: "RESULT", response: exec({}) });
    expect(s.phase).toBe("SUCCESS");
    s = assistantReducer(s, { type: "SPEAK_START" });
    expect(s.phase).toBe("SPEAKING");
    s = assistantReducer(s, { type: "SPEAK_END" });
    expect(s.phase).toBe("IDLE");
  });

  it("holds CONFIRMATION_REQUIRED after speaking until the user decides", () => {
    let s = connected();
    s = assistantReducer(s, {
      type: "RESULT",
      response: exec({
        status: "needs_confirmation",
        reply: "This would move 3 files to the trash. Do you want me to proceed?",
        confirmation: { id: "c1", kind: "confirm", summary: "…", permission: "DESTRUCTIVE", expires_at: 0, action: "delete_files" },
      }),
    });
    expect(s.phase).toBe("CONFIRMATION_REQUIRED");
    s = assistantReducer(s, { type: "SPEAK_START" });
    s = assistantReducer(s, { type: "SPEAK_END" });
    expect(s.phase).toBe("CONFIRMATION_REQUIRED");
    expect(s.messages.at(-1)?.tone).toBe("question");
    s = assistantReducer(s, { type: "DISMISS_CONFIRMATION" });
    expect(s.phase).toBe("IDLE");
    expect(s.confirmation).toBeNull();
  });

  it("shows ERROR with the reply and surfaces details", () => {
    let s = connected();
    s = assistantReducer(s, {
      type: "RESULT",
      response: exec({
        status: "error",
        reply: "My offline language model isn't available right now.",
        results: [{ action: "answer_question", ok: false, message: "", error_code: "AI_UNAVAILABLE", data: { detail: "Ollama isn't running" }, latency_ms: 1 }],
      }),
    });
    expect(s.phase).toBe("ERROR");
    expect(s.lastDetail).toBe("Ollama isn't running");
    expect(assistantReducer(s, { type: "SETTLE" }).phase).toBe("IDLE");
  });

  it("goes OFFLINE on disconnect and drops pending confirmations", () => {
    let s = connected();
    s = { ...s, confirmation: { id: "c", kind: "offer", summary: "", permission: "SAFE", expires_at: 0, action: null } };
    s = assistantReducer(s, { type: "DISCONNECTED" });
    expect(s.phase).toBe("OFFLINE");
    expect(s.confirmation).toBeNull();
  });

  it("returns from PROCESSING to rest when transcription yields nothing", () => {
    let s = connected();
    s = assistantReducer(s, { type: "LISTEN_START" });
    s = assistantReducer(s, { type: "TRANSCRIBING" });
    expect(s.phase).toBe("PROCESSING");
    expect(assistantReducer(s, { type: "LISTEN_END" }).phase).toBe("IDLE");
  });
});

describe("live speech", () => {
  it("keeps speaking when the final result arrives mid-sentence", () => {
    let s = assistantReducer({ ...initialState, connected: true, phase: "IDLE" }, { type: "UTTERANCE", text: "what is polymorphism" });
    s = assistantReducer(s, { type: "SPEAK_START" });
    s = assistantReducer(s, {
      type: "RESULT",
      response: {
        request_id: "r",
        status: "done",
        intent: "QUESTION",
        reply: "Polymorphism means many forms.",
        results: [],
        confirmation: null,
        error_code: null,
        success: true,
        response_type: "conversation",
        speech: "",
        spoken_live: true,
      },
    });
    expect(s.phase).toBe("SPEAKING");
    expect(assistantReducer(s, { type: "SPEAK_END" }).phase).toBe("IDLE");
  });
});
