import { useCallback, useEffect, useMemo, useReducer, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError, BackendUnreachable, jarvis } from "@/lib/api";
import { DATA_CHANGED_EVENT } from "@/lib/storage";
import { AssistantContext, type AssistantApi, type AssistantSettings, type BriefingView } from "./context";
import { applyLocalCommand, matchLocalCommand } from "./localCommands";
import { assistantReducer, initialState } from "./machine";
import {
  audioBlocked,
  browserSttSupported,
  enqueueSpeech,
  installAudioUnlock,
  isSpeaking,
  openMic,
  recognizeOnce,
  recordUtterance,
  SpeechError,
  speak,
  speechDrained,
  stopSpeaking,
  type SttEngine,
  type TtsEngine,
} from "./speech";
import type { Briefing, ExecResponse } from "./types";
import { matchWake } from "./wake";

const SETTINGS_KEY = "jarvis_assistant_settings";
/** Below this Whisper confidence, JARVIS asks you to check the text instead of running it. */
const LOW_STT_CONFIDENCE = 0.5;
const DEFAULT_SETTINGS: AssistantSettings = { stt: "auto", voice: true, tts: "auto", wake: true, briefing: true };
const BRIEFING_SEEN_KEY = "jarvis_briefing_seen";

/** Resolves after `ms`, or at once when `signal` aborts (retry back-off, not synchronisation). */
function pause(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const t = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => {
      clearTimeout(t);
      resolve();
    }, { once: true });
  });
}

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

  const speakOptions = useCallback(
    () => ({
      engine: activeTtsRef.current ?? ("browser" as const),
      fetchAudio: (t: string) => jarvis.speak(t),
      onStart: () => dispatch({ type: "SPEAK_START" }),
      onLevel: (l: number) => (levelRef.current = l),
    }),
    [],
  );

  /** Speak with the active engine; the visualizer follows the real output level. */
  const voiceOut = useCallback(async (text: string) => {
    if (!activeTtsRef.current || !text) return;
    await speak(text, speakOptions());
    levelRef.current = 0;
  }, [speakOptions]);

  // Sentences of a streaming answer are spoken as they arrive (the backend sends them as "say" events).
  const spokeLiveRef = useRef(false);
  const sayLive = useCallback((sentence: string) => {
    if (!activeTtsRef.current) return;
    spokeLiveRef.current = true;
    void enqueueSpeech(sentence, speakOptions());
  }, [speakOptions]);

  // ---------------------------------------------------------------- responding
  const listenRef = useRef<() => Promise<void>>(async () => {});

  const respond = useCallback(async (text: string, opts: { fromVoice?: boolean; expectAnswer?: boolean; live?: boolean }) => {
    // The turn's work is done; speaking must not block barge-in (Space interrupts).
    busyRef.current = false;
    if (activeTtsRef.current && opts.live) {
      // Most of the answer is already queued; add what's left and wait for the voice to finish.
      if (text) void enqueueSpeech(text, speakOptions());
      await speechDrained();
      levelRef.current = 0;
      dispatch({ type: "SPEAK_END" });
    } else if (activeTtsRef.current && text) {
      await voiceOut(text);
      dispatch({ type: "SPEAK_END" });
    }
    // Continue hands-free when JARVIS asked a question. Deferred to the next task so the
    // current turn (and its busy flag) has fully finished before listening again.
    if (opts.fromVoice && opts.expectAnswer) setTimeout(() => void listenRef.current(), 0);
  }, [speakOptions, voiceOut]);

  const handleExec = useCallback(
    async (resp: ExecResponse, fromVoice: boolean, listenAfter = false) => {
      dispatch({ type: "RESULT", response: resp });
      // Notes/Tasks/Calendar pages refresh when JARVIS changed their data by voice.
      const changed = new Set(resp.results.map((r) => r.data?.changed).filter(Boolean) as string[]);
      changed.forEach((kind) => window.dispatchEvent(new CustomEvent(DATA_CHANGED_EVENT, { detail: kind })));
      // Speak only the final user-facing response, in its short spoken form.
      const asks = resp.status === "needs_confirmation" || resp.status === "needs_clarification";
      const live = Boolean(resp.spoken_live) && spokeLiveRef.current;
      spokeLiveRef.current = false;
      await respond(live ? resp.speech : resp.speech || resp.reply, { fromVoice, expectAnswer: asks || listenAfter, live });
    },
    [respond],
  );

  /** Show answers as they are written; fall back to a plain request if streaming isn't possible. */
  const executeStreaming = useCallback(async (planId: string) => {
    try {
      spokeLiveRef.current = false;
      return await jarvis.executeStream(planId, (text) => dispatch({ type: "STREAM_DELTA", text }), sayLive);
    } catch (err) {
      if (err instanceof BackendUnreachable) throw err;
      if (spokeLiveRef.current) throw err; // the plan already ran; never run it twice
      return jarvis.execute(planId);
    }
  }, [sayLive]);

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
  const [audioLocked, setAudioLocked] = useState(false);
  const wakeAvailable = settings.wake && activeStt === "local";
  // Only while JARVIS is idle: never while it speaks (it would hear itself) or while a command is in progress.
  const wakeEligible = wakeAvailable && !wakeError && state.connected && state.phase === "IDLE";

  // Without the launcher, Chrome holds audio back until the first click or key press anywhere on the page.
  useEffect(() => installAudioUnlock(() => setAudioLocked(audioBlocked())), []);

  useEffect(() => {
    if (!wakeEligible) return;
    const controller = new AbortController();
    const { signal } = controller;
    let mic: Awaited<ReturnType<typeof openMic>> | null = null;
    void (async () => {
      let failures = 0;
      while (!signal.aborted) {
        try {
          // A new microphone session after the old one died (unplugged, or the laptop slept and woke up).
          if (!mic || !mic.alive()) {
            mic?.close();
            mic = await openMic();
            if (signal.aborted) break;
          }
          if (mic.blocked()) {
            setAudioLocked(true);
            await pause(1000, signal);
            continue;
          }
          setAudioLocked(false);
          setWakeListening(true);
          // Short bursts: "Jarvis" alone is ~0.5 s, "Jarvis, <command>" up to ~8 s. Silence restarts the recorder.
          const blob = await recordUtterance({ mic, signal, noSpeechMs: 5000, silenceMs: 1200, maxSpeechMs: 12000 });
          failures = 0;
          if (!blob || signal.aborted) continue;
          const heard = await jarvis.transcribe(blob, "wake");
          const hit = matchWake(heard.text);
          if (hit && !signal.aborted && !busyRef.current && !listeningRef.current) {
            controller.abort();
            mic.close();
            mic = null;
            if (!hit.listenAfter && heard.confidence < LOW_STT_CONFIDENCE) askToCheck(hit.utterance);
            else void submit(hit.utterance, { fromVoice: true, listenAfter: hit.listenAfter });
            return;
          }
        } catch (err) {
          if (signal.aborted) break;
          if (err instanceof SpeechError && err.code === "MIC_DENIED") {
            setWakeError("Microphone access is blocked, so the wake phrase is off. Allow the microphone for this page.");
            break;
          }
          if (err instanceof ApiError && err.code === "STT_UNAVAILABLE") {
            setWakeError("Offline speech recognition isn't installed.");
            break;
          }
          // Anything else is temporary (mic busy, backend restarting, waking from sleep): try again shortly.
          mic?.close();
          mic = null;
          setWakeListening(false);
          failures += 1;
          await pause(Math.min(10000, 1000 * failures), signal);
        }
      }
      mic?.close();
      setWakeListening(false);
    })();
    return () => controller.abort();
  }, [askToCheck, wakeEligible, submit]);

  // ---------------------------------------------------------------- briefing (lid open, start-up, on request)
  const [briefing, setBriefing] = useState<BriefingView | null>(null);
  const pendingBriefing = useRef<BriefingView | null>(null);

  const deliverBriefing = useCallback(
    (b: Briefing, reason: BriefingView["reason"]) => {
      const view: BriefingView = { reply: b.reply, speech: b.speech, at: Date.now(), reason };
      setBriefing(view);
      // Never talk over a command in progress; it is said as soon as JARVIS is idle again.
      if (busyRef.current || listeningRef.current || stateRef.current.phase !== "IDLE") {
        pendingBriefing.current = view;
        return;
      }
      stopSpeaking();
      dispatch({ type: "REPLY", text: view.reply });
      void respond(view.speech, {});
    },
    [respond],
  );

  useEffect(() => {
    const view = pendingBriefing.current;
    if (!view || state.phase !== "IDLE" || busyRef.current) return;
    pendingBriefing.current = null;
    dispatch({ type: "REPLY", text: view.reply });
    void respond(view.speech, {});
  }, [state.phase, respond]);

  const requestBriefing = useCallback(async () => {
    try {
      deliverBriefing(await jarvis.briefing(), "request");
    } catch (err) {
      fail(err);
    }
  }, [deliverBriefing, fail]);

  // Started by the launcher at login (?briefing=1): brief once the backend is reachable.
  const startBriefingDone = useRef(false);
  useEffect(() => {
    if (!state.connected || startBriefingDone.current) return;
    startBriefingDone.current = true;
    const params = new URLSearchParams(window.location.search);
    if (params.get("briefing") !== "1" || !settings.briefing) return;
    params.delete("briefing");
    const rest = params.toString();
    window.history.replaceState(null, "", window.location.pathname + (rest ? `?${rest}` : "") + window.location.hash);
    void jarvis.briefing().then((b) => deliverBriefing(b, "start")).catch(() => undefined);
  }, [state.connected, settings.briefing, deliverBriefing]);

  // Lid-open briefings are pushed by the backend; long-poll for them while connected.
  const briefingOn = settings.briefing;
  useEffect(() => {
    if (!state.connected || !briefingOn) return;
    const controller = new AbortController();
    void (async () => {
      let after = -1;
      let seenTs = 0;
      try {
        seenTs = Number(sessionStorage.getItem(BRIEFING_SEEN_KEY) ?? 0);
      } catch {
        seenTs = 0;
      }
      while (!controller.signal.aborted) {
        try {
          const r = await jarvis.events(after, after < 0 ? 0 : 25);
          if (controller.signal.aborted) return;
          if (r.seq < after) {
            after = -1; // the backend restarted and counts from zero again
            continue;
          }
          for (const e of r.events) {
            if (e.type !== "briefing" || e.ts <= seenTs) continue;
            seenTs = e.ts;
            try {
              sessionStorage.setItem(BRIEFING_SEEN_KEY, String(e.ts));
            } catch {
              // per-tab convenience only
            }
            deliverBriefing(e, e.reason);
          }
          after = r.seq;
        } catch {
          await pause(3000, controller.signal); // backend restarting or the laptop just woke up
        }
      }
    })();
    return () => controller.abort();
  }, [state.connected, briefingOn, deliverBriefing]);

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

  // Return to rest after a SUCCESS/ERROR flash once nothing is being said. Also a safety net: if a reply was
  // never spoken (no audio, empty text), the wake listener must not stay switched off.
  useEffect(() => {
    if (state.phase !== "SUCCESS" && state.phase !== "ERROR") return;
    const t = setInterval(() => {
      if (!isSpeaking() && !busyRef.current) dispatch({ type: "SETTLE" });
    }, activeTts ? 2500 : 1600);
    return () => clearInterval(t);
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
      audioLocked,
      briefing,
      requestBriefing,
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
      audioLocked,
      briefing,
      requestBriefing,
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
