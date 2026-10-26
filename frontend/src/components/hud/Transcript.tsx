import { useEffect, useRef } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import PlanSteps from "@/components/hud/PlanSteps";
import type { ChatMessage, StepView } from "@/features/assistant/types";

const SUGGESTIONS = [
  "What's on my screen?",
  "Remind me to submit the report tomorrow at 5 pm",
  "Search YouTube for lo-fi music",
  "Explain recursion with an example",
];

interface Props {
  messages: ChatMessage[];
  /** The plan currently executing (shown live under a pending JARVIS turn). */
  livePlan: StepView[];
  busy: boolean;
  /** Answer text arriving while the model is still writing. */
  streamText?: string;
  onSuggest: (text: string) => void;
}

const time = (ts: number) => new Date(ts).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });

const Transcript = ({ messages, livePlan, busy, streamText = "", onSuggest }: Props) => {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages.length, busy, streamText]);

  if (messages.length === 0) {
    return (
      <div className="flex h-full flex-col justify-end gap-4 pb-2">
        <div>
          <p className="font-display text-2xl font-semibold text-foreground">How can I help?</p>
          <p className="mt-1 max-w-prose text-muted-foreground">
            Ask a question, or tell me to do something on this computer. I'll show you the plan, and I'll ask before
            anything that can't be undone.
          </p>
        </div>
        <ul className="flex flex-wrap gap-2" aria-label="Suggestions">
          {SUGGESTIONS.map((s) => (
            <li key={s}>
              <button
                type="button"
                onClick={() => onSuggest(s)}
                className="min-h-11 rounded-full border border-border px-4 text-sm text-foreground/90 transition-colors hover:border-primary/60 hover:text-foreground"
              >
                {s}
              </button>
            </li>
          ))}
        </ul>
      </div>
    );
  }

  return (
    <ol className="flex flex-col gap-5" aria-label="Conversation" aria-live="polite">
      {messages.map((m) =>
        m.role === "user" ? (
          <li key={m.id} className="flex justify-end">
            <div className="max-w-[85%] rounded-2xl rounded-br-md bg-secondary px-4 py-2.5 text-foreground">
              <p className="whitespace-pre-wrap break-words">{m.text}</p>
              <p className="mt-1 text-right text-xs text-muted-foreground">{time(m.ts)}</p>
            </div>
          </li>
        ) : (
          <li key={m.id} className="flex gap-3">
            <span
              aria-hidden
              className={`mt-2 h-2 w-2 shrink-0 rounded-full ${
                m.tone === "error" ? "bg-jarvis-red" : m.tone === "question" ? "bg-jarvis-ember" : "bg-primary"
              }`}
            />
            <div className="min-w-0 max-w-[92%] flex-1">
              <div className={`prose-jarvis break-words ${m.tone === "error" ? "text-jarvis-red" : ""}`}>
                <ReactMarkdown
                  remarkPlugins={[remarkGfm]}
                  components={{
                    a: ({ href, children }) => (
                      <a href={href} target="_blank" rel="noreferrer noopener">
                        {children}
                      </a>
                    ),
                  }}
                >
                  {m.text}
                </ReactMarkdown>
              </div>
              {m.plan && <PlanSteps steps={m.plan} results={m.results} confidence={m.confidence} source={m.source} />}
              <p className="mt-1.5 text-xs text-muted-foreground">JARVIS, {time(m.ts)}</p>
            </div>
          </li>
        ),
      )}
      {busy && (
        <li className="flex gap-3">
          <span aria-hidden className="mt-2 h-2 w-2 shrink-0 animate-pulse rounded-full bg-jarvis-ember" />
          <div className="min-w-0 flex-1">
            {streamText ? (
              <div className="prose-jarvis break-words">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{streamText}</ReactMarkdown>
              </div>
            ) : (
              <>
                <p className="text-muted-foreground">{livePlan.length ? "Working on it" : "Thinking"}</p>
                {livePlan.length > 0 && <PlanSteps steps={livePlan} pending />}
              </>
            )}
          </div>
        </li>
      )}
      <div ref={endRef} />
    </ol>
  );
};

export default Transcript;
