import { afterEach, describe, expect, it, vi } from "vitest";
import { speak, stopSpeaking } from "@/features/assistant/speech";

class FakeUtterance {
  onstart: (() => void) | null = null;
  onend: (() => void) | null = null;
  onerror: (() => void) | null = null;
  voice: unknown = null;
  rate = 1;
  pitch = 1;
  constructor(public text: string) {}
}

function installBrowserVoice() {
  const spoken: string[] = [];
  const synth = {
    getVoices: () => [],
    cancel: vi.fn(),
    speak: (u: FakeUtterance) => {
      spoken.push(u.text);
      u.onstart?.();
      u.onend?.();
    },
  };
  Object.defineProperty(window, "speechSynthesis", { value: synth, configurable: true });
  vi.stubGlobal("SpeechSynthesisUtterance", FakeUtterance);
  return spoken;
}

describe("speak()", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    stopSpeaking();
  });

  it("falls back to the browser voice when the offline voice fails", async () => {
    const spoken = installBrowserVoice();
    vi.stubGlobal(
      "AudioContext",
      class {
        state = "running";
      },
    );
    const onStart = vi.fn();
    const engine = await speak("Hello there", { engine: "local", fetchAudio: () => Promise.reject(new Error("503")), onStart });
    expect(engine).toBe("browser");
    expect(spoken).toEqual(["Hello there"]);
    expect(onStart).toHaveBeenCalled();
  });

  it("uses the browser voice directly when asked", async () => {
    const spoken = installBrowserVoice();
    const fetchAudio = vi.fn();
    expect(await speak("Hi", { engine: "browser", fetchAudio })).toBe("browser");
    expect(fetchAudio).not.toHaveBeenCalled();
    expect(spoken).toEqual(["Hi"]);
  });

  it("says nothing for empty text", async () => {
    installBrowserVoice();
    expect(await speak("   ", { engine: "browser" })).toBe("none");
  });
});

describe("speech queue", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    stopSpeaking();
  });

  it("groups short sentences and keeps decimals intact", async () => {
    const { speechChunks } = await import("@/features/assistant/speech");
    expect(speechChunks("Hi. The answer is 3.5 meters. That is all for now.", 20)).toEqual([
      "Hi. The answer is 3.5 meters.",
      "That is all for now.",
    ]);
  });

  it("speaks queued sentences in order", async () => {
    const { enqueueSpeech, speechDrained } = await import("@/features/assistant/speech");
    const spoken = installBrowserVoice();
    void enqueueSpeech("First sentence.", { engine: "browser" });
    void enqueueSpeech("Second sentence.", { engine: "browser" });
    await speechDrained();
    expect(spoken).toEqual(["First sentence.", "Second sentence."]);
  });

  it("stop drops everything still queued", async () => {
    const { enqueueSpeech, speechDrained } = await import("@/features/assistant/speech");
    const spoken: string[] = [];
    let finish: (() => void) | null = null;
    Object.defineProperty(window, "speechSynthesis", {
      value: {
        getVoices: () => [],
        cancel: () => finish?.(),
        speak: (u: FakeUtterance) => {
          spoken.push(u.text);
          finish = () => u.onend?.(); // still talking until cancelled
        },
      },
      configurable: true,
    });
    vi.stubGlobal("SpeechSynthesisUtterance", FakeUtterance);
    void enqueueSpeech("Talking now.", { engine: "browser" });
    const later = enqueueSpeech("Never said.", { engine: "browser" });
    stopSpeaking();
    expect(await later).toBe("none");
    await speechDrained();
    expect(spoken).toEqual(["Talking now."]);
  });

  it("never waits forever when the browser blocks audio", async () => {
    const spoken = installBrowserVoice();
    vi.stubGlobal(
      "AudioContext",
      class {
        state = "suspended";
        resume = () => new Promise(() => {}); // Chrome without a click: never settles
        decodeAudioData = async () => ({});
      },
    );
    const engine = await speak("Hello there", { engine: "local", fetchAudio: async () => new Blob(["x"]) });
    expect(engine).toBe("browser");
    expect(spoken).toEqual(["Hello there"]);
  });
});
