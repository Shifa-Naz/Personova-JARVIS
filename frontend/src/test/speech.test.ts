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
