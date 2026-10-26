import { ArrowUp, Mic, Square, VolumeX } from "lucide-react";
import { useEffect, useRef, type FormEvent, type KeyboardEvent } from "react";
import type { AssistantPhase } from "@/features/assistant/types";

interface Props {
  phase: AssistantPhase;
  canListen: boolean;
  onSubmit: (text: string) => void;
  onToggleMic: () => void;
  onStopSpeaking: () => void;
  /** Controlled text, so JARVIS can pre-fill unclear voice input for you to check. */
  value: string;
  onChange: (text: string) => void;
}

const BUSY: AssistantPhase[] = ["THINKING", "EXECUTING", "PROCESSING"];

/** Message composer: Enter sends, Shift+Enter adds a line. */
const CommandBar = ({ phase, canListen, onSubmit, onToggleMic, onStopSpeaking, value: text, onChange: setText }: Props) => {
  const busy = BUSY.includes(phase);
  const listening = phase === "LISTENING";
  const speaking = phase === "SPEAKING";
  const offline = phase === "OFFLINE";

  const inputRef = useRef<HTMLTextAreaElement>(null);
  // When JARVIS pre-fills something it misheard, put the cursor there so it can be fixed straight away.
  useEffect(() => {
    if (text) inputRef.current?.focus();
  }, [text]);

  const send = () => {
    if (!text.trim() || busy || offline) return;
    onSubmit(text.trim());
    setText("");
  };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    send();
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send();
    }
  };

  return (
    <form
      onSubmit={submit}
      className="flex items-end gap-2 rounded-2xl border border-border bg-card p-2 focus-within:border-primary/50"
    >
      <label htmlFor="jarvis-command" className="sr-only">
        Message JARVIS
      </label>
      <textarea
        id="jarvis-command"
        ref={inputRef}
        rows={1}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKey}
        placeholder={offline ? "JARVIS is offline. Start the backend to continue." : "Ask or tell JARVIS…"}
        disabled={offline}
        maxLength={500}
        className="max-h-40 min-h-11 flex-1 resize-none bg-transparent px-3 py-2.5 text-base text-foreground placeholder:text-muted-foreground focus:outline-none disabled:opacity-60 [field-sizing:content]"
      />
      {speaking && (
        <button
          type="button"
          onClick={onStopSpeaking}
          aria-label="Stop speaking"
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl text-muted-foreground hover:bg-secondary hover:text-foreground"
        >
          <VolumeX className="h-5 w-5" />
        </button>
      )}
      <button
        type="button"
        onClick={onToggleMic}
        disabled={!canListen || busy || offline}
        aria-label={listening ? "Stop listening" : "Speak to JARVIS"}
        aria-pressed={listening}
        className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl transition-colors disabled:cursor-not-allowed disabled:opacity-40 ${
          listening ? "bg-primary text-primary-foreground" : "text-primary hover:bg-secondary"
        }`}
      >
        {listening ? <Square className="h-4 w-4 fill-current" /> : <Mic className="h-5 w-5" />}
      </button>
      <button
        type="submit"
        disabled={!text.trim() || busy || offline}
        aria-label="Send"
        className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground transition-opacity disabled:cursor-not-allowed disabled:bg-secondary disabled:text-muted-foreground"
      >
        <ArrowUp className="h-5 w-5" />
      </button>
    </form>
  );
};

export default CommandBar;
