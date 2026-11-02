/**
 * Speech I/O adapters.
 *
 * STT has two interchangeable engines:
 *  - "local":   records with MediaRecorder, stops on silence, sends audio to the backend's
 *               offline Whisper model (works without internet).
 *  - "browser": the browser's SpeechRecognition (Chrome/Edge; sends audio to the vendor's cloud).
 * TTS uses the browser's speechSynthesis (OS voices; offline on most systems).
 */

export type SttEngine = "local" | "browser";

export class SpeechError extends Error {
  constructor(
    public code: "MIC_DENIED" | "MIC_UNAVAILABLE" | "STT_UNSUPPORTED" | "STT_NETWORK" | "STT_FAILED",
    message: string,
  ) {
    super(message);
  }
}

// ------------------------------------------------------------------ mic + level meter
export interface MicSession {
  stream: MediaStream;
  /** Current input level, 0..1 (RMS, lightly scaled). */
  level(): number;
  /** False once the device went away (unplugged, or the laptop slept); open a new session then. */
  alive(): boolean;
  /** True while the browser holds audio back until the page is clicked (no level readings). */
  blocked(): boolean;
  close(): void;
}

export async function openMic(): Promise<MicSession> {
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new SpeechError("MIC_UNAVAILABLE", "This browser can't access a microphone.");
  }
  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      // Mono with auto gain: quiet laptop mics are the most common cause of misheard commands.
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
  } catch (err) {
    const name = (err as DOMException)?.name;
    if (name === "NotAllowedError" || name === "SecurityError") {
      throw new SpeechError("MIC_DENIED", "Microphone access was blocked. Allow it in the browser's site settings.");
    }
    throw new SpeechError("MIC_UNAVAILABLE", "I couldn't find a working microphone.");
  }
  const ctx = tracked(new AudioContext());
  void resumeQuick(ctx);
  const source = ctx.createMediaStreamSource(stream);
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 1024;
  source.connect(analyser);
  const buf = new Float32Array(analyser.fftSize);
  return {
    stream,
    level() {
      analyser.getFloatTimeDomainData(buf);
      let sum = 0;
      for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i];
      return Math.min(1, Math.sqrt(sum / buf.length) * 4);
    },
    alive() {
      return ctx.state !== "closed" && stream.getAudioTracks().some((t) => t.readyState === "live" && t.enabled);
    },
    blocked() {
      return ctx.state === "suspended";
    },
    close() {
      stream.getTracks().forEach((t) => t.stop());
      contexts.delete(ctx);
      void ctx.close();
    },
  };
}

// ------------------------------------------------------------------ local (offline) recording
export interface RecordOptions {
  mic: MicSession;
  signal: AbortSignal;
  onLevel?: (level: number) => void;
  maxMs?: number;
  silenceMs?: number;
  noSpeechMs?: number;
  /** Stop this long after speech starts (wake phrases are short). */
  maxSpeechMs?: number;
}

/** Records one utterance; resolves null when nothing was said or it was aborted. */
export function recordUtterance({
  mic,
  signal,
  onLevel,
  maxMs = 15000,
  // A natural pause mid-sentence is ~1 s; 1.7 s of quiet means you're done.
  silenceMs = 1700,
  noSpeechMs = 6000,
  maxSpeechMs = Infinity,
}: RecordOptions): Promise<Blob | null> {
  return new Promise((resolve, reject) => {
    const mime = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus"].find((m) => MediaRecorder.isTypeSupported(m));
    let recorder: MediaRecorder;
    try {
      recorder = new MediaRecorder(mic.stream, { ...(mime ? { mimeType: mime } : {}), audioBitsPerSecond: 96_000 });
    } catch {
      reject(new SpeechError("STT_FAILED", "Recording isn't supported in this browser."));
      return;
    }
    const chunks: Blob[] = [];
    const started = performance.now();
    let heardSpeech = false;
    let speechStart = 0;
    let lastLoud = started;
    // Background level, tracked continuously from the quiet moments (not just the first instant,
    // which mistook immediate speech for noise and then cut sentences short).
    let ambient = 0.01;
    // setInterval, not requestAnimationFrame: rAF is paused in background tabs, which would stall the wake listener.
    const timer: { id?: ReturnType<typeof setInterval> } = {};
    let finished = false;

    const finish = (keep: boolean) => {
      if (finished) return;
      finished = true;
      clearInterval(timer.id);
      signal.removeEventListener("abort", onAbort);
      recorder.onstop = () => resolve(keep && heardSpeech && chunks.length ? new Blob(chunks, { type: recorder.mimeType || "audio/webm" }) : null);
      if (recorder.state !== "inactive") recorder.stop();
      else resolve(null);
    };
    const onAbort = () => finish(false);
    signal.addEventListener("abort", onAbort);

    recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    recorder.start(250);

    const tick = () => {
      const now = performance.now();
      const level = mic.level();
      onLevel?.(level);
      const threshold = Math.min(0.12, Math.max(0.025, ambient * 3));
      if (level <= threshold) ambient = ambient * 0.97 + level * 0.03;
      if (level > threshold) {
        if (!heardSpeech) speechStart = now;
        heardSpeech = true;
        lastLoud = now;
      }
      if (heardSpeech && now - lastLoud > silenceMs) return finish(true);
      if (heardSpeech && now - speechStart > maxSpeechMs) return finish(true);
      if (!heardSpeech && now - started > noSpeechMs) return finish(false);
      if (now - started > maxMs) return finish(true);
    };
    timer.id = setInterval(tick, 50);
  });
}

// ------------------------------------------------------------------ browser recognition
interface RecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  abort(): void;
}
type RecognitionCtor = new () => RecognitionLike;

export function browserSttSupported(): boolean {
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return Boolean(w.SpeechRecognition ?? w.webkitSpeechRecognition);
}

export function recognizeOnce(signal: AbortSignal, onInterim?: (text: string) => void): Promise<string | null> {
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  const Ctor = w.SpeechRecognition ?? w.webkitSpeechRecognition;
  if (!Ctor) return Promise.reject(new SpeechError("STT_UNSUPPORTED", "This browser has no built-in speech recognition."));
  return new Promise((resolve, reject) => {
    const rec = new Ctor();
    rec.lang = "en-US";
    rec.continuous = false;
    rec.interimResults = true;
    let finalText = "";
    let settled = false;
    const settle = (fn: () => void) => {
      if (!settled) {
        settled = true;
        signal.removeEventListener("abort", onAbort);
        fn();
      }
    };
    const onAbort = () => {
      rec.abort();
      settle(() => resolve(null));
    };
    signal.addEventListener("abort", onAbort);
    rec.onresult = (e) => {
      let interim = "";
      for (let i = 0; i < e.results.length; i++) {
        const r = e.results[i];
        if (r.isFinal) finalText += r[0].transcript;
        else interim += r[0].transcript;
      }
      onInterim?.(finalText + interim);
    };
    rec.onerror = (e) => {
      if (e.error === "no-speech" || e.error === "aborted") return settle(() => resolve(null));
      if (e.error === "not-allowed" || e.error === "service-not-allowed")
        return settle(() => reject(new SpeechError("MIC_DENIED", "Microphone access was blocked. Allow it in the browser's site settings.")));
      if (e.error === "network")
        return settle(() => reject(new SpeechError("STT_NETWORK", "Browser speech recognition needs internet. Switch to offline recognition in settings.")));
      settle(() => reject(new SpeechError("STT_FAILED", `Speech recognition failed (${e.error}).`)));
    };
    rec.onend = () => settle(() => resolve(finalText.trim() || null));
    rec.start();
  });
}

// ------------------------------------------------------------------ text to speech
export type TtsEngine = "local" | "browser";

export interface SpeakOptions {
  /** Preferred engine; "local" falls back to the browser voice if synthesis/playback fails. */
  engine: TtsEngine;
  /** Fetches synthesized WAV audio (backend Piper voice). Required for "local". */
  fetchAudio?: (text: string) => Promise<Blob>;
  onStart?: () => void;
  /** Output level 0..1 while the local voice plays (drives the visualizer). */
  onLevel?: (level: number) => void;
}

export function ttsSupported(): boolean {
  return typeof window !== "undefined" && "speechSynthesis" in window;
}

// Chrome starts every AudioContext "suspended" until the page gets a click or key press (autoplay policy), and
// resume() then never settles. Nothing here may wait on it forever: a blocked context falls back or reports itself.
// The JARVIS launcher opens the app with --autoplay-policy=no-user-gesture-required, so it is never blocked there.
const RESUME_WAIT_MS = 400;
const contexts = new Set<AudioContext>();

function tracked(ctx: AudioContext): AudioContext {
  contexts.add(ctx);
  return ctx;
}

async function resumeQuick(ctx: AudioContext): Promise<boolean> {
  if (ctx.state === "running") return true;
  await Promise.race([ctx.resume().catch(() => undefined), new Promise((r) => setTimeout(r, RESUME_WAIT_MS))]);
  return (ctx.state as AudioContextState) === "running";
}

/** True while the browser is holding audio back until the user interacts with the page. */
export function audioBlocked(): boolean {
  for (const ctx of contexts) if (ctx.state === "suspended") return true;
  return false;
}

/** Resume all audio on the first click or key press. Returns a cleanup function. */
export function installAudioUnlock(onUnlocked?: () => void): () => void {
  const unlock = () => {
    contexts.forEach((ctx) => {
      if (ctx.state === "suspended") void ctx.resume().then(() => onUnlocked?.());
    });
  };
  window.addEventListener("pointerdown", unlock, true);
  window.addEventListener("keydown", unlock, true);
  return () => {
    window.removeEventListener("pointerdown", unlock, true);
    window.removeEventListener("keydown", unlock, true);
  };
}

let audioCtx: AudioContext | null = null;
let currentSource: AudioBufferSourceNode | null = null;
let speakGeneration = 0;

function audioContext(): AudioContext {
  audioCtx ??= tracked(new AudioContext());
  return audioCtx;
}

function pickVoice(): SpeechSynthesisVoice | undefined {
  const voices = window.speechSynthesis.getVoices();
  return (
    voices.find((v) => v.lang.startsWith("en") && v.localService && /male|daniel|david|guy|alex/i.test(v.name)) ??
    voices.find((v) => v.lang.startsWith("en") && v.localService) ??
    voices.find((v) => v.lang.startsWith("en"))
  );
}

function speakBrowser(text: string, onStart?: () => void): Promise<void> {
  if (!ttsSupported()) return Promise.resolve();
  return new Promise((resolve) => {
    const u = new SpeechSynthesisUtterance(text);
    const voice = pickVoice();
    if (voice) u.voice = voice;
    u.rate = 1.03;
    u.pitch = 0.9;
    u.onstart = () => onStart?.();
    u.onend = () => resolve();
    u.onerror = () => resolve();
    window.speechSynthesis.speak(u);
  });
}

function playBuffer(buffer: AudioBuffer, opts: SpeakOptions): Promise<void> {
  const ctx = audioContext();
  const source = ctx.createBufferSource();
  source.buffer = buffer;
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 1024;
  source.connect(analyser);
  analyser.connect(ctx.destination);
  currentSource = source;

  const samples = new Float32Array(analyser.fftSize);
  let raf = 0;
  const meter = () => {
    analyser.getFloatTimeDomainData(samples);
    let sum = 0;
    for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
    opts.onLevel?.(Math.min(1, Math.sqrt(sum / samples.length) * 5));
    raf = requestAnimationFrame(meter);
  };

  return new Promise((resolve) => {
    source.onended = () => {
      cancelAnimationFrame(raf);
      opts.onLevel?.(0);
      if (currentSource === source) currentSource = null;
      resolve();
    };
    opts.onStart?.();
    source.start();
    meter();
  });
}

// ------------------------------------------------------------------ speech queue
// Sentences are synthesized as soon as they are queued and played in order, so the next one is ready when the
// current one ends. Answers start speaking after their first sentence instead of after the whole text.
interface QueueItem {
  text: string;
  opts: SpeakOptions;
  generation: number;
  audio: Promise<AudioBuffer | null> | null;
  done: (engine: TtsEngine | "none") => void;
}

const queue: QueueItem[] = [];
let pumping = false;
const drainWaiters: Array<() => void> = [];

async function synthesize(text: string, opts: SpeakOptions): Promise<AudioBuffer | null> {
  if (!opts.fetchAudio || typeof AudioContext === "undefined") return null;
  try {
    const wav = await opts.fetchAudio(text);
    return await audioContext().decodeAudioData(await wav.arrayBuffer());
  } catch {
    return null; // offline voice unavailable: the browser voice speaks this one
  }
}

async function pump(): Promise<void> {
  pumping = true;
  while (queue.length) {
    const item = queue.shift() as QueueItem;
    if (item.generation !== speakGeneration) {
      item.done("none");
      continue;
    }
    const buffer = item.audio ? await item.audio : null;
    if (item.generation !== speakGeneration) {
      item.done("none");
      continue;
    }
    if (buffer && (await resumeQuick(audioContext()))) {
      await playBuffer(buffer, item.opts);
      item.done(item.generation === speakGeneration ? "local" : "none");
    } else if (ttsSupported()) {
      await speakBrowser(item.text, item.opts.onStart);
      item.done("browser");
    } else {
      item.done("none");
    }
  }
  pumping = false;
  drainWaiters.splice(0).forEach((resolve) => resolve());
}

/** Queue one piece of speech (a sentence or two). Returns when that piece has been spoken or dropped. */
export function enqueueSpeech(text: string, opts: SpeakOptions): Promise<TtsEngine | "none"> {
  const clean = text.trim();
  if (!clean) return Promise.resolve("none");
  return new Promise((done) => {
    const audio = opts.engine === "local" ? synthesize(clean, opts) : null;
    queue.push({ text: clean, opts, generation: speakGeneration, audio, done });
    if (!pumping) void pump();
  });
}

/** Resolves once everything queued so far has been spoken (or stopped). */
export function speechDrained(): Promise<void> {
  return pumping || queue.length ? new Promise((resolve) => drainWaiters.push(resolve)) : Promise.resolve();
}

export function isSpeaking(): boolean {
  return pumping || queue.length > 0;
}

/** Split text into speakable chunks of a sentence or more (very short sentences are grouped). */
export function speechChunks(text: string, minChars = 60): string[] {
  const sentences = text.split(/(?<=[.!?])\s+/).map((x) => x.trim()).filter(Boolean);
  const chunks: string[] = [];
  for (const sentence of sentences) {
    const last = chunks[chunks.length - 1];
    if (last !== undefined && last.length < minChars) chunks[chunks.length - 1] = `${last} ${sentence}`;
    else chunks.push(sentence);
  }
  return chunks;
}

/**
 * Speaks text and resolves when finished or interrupted (never rejects).
 * Returns which engine actually spoke.
 */
export async function speak(text: string, opts: SpeakOptions): Promise<TtsEngine | "none"> {
  const clean = text.trim();
  if (!clean) return "none";
  stopSpeaking();
  const parts = speechChunks(clean);
  const results = await Promise.all((parts.length ? parts : [clean]).map((part) => enqueueSpeech(part, opts)));
  return results.filter((r) => r !== "none").pop() ?? "none";
}

export function stopSpeaking(): void {
  speakGeneration++;
  queue.splice(0).forEach((item) => item.done("none"));
  if (currentSource) {
    try {
      currentSource.stop();
    } catch {
      // already stopped
    }
    currentSource = null;
  }
  if (ttsSupported()) window.speechSynthesis.cancel();
}
