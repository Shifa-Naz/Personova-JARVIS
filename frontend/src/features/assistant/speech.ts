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
  const ctx = new AudioContext();
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
    close() {
      stream.getTracks().forEach((t) => t.stop());
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

let audioCtx: AudioContext | null = null;
let currentSource: AudioBufferSourceNode | null = null;
let speakGeneration = 0;

function audioContext(): AudioContext {
  audioCtx ??= new AudioContext();
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
    window.speechSynthesis.cancel();
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

async function speakLocal(text: string, opts: SpeakOptions, generation: number): Promise<"played" | "cancelled"> {
  if (!opts.fetchAudio) throw new Error("no audio source");
  const ctx = audioContext();
  if (ctx.state === "suspended") await ctx.resume();
  const wav = await opts.fetchAudio(text);
  if (generation !== speakGeneration) return "cancelled"; // interrupted while synthesizing
  const buffer = await ctx.decodeAudioData(await wav.arrayBuffer());
  if (generation !== speakGeneration) return "cancelled";

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
      resolve("played");
    };
    opts.onStart?.();
    source.start();
    meter();
  });
}

/**
 * Speaks text and resolves when finished or interrupted (never rejects).
 * Returns which engine actually spoke.
 */
export async function speak(text: string, opts: SpeakOptions): Promise<TtsEngine | "none"> {
  const clean = text.trim();
  if (!clean) return "none";
  stopSpeaking();
  const generation = ++speakGeneration;
  if (opts.engine === "local" && typeof AudioContext !== "undefined") {
    try {
      const outcome = await speakLocal(clean, opts, generation);
      return outcome === "played" ? "local" : "none";
    } catch {
      if (generation !== speakGeneration) return "none";
      // Offline voice unavailable or audio failed: fall back to the browser's voice.
    }
  }
  if (!ttsSupported()) return "none";
  await speakBrowser(clean, opts.onStart);
  return "browser";
}

export function stopSpeaking(): void {
  speakGeneration++;
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
