import { useCallback, useEffect, useMemo, useReducer, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, BackendUnreachable, jarvis } from "@/lib/api";
import { DATA_CHANGED_EVENT } from "@/lib/storage";
import { AssistantContext, type AssistantApi, type AssistantSettings } from "./context";
import { applyLocalCommand, matchLocalCommand } from "./localCommands";
import { assistantReducer, initialState } from "./machine";
import {
  browserSttSupported,
  openMic,
  recognizeOnce,
  recordUtterance,
  SpeechError,
  speak,
  stopSpeaking,
  type SttEngine,
  type TtsEngine,
} from "./speech";
import type { ExecResponse } from "./types";
import { matchWake } from "./wake";

const SETTINGS_KEY = "jarvis_assistant_settings";
/** Below this Whisper confidence, JARVIS asks you to check the text instead of running it. */
const LOW_STT_CONFIDENCE = 0.5;
const DEFAULT_SETTINGS: AssistantSettings = { stt: "auto", voice: true, tts: "auto", wake: true };

function loadSettings(): AssistantSettings {
  try {
    return { ...DEFAULT_SETTINGS, ...JSON.parse(localStorage.getItem(SETTINGS_KEY) ?? "{}") };
  } catch {
    return DEFAULT_SETTINGS;
  }
}

function isTypingTarget(el: EventTarget | null): boolean {
  const node = el as HTMLElement | null;
  if (!node) return false;
  return node.isContentEditable || ["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(node.tagName);
}

export function AssistantProvider({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const [state, dispatch] = useReducer(assistantReducer, initialState);
  const [settings, setSettings] = useState<AssistantSettings>(loadSettings);
  const levelRef = useRef(0);
  const [draft, setDraft] = useState("");
  const listenAbort = useRef<AbortController | null>(null);
  // Imperative guards: React state lags behind awaits, so it can't gate re-entry.
  const busyRef = useRef(false);
  const listeningRef = useRef(false);
  const stateRef = useRef(state);
  stateRef.current = state;

  // ---------------------------------------------------------------- connection
  const reconnectRef = useRef<() => void>(() => {});
  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const wasConnected = stateRef.current.connected;
        const caps = wasConnected ? (await jarvis.status()).capabilities : (await jarvis.connect(true)).capabilities;
        if (alive) dispatch({ type: "CONNECTED", capabilities: caps });
      } catch {
        if (alive) dispatch({ type: "DISCONNECTED" });
      }
      if (alive) timer = setTimeout(poll, stateRef.current.connected ? 10000 : 3000);
    };
    void poll();
    reconnectRef.current = () => {
      clearTimeout(timer);
      void poll();
    };
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, []);

  const activeStt: SttEngine | null = useMemo(() => {
    const caps = state.capabilities;
    if (settings.stt === "local") return caps?.stt ? "local" : null;
    if (settings.stt === "browser") return browserSttSupported() ? "browser" : null;
    if (caps?.stt) return "local";
    return browserSttSupported() ? "browser" : null;
  }, [settings.stt, state.capabilities]);
  const activeSttRef = useRef(activeStt);
  activeSttRef.current = activeStt;

  const activeTts: TtsEngine | null = useMemo(() => {
    if (!settings.voice) return null;
    const localReady = Boolean(state.capabilities?.tts);
    if (settings.tts === "browser") return "browser";
    if (localReady) return "local";
    return typeof window !== "undefined" && "speechSynthesis" in window ? "browser" : null;
  }, [settings.voice, settings.tts, state.capabilities]);
  const activeTtsRef = useRef(activeTts);
  activeTtsRef.current = activeTts;

  /** Speak with the active engine; the visualizer follows the real output level. */
  const voiceOut = useCallback(async (text: string) => {
    const engine = activeTtsRef.current;
    if (!engine || !text) return;
    await speak(text, {
      engine,
      fetchAudio: (t) => jarvis.speak(t),
      onStart: () => dispatch({ type: "SPEAK_START" }),
      onLevel: (l) => (levelRef.current = l),
    });
    levelRef.current = 0;
  }, []);

  // ---------------------------------------------------------------- responding
  const listenRef = useRef<() => Promise<void>>(async () => {});

  const respond = useCallback(async (text: string, opts: { fromVoice?: boolean; expectAnswer?: boolean }) => {
    // The turn's work is done; speaking must not block barge-in (Space interrupts).
    busyRef.current = false;
    if (activeTtsRef.current && text) {
      await voiceOut(text);
      dispatch({ type: "SPEAK_END" });
    }
    // Continue hands-free when JARVIS asked a question. Deferred to the next task so the
    // current turn (and its busy flag) has fully finished before listening again.
    if (opts.fromVoice && opts.expectAnswer) setTimeout(() => void listenRef.current(), 0);
  }, [voiceOut]);

  const handleExec = useCallback(
    async (resp: ExecResponse, fromVoice: boolean, listenAfter = false) => {
      dispatch({ type: "RESULT", response: resp });
      // Notes/Tasks/Calendar pages refresh when JARVIS changed their data by voice.
      const changed = new Set(resp.results.map((r) => r.data?.changed).filter(Boolean) as string[]);
      changed.forEach((kind) => window.dispatchEvent(new CustomEvent(DATA_CHANGED_EVENT, { detail: kind })));
      // Speak only the final user-facing response, in its short spoken form.
      const asks = resp.status === "needs_confirmation" || resp.status === "needs_clarification";
      await respond(resp.speech || resp.reply, { fromVoice, expectAnswer: asks || listenAfter });
    },
    [respond],
  );

  /** Show answers as they are written; fall back to a plain request if streaming isn't possible. */
  const executeStreaming = useCallback(async (planId: string) => {
    try {
      return await jarvis.executeStream(planId, (text) => dispatch({ type: "STREAM_DELTA", text }));
    } catch (err) {
      if (err instanceof BackendUnreachable) throw err;
      return jarvis.execute(planId);
    }
  }, []);

  const fail = useCallback((err: unknown) => {
    if (err instanceof BackendUnreachable) {
      dispatch({ type: "DISCONNECTED" });
      dispatch({ type: "FAIL", message: err.message });
      return;
    }
    const message = err instanceof Error ? err.message : "Something went wrong.";
    dispatch({ type: "FAIL", message });
    void voiceOut(message).then(() => dispatch({ type: "SPEAK_END" }));
  }, [voiceOut]);

  // ---------------------------------------------------------------- submit
  const submit = useCallback(
    async (raw: string, opts: { fromVoice?: boolean; listenAfter?: boolean } = {}) => {
      const text = raw.trim();
      if (!text || busyRef.current) return;
      busyRef.current = true;
      stopSpeaking();
      const fromVoice = Boolean(opts.fromVoice);

      const local = matchLocalCommand(text);
      if (local) {
        dispatch({ type: "UTTERANCE", text });
        applyLocalCommand(local, navigate);
        dispatch({ type: "REPLY", text: local.reply });
        busyRef.current = false;
        await respond(local.reply, { fromVoice });
        return;
      }

      dispatch({ type: "UTTERANCE", text });
      try {
        const plan = await jarvis.plan(text);
        if (plan.status === "ready" && plan.plan_id) {
          dispatch({ type: "PLAN_READY", steps: plan.steps, source: plan.source, confidence: plan.confidence });
          await handleExec(await executeStreaming(plan.plan_id), fromVoice, Boolean(opts.listenAfter));
        } else if (plan.status === "confirmation_decision" && plan.confirmation_id && plan.decision) {
          await handleExec(await jarvis.confirm(plan.confirmation_id, plan.decision), fromVoice);
        } else if (plan.status === "needs_clarification") {
          const q = plan.reply ?? "Could you say that differently?";
          dispatch({ type: "REPLY", text: q, tone: "question" });
          await respond(q, { fromVoice, expectAnswer: true });
        } else if (plan.status === "empty") {
          dispatch({ type: "SETTLE" });
        } else {
          const m = plan.reply ?? "I couldn't plan that.";
          dispatch({ type: "REPLY", text: m, tone: "error" });
          await respond(m, { fromVoice });
        }
      } catch (err) {
        fail(err);
      } finally {
        busyRef.current = false;
      }
    },
    [executeStreaming, fail, handleExec, navigate, respond],
  );

  const decide = useCallback(
    async (decision: "confirm" | "cancel") => {
      const conf = stateRef.current.confirmation;
      if (!conf || busyRef.current) return;
      busyRef.current = true;
      stopSpeaking();
      listenAbort.current?.abort();
      dispatch({ type: "DISMISS_CONFIRMATION" });
      try {
        const resp = await jarvis.confirm(conf.id, decision);
        busyRef.current = false;
        await handleExec(resp, false);
      } catch (err) {
        fail(err);
      } finally {
        busyRef.current = false;
      }
    },
    [fail, handleExec],
  );

  /** Unclear voice input: show it in the message box instead of acting on a guess. */
  const askToCheck = useCallback((heard: string) => {
    setDraft(heard);
    dispatch({ type: "REPLY", text: `I'm not sure I heard that right: “${heard}”. Fix it in the message box, or press Enter to send.`, tone: "question" });
  }, []);

  // ---------------------------------------------------------------- listening
  const listen = useCallback(async () => {
    const engine = activeSttRef.current;
    if (!engine) {
      dispatch({ type: "FAIL", message: "No speech recognition is available. Install faster-whisper on the backend or use Chrome." });
      return;
    }
    if (busyRef.current || listeningRef.current) return;
    listeningRef.current = true;
    stopSpeaking(); // barge-in
    const controller = new AbortController();
    listenAbort.current = controller;
    dispatch({ type: "LISTEN_START" });
    let mic: Awaited<ReturnType<typeof openMic>> | null = null;
    let meterRaf = 0;
    try {
      mic = await openMic();
      let text: string | null;
      if (engine === "local") {
        const blob = await recordUtterance({ mic, signal: controller.signal, onLevel: (l) => (levelRef.current = l) });
        mic.close();
        mic = null;
        levelRef.current = 0;
        if (!blob) {
          dispatch({ type: "LISTEN_END" });
          return;
        }
        dispatch({ type: "TRANSCRIBING" });
        const heard = await jarvis.transcribe(blob);
        if (heard.text.trim() && heard.confidence < LOW_STT_CONFIDENCE) {
          askToCheck(heard.text);
          return;
        }
        text = heard.text;
      } else {
        const m = mic;
        const meter = () => {
          levelRef.current = m.level();
          meterRaf = requestAnimationFrame(meter);
        };
        meter();
        text = await recognizeOnce(controller.signal);
      }
      if (!text?.trim()) {
        if (controller.signal.aborted) dispatch({ type: "LISTEN_END" });
        else {
          dispatch({ type: "LISTEN_END" });
          dispatch({ type: "REPLY", text: "I didn't catch that.", tone: "question" });
        }
        return;
      }
      dispatch({ type: "LISTEN_END" });
      listeningRef.current = false;
      await submit(text, { fromVoice: true });
    } catch (err) {
      dispatch({ type: "LISTEN_END" });
      if (err instanceof SpeechError || err instanceof ApiError) fail(err);
      else fail(new Error("Listening failed."));
    } finally {
      cancelAnimationFrame(meterRaf);
      mic?.close();
      levelRef.current = 0;
      listeningRef.current = false;
      if (listenAbort.current === controller) listenAbort.current = null;
    }
  }, [askToCheck, fail, submit]);
  listenRef.current = listen;

  // ---------------------------------------------------------------- wake phrase ("Jarvis, are you up?")
  const [wakeListening, setWakeListening] = useState(false);
  const [wakeError, setWakeError] = useState<string | null>(null);
  const wakeAvailable = settings.wake && activeStt === "local";
  // Only while JARVIS is idle: never while it speaks (it would hear itself) or while a command is in progress.
  const wakeEligible = wakeAvailable && !wakeError && state.connected && state.phase === "IDLE";

  useEffect(() => {
    if (!wakeEligible) return;
    const controller = new AbortController();
    let mic: Awaited<ReturnType<typeof openMic>> | null = null;
    void (async () => {
      try {
        mic = await openMic();
        if (controller.signal.aborted) return;
        setWakeListening(true);
        while (!controller.signal.aborted) {
          // Short bursts: "Jarvis" alone is ~0.5 s, "Jarvis, <command>" up to ~8 s. Silence restarts the recorder.
          const blob = await recordUtterance({ mic, signal: controller.signal, noSpeechMs: 5000, silenceMs: 1400, maxSpeechMs: 12000 });
          if (!blob || controller.signal.aborted) continue;
          const heard = await jarvis.transcribe(blob, "wake");
          const hit = matchWake(heard.text);
          if (hit && !controller.signal.aborted && !busyRef.current && !listeningRef.current) {
            controller.abort();
            mic.close();
            mic = null;
            if (!hit.listenAfter && heard.confidence < LOW_STT_CONFIDENCE) askToCheck(hit.utterance);
            else void submit(hit.utterance, { fromVoice: true, listenAfter: hit.listenAfter });
            return;
          }
        }
      } catch (err) {
        if (controller.signal.aborted) return;
        if (err instanceof SpeechError && err.code === "MIC_DENIED") setWakeError("Microphone access is blocked, so the wake phrase is off.");
        else if (err instanceof ApiError && err.code === "STT_UNAVAILABLE") setWakeError("Offline speech recognition isn't installed.");
        else if (!(err instanceof BackendUnreachable)) setWakeError("The wake listener stopped. Turn it off and on to retry.");
      } finally {
        mic?.close();
        setWakeListening(false);
      }
    })();
    return () => controller.abort();
  }, [askToCheck, wakeEligible, submit]);

  const cancel = useCallback(() => {
    listenAbort.current?.abort();
    stopSpeaking();
    if (stateRef.current.confirmation) void decide("cancel");
    else dispatch({ type: "SETTLE" });
  }, [decide]);

  const toggleListening = useCallback(() => {
    if (listeningRef.current) listenAbort.current?.abort();
    else void listen();
  }, [listen]);

  // Brief SUCCESS/ERROR flash when not speaking (purely visual).
  useEffect(() => {
    if ((state.phase === "SUCCESS" || state.phase === "ERROR") && !activeTts) {
      const t = setTimeout(() => dispatch({ type: "SETTLE" }), 1600);
      return () => clearTimeout(t);
    }
  }, [state.phase, activeTts]);

  // Global shortcuts: Space = push-to-talk toggle, Escape = cancel.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.repeat || isTypingTarget(e.target)) return;
      if (e.code === "Space") {
        e.preventDefault();
        toggleListening();
      } else if (e.key === "Escape") {
        cancel();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [cancel, toggleListening]);

  const updateSettings = useCallback((patch: Partial<AssistantSettings>) => {
    if ("wake" in patch) setWakeError(null); // toggling retries the listener
    setSettings((prev) => {
      const next = { ...prev, ...patch };
      try {
        localStorage.setItem(SETTINGS_KEY, JSON.stringify(next));
      } catch {
        // per-viewer convenience only
      }
      return next;
    });
  }, []);

  const api: AssistantApi = useMemo(
    () => ({
      reconnect: () => reconnectRef.current(),
      draft,
      setDraft,
      stopSpeaking: () => {
        stopSpeaking();
        dispatch({ type: "SPEAK_END" });
      },
      state,
      settings,
      levelRef,
      activeStt,
      activeTts,
      wakeAvailable,
      wakeListening,
      wakeError,
      say: async (text: string) => {
        await voiceOut(text);
        dispatch({ type: "SPEAK_END" });
      },
      submit,
      listen,
      toggleListening,
      cancel,
      decide,
      updateSettings,
    }),
    [
      draft,
      state,
      settings,
      activeStt,
      activeTts,
      wakeAvailable,
      wakeListening,
      wakeError,
      voiceOut,
      submit,
      listen,
      toggleListening,
      cancel,
      decide,
      updateSettings,
    ],
  );

  return <AssistantContext.Provider value={api}>{children}</AssistantContext.Provider>;
}
