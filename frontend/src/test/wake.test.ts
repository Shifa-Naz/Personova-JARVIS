import { describe, expect, it } from "vitest";
import { matchWake, WAKE_PHRASE } from "@/features/assistant/wake";

describe("wake word", () => {
  it.each(["Jarvis.", "jarvis", "Hey Jarvis!", "Jervis?"])("name alone listens: %s", (heard) => {
    expect(matchWake(heard)).toEqual({ utterance: "Jarvis", listenAfter: true });
  });

  it.each(["Jarvis, are you up?", "jarvis are you up??", "Jervis, are you up?", "Hey Jarvis, are you awake?", "Jarvis, you there?"])(
    "the special phrase: %s",
    (heard) => {
      expect(matchWake(heard)).toEqual({ utterance: WAKE_PHRASE, listenAfter: true });
    },
  );

  it("special phrase plus a command runs the command", () => {
    expect(matchWake("Jarvis, are you up? Open Chrome.")).toEqual({ utterance: `${WAKE_PHRASE} Open Chrome.`, listenAfter: false });
  });

  it.each([
    ["Jarvis, open Chrome and search YouTube for Java tutorials.", "open Chrome and search YouTube for Java tutorials."],
    ["Jarvis what's the time", "what's the time"],
    ["Okay Jarvis, remind me to call mom tomorrow", "remind me to call mom tomorrow"],
  ])("name plus anything does the work: %s", (heard, command) => {
    expect(matchWake(heard)).toEqual({ utterance: command, listenAfter: false });
  });

  it.each(["Are you up?", "I asked Travis if he was up", "I watched a film with Jarvis in it", "Thank you.", "Jarvisville is far", ""])(
    "ignores: %s",
    (heard) => {
      expect(matchWake(heard)).toBeNull();
    },
  );
});
