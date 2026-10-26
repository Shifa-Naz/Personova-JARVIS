/**
 * Wake word handling. Three ways to start:
 *   "Jarvis"                → "Yes?" and JARVIS listens for the command
 *   "Jarvis, are you up?"   → "For you, always ma'am." and JARVIS listens
 *   "Jarvis, <anything>"    → JARVIS does it straight away
 * The name must come first, so "I watched a film with Jarvis in it" doesn't wake it.
 * Detection runs on short bursts of speech transcribed by offline Whisper (see AssistantProvider).
 */

export const WAKE_PHRASE = "Jarvis, are you up?";

// Accept plausible transcription variants of the name, not only the exact spelling.
const NAME = "(?:jarvis|jarvas|jervis|javis|jarviz|jarves)";
const LEAD = new RegExp(`^\\s*(?:(?:hey|ok|okay|hi|hello)[\\s,]+)?${NAME}\\b[\\s,.!?:;-]*(.*)$`, "i");
const ARE_YOU_UP = /^(?:are\s+)?(?:you\s+)?(?:up|awake|there)\b[\s,.!?-]*(.*)$/i;

export interface WakeMatch {
  /** What to send to the backend. */
  utterance: string;
  /** Listen for a command after JARVIS replies (nothing actionable was said yet). */
  listenAfter: boolean;
}

export function matchWake(transcript: string): WakeMatch | null {
  const m = transcript.trim().match(LEAD);
  if (!m) return null;
  const after = m[1].trim();
  if (!after || /^[.!?,\s]*$/.test(after)) return { utterance: "Jarvis", listenAfter: true };
  const up = after.match(ARE_YOU_UP);
  if (up) {
    const rest = up[1].trim();
    return { utterance: rest ? `${WAKE_PHRASE} ${rest}` : WAKE_PHRASE, listenAfter: !rest };
  }
  return { utterance: after, listenAfter: false };
}
