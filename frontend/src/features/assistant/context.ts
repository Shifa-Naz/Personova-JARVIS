import { createContext, useContext, type MutableRefObject } from "react";
import type { AssistantState } from "./machine";
import type { SttEngine, TtsEngine } from "./speech";

export type SttPreference = "auto" | SttEngine;
export type TtsPreference = "auto" | TtsEngine;

export interface AssistantSettings {
  stt: SttPreference;
  /** Spoken replies on/off. */
  voice: boolean;
  /** Which voice speaks: offline Piper ("local") or the browser/OS voice. */
  tts: TtsPreference;
  /** Listen in the background for "Jarvis, are you up?" (needs offline speech recognition). */
  wake: boolean;
}

export interface AssistantApi {
  state: AssistantState;
  settings: AssistantSettings;
  /** Live mic / voice level 0..1, read by visualizers in their own animation loop (no re-renders). */
  levelRef: MutableRefObject<number>;
  activeStt: SttEngine | null;
  activeTts: TtsEngine | null;
  /** The wake listener can run (setting on and offline recognition available). */
  wakeAvailable: boolean;
  /** The wake listener currently has the microphone open. */
  wakeListening: boolean;
  wakeError: string | null;
  /** Speak arbitrary text with the current voice settings (e.g. boot greeting). */
  say: (text: string) => Promise<void>;
  submit: (text: string, opts?: { fromVoice?: boolean; listenAfter?: boolean }) => Promise<void>;
  listen: () => Promise<void>;
  toggleListening: () => void;
  cancel: () => void;
  decide: (decision: "confirm" | "cancel") => Promise<void>;
  updateSettings: (patch: Partial<AssistantSettings>) => void;
  /** Retry the backend connection now (instead of waiting for the next poll). */
  reconnect: () => void;
  /** Stop the current spoken reply. */
  stopSpeaking: () => void;
  /** Text in the message box; JARVIS puts unclear voice input here for you to check. */
  draft: string;
  setDraft: (text: string) => void;
}

export const AssistantContext = createContext<AssistantApi | null>(null);

export function useAssistant(): AssistantApi {
  const ctx = useContext(AssistantContext);
  if (!ctx) throw new Error("useAssistant must be used inside <AssistantProvider>");
  return ctx;
}
