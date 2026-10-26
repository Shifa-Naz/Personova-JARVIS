import { Check } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import CoreVisualizer from "@/components/hud/CoreVisualizer";
import TelemetryPanel from "@/components/hud/TelemetryPanel";
import { useAssistant } from "@/features/assistant/context";
import { useItems } from "@/hooks/use-items";
import { useTelemetry } from "@/hooks/use-telemetry";
import { friendlyDate, friendlyTime, localDateString, type CalEvent, type Task } from "@/lib/storage";

const TRY = [
  "What's on my calendar this week?",
  "Remember that I prefer C++",
  "Open Chrome and search YouTube for Java DSA tutorials",
  "Copy report.pdf to Documents",
];

function greeting(now: Date): string {
  const h = now.getHours();
  if (h < 5) return "Working late";
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

const Index = () => {
  const { state, levelRef, submit, reconnect } = useAssistant();
  const navigate = useNavigate();
  const telemetry = useTelemetry();
  const tasks = useItems<Task>("tasks");
  const events = useItems<CalEvent>("events");
  const now = new Date();
  const today = localDateString(now);
  const weekAhead = localDateString(new Date(now.getFullYear(), now.getMonth(), now.getDate() + 7));

  const open = tasks.items.filter((t) => !t.completed);
  const dueSoon = open
    .filter((t) => t.due && t.due <= today)
    .concat(open.filter((t) => !t.due || t.due > today))
    .slice(0, 6);
  const upcoming = events.items
    .filter((e) => e.date >= today && e.date <= weekAhead)
    .sort((a, b) => (a.date + (a.time || "")).localeCompare(b.date + (b.time || "")))
    .slice(0, 5);

  const ask = (text: string) => {
    navigate("/assistant");
    void submit(text);
  };

  return (
    <div className="mx-auto max-w-7xl px-4 pb-20 pt-24 sm:px-6 lg:px-8">
      <section className="grid grid-cols-1 items-center gap-10 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
        <div className="order-2 lg:order-1">
          <p className="text-muted-foreground">
            {now.toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })}
          </p>
          <h1 className="mt-2 font-display text-5xl font-semibold leading-[1.05] text-foreground sm:text-6xl">
            {greeting(now)}.
          </h1>
          <p className="mt-4 max-w-xl text-lg leading-relaxed text-foreground/80">
            {state.connected
              ? open.length
                ? `You have ${open.length} open ${open.length === 1 ? "task" : "tasks"} and ${upcoming.length} ${
                    upcoming.length === 1 ? "event" : "events"
                  } this week. Press Space and tell me what you need.`
                : "Your list is clear. Press Space and tell me what you need."
              : "I can't reach my backend. Start it with python run.py, then try again."}
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              to="/assistant"
              className="inline-flex min-h-12 items-center rounded-xl bg-primary px-6 font-medium text-primary-foreground hover:bg-primary/90"
            >
              Open the console
            </Link>
            {!state.connected && (
              <button
                type="button"
                onClick={reconnect}
                className="inline-flex min-h-12 items-center rounded-xl border border-border px-6 text-foreground hover:border-primary/60"
              >
                Try again
              </button>
            )}
          </div>
        </div>
        <div className="core-boot order-1 mx-auto w-[min(70vw,340px)] lg:order-2">
          <CoreVisualizer phase={state.phase} levelRef={levelRef} size={340} className="h-auto w-full" />
        </div>
      </section>

      <section className="mt-16 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="panel p-5 lg:col-span-1">
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="text-lg font-semibold">Tasks</h2>
            <Link to="/tasks" className="text-sm text-muted-foreground hover:text-foreground">
              See all
            </Link>
          </div>
          {dueSoon.length === 0 ? (
            <p className="text-muted-foreground">Nothing open. Try “remind me to call mom tomorrow”.</p>
          ) : (
            <ul className="divide-y divide-border/70">
              {dueSoon.map((t) => {
                const overdue = t.due && t.due < today;
                return (
                  <li key={t.id} className="flex items-center gap-3 py-2">
                    <button
                      type="button"
                      onClick={() => void tasks.update(t.id, { completed: true })}
                      aria-label={`Mark “${t.title}” done`}
                      className="group flex h-6 w-6 shrink-0 items-center justify-center rounded-md border border-border hover:border-primary"
                    >
                      <Check className="h-3.5 w-3.5 opacity-0 transition-opacity group-hover:opacity-100" />
                    </button>
                    <span className="min-w-0 flex-1 truncate">{t.title}</span>
                    {t.due && (
                      <span className={`shrink-0 text-sm ${overdue ? "text-jarvis-ember" : "text-muted-foreground"}`}>
                        {overdue ? "Overdue" : friendlyDate(t.due)}
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div className="panel p-5 lg:col-span-1">
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="text-lg font-semibold">This week</h2>
            <Link to="/calendar" className="text-sm text-muted-foreground hover:text-foreground">
              Calendar
            </Link>
          </div>
          {upcoming.length === 0 ? (
            <p className="text-muted-foreground">No events. Try “schedule team sync on Friday at 4 pm”.</p>
          ) : (
            <ul className="space-y-3">
              {upcoming.map((e) => (
                <li key={e.id} className="flex gap-3">
                  <span className="w-24 shrink-0 text-sm text-muted-foreground">
                    {friendlyDate(e.date)}
                    {e.time && <span className="block text-foreground/80">{friendlyTime(e.time)}</span>}
                  </span>
                  <span className="min-w-0 flex-1">{e.title}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="panel p-5 lg:col-span-1">
          <h2 className="mb-3 text-lg font-semibold">Try saying</h2>
          <ul className="space-y-1">
            {TRY.map((t) => (
              <li key={t}>
                <button
                  type="button"
                  onClick={() => ask(t)}
                  disabled={!state.connected}
                  className="min-h-11 w-full rounded-lg px-3 text-left text-foreground/90 hover:bg-secondary hover:text-foreground disabled:opacity-50"
                >
                  “{t}”
                </button>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="panel mt-6 p-5">
        <h2 className="mb-4 text-lg font-semibold">This computer</h2>
        <TelemetryPanel data={telemetry} />
      </section>
    </div>
  );
};

export default Index;
