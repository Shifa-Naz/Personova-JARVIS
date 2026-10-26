import { Check, Loader2, ShieldAlert, X } from "lucide-react";
import { actionName } from "@/features/assistant/actionNames";
import { friendlyDate, friendlyTime } from "@/lib/storage";
import type { Permission, StepResult, StepView } from "@/features/assistant/types";

/** What each permission level means to the user, and how it is marked. */
const RISK: Record<Permission, { label: string; className: string }> = {
  READ_ONLY: { label: "Reads only", className: "text-muted-foreground" },
  SAFE: { label: "Safe", className: "text-jarvis-ember" },
  SENSITIVE: { label: "Asks first", className: "text-jarvis-ember" },
  DESTRUCTIVE: { label: "Asks first, can't undo", className: "text-jarvis-red" },
  BLOCKED: { label: "Not allowed", className: "text-jarvis-red" },
};

// The thing being acted on first ("Dentist"), then when/where, so the card reads like a sentence.
const PARAM_ORDER = ["title", "text", "name", "query", "app", "url", "question", "known", "folder", "destination",
  "new_name", "date", "due", "time", "due_time", "priority", "command", "value", "topic", "mode", "range", "filter"];
const HIDDEN = new Set(["browser", "kind", "overwrite", "src_path", "dest_path", "path", "all_in_folder", "latest"]);

const formatValue = (key: string, v: string) => {
  if ((key === "date" || key === "due") && /^\d{4}-\d{2}-\d{2}$/.test(v)) return friendlyDate(v);
  if ((key === "time" || key === "due_time") && /^\d{2}:\d{2}$/.test(v)) return friendlyTime(v);
  if (key === "priority") return `${v} priority`;
  return v;
};

const describeParams = (params: Record<string, unknown>) =>
  Object.entries(params)
    .filter(([k, v]) => !HIDDEN.has(k) && (typeof v === "string" || typeof v === "number") && String(v) && v !== "[redacted]")
    .sort(([a], [b]) => (PARAM_ORDER.indexOf(a) + 100) % 100 - (PARAM_ORDER.indexOf(b) + 100) % 100)
    .map(([k, v]) => formatValue(k, String(v)))
    .join(", ");

interface Props {
  steps: StepView[];
  results?: StepResult[];
  /** Steps still running (shown while the request is in flight). */
  pending?: boolean;
  confidence?: number | null;
  source?: "rules" | "llm" | null;
}

/** The plan JARVIS executed for a turn: an ordered list, so numbering carries meaning here. */
const PlanSteps = ({ steps, results = [], pending = false, confidence, source }: Props) => {
  if (steps.length === 0) return null;
  const trivial = steps.length === 1 && ["reply", "answer_question", "calculate"].includes(steps[0].action);
  if (trivial && !pending) return null;

  return (
    <div className="mt-3 rounded-lg border border-border/80 bg-background/40">
      <ol className="divide-y divide-border/70">
        {steps.map((s, i) => {
          const r = results[i];
          const risk = RISK[s.permission];
          const detail = describeParams(s.params);
          return (
            <li key={`${s.action}-${i}`} className="flex items-start gap-3 px-3 py-2">
              <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center">
                {r ? (
                  r.ok ? (
                    <Check className="h-4 w-4 text-jarvis-green" aria-label="Done" />
                  ) : (
                    <X className="h-4 w-4 text-jarvis-red" aria-label="Failed" />
                  )
                ) : pending ? (
                  <Loader2 className="h-4 w-4 animate-spin text-jarvis-ember" aria-label="Running" />
                ) : s.permission === "SENSITIVE" || s.permission === "DESTRUCTIVE" ? (
                  <ShieldAlert className="h-4 w-4 text-jarvis-ember" aria-label="Waiting for you" />
                ) : (
                  <span className="tabular text-sm text-muted-foreground">{i + 1}</span>
                )}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-foreground">
                  {actionName(s.action)}
                  {detail && <span className="font-normal text-muted-foreground"> — {detail}</span>}
                </p>
                {r && !r.ok && r.message && <p className="text-sm text-jarvis-red">{r.message}</p>}
              </div>
              <span className={`shrink-0 text-xs ${risk.className}`}>{risk.label}</span>
            </li>
          );
        })}
      </ol>
      {source === "llm" && confidence != null && (
        <p className="border-t border-border/70 px-3 py-1.5 text-xs text-muted-foreground">
          Planned by the offline model, {Math.round(confidence * 100)}% sure
        </p>
      )}
    </div>
  );
};

export default PlanSteps;
