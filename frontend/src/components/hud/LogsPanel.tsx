import { RefreshCw } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { actionName } from "@/features/assistant/actionNames";
import { jarvis } from "@/lib/api";
import type { LogEvent } from "@/features/assistant/types";

const EVENT_LABELS: Record<string, string> = {
  plan: "Planned",
  action: "Ran",
  confirmation_required: "Asked to confirm",
  confirmation: "You answered",
  blocked: "Refused",
  llm_plan_rejected: "Rejected an unsafe plan",
};

/** Recent pipeline events from the backend. Parameters are already redacted server-side. */
const LogsPanel = ({ refreshKey }: { refreshKey: number }) => {
  const [events, setEvents] = useState<LogEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setEvents((await jarvis.logs()).events.slice().reverse());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't load the log.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load, refreshKey]);

  return (
    <div>
      <div className="mb-3 flex items-center justify-between">
        <p className="text-sm text-muted-foreground">What JARVIS did recently, newest first.</p>
        <button
          type="button"
          onClick={() => void load()}
          className="flex h-10 w-10 items-center justify-center rounded-lg text-muted-foreground hover:bg-secondary hover:text-foreground"
          aria-label="Refresh log"
        >
          <RefreshCw className="h-4 w-4" />
        </button>
      </div>
      {error && <p className="text-sm text-jarvis-red">{error}</p>}
      <ol className="max-h-80 divide-y divide-border/70 overflow-y-auto">
        {events.map((e, i) => {
          const failed = e.ok === false || e.msg === "blocked";
          const action = typeof e.action === "string" ? actionName(e.action) : null;
          return (
            <li key={`${e.ts}-${i}`} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 py-2 text-sm">
              <time className="tabular w-20 shrink-0 font-mono text-xs text-muted-foreground">
                {new Date(e.ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
              </time>
              <span className={failed ? "text-jarvis-red" : "text-foreground"}>
                {EVENT_LABELS[e.msg] ?? e.msg}
                {action && ` ${action.toLowerCase()}`}
                {typeof e.intent === "string" && ` (${e.intent.toLowerCase().replace("_", " ")})`}
              </span>
              {typeof e.error_code === "string" && <span className="font-mono text-xs text-jarvis-red">{e.error_code}</span>}
              {typeof e.latency_ms === "number" && (
                <span className="tabular ml-auto font-mono text-xs text-muted-foreground">{e.latency_ms} ms</span>
              )}
            </li>
          );
        })}
        {events.length === 0 && !error && <li className="py-2 text-sm text-muted-foreground">Nothing yet.</li>}
      </ol>
    </div>
  );
};

export default LogsPanel;
