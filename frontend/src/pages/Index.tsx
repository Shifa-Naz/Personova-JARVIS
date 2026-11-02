import { useEffect, useState } from "react";
import { Check } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Link, useNavigate } from "react-router-dom";
import CoreVisualizer from "@/components/hud/CoreVisualizer";
import TelemetryPanel from "@/components/hud/TelemetryPanel";
import { useAssistant } from "@/features/assistant/context";
import { useItems } from "@/hooks/use-items";
import { useNews } from "@/hooks/use-news";
import { useTelemetry } from "@/hooks/use-telemetry";
import { friendlyDate, friendlyTime, localDateString, type CalEvent, type Task } from "@/lib/storage";

const TRY = [
  "Brief me",
  "What's on my screen?",
  "Which apps are using the most CPU?",
  "Open YouTube and search for Java DSA tutorials",
];

const gb = (n: number) => `${(n / 1024 ** 3).toFixed(1)} GB`;

function uptime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  if (h >= 24) return `${Math.floor(h / 24)} d ${h % 24} h`;
  return h ? `${h} h ${m} min` : `${m} min`;
}

/** Re-renders every second for the live clock. */
function useNow(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  return now;
}

function greeting(now: Date): string {
  const h = now.getHours();
  if (h < 5) return "Working late";
  if (h < 12) return "Good morning";
  if (h < 17) return "Good afternoon";
  return "Good evening";
}

const Index = () => {
  const { state, levelRef, submit, reconnect, briefing, requestBriefing } = useAssistant();
  const navigate = useNavigate();
  const telemetry = useTelemetry(3000, true);
  const news = useNews(5);
  const tasks = useItems<Task>("tasks");
  const events = useItems<CalEvent>("events");
  const now = useNow();
  const today = localDateString(now);
  const weekAhead = localDateString(new Date(now.getFullYear(), now.getMonth(), now.getDate() + 7));

  const open = tasks.items.filter((t) => !t.completed);
  const dueSoon = open
    .filter((t) => t.due && t.due <= today)
    .concat(open.filter((t) => !t.due || t.due > today))
    .slice(0, 6);
  const todayEvents = events.items
    .filter((e) => e.date === today)
    .sort((a, b) => (a.time || "99").localeCompare(b.time || "99"));
  const dueToday = open.filter((t) => t.due === today);
  const nowHM = now.toTimeString().slice(0, 5);
  const overdue = open.filter((t) => t.due && t.due < today);
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
            <span className="tabular ml-3 font-display text-foreground/90">
              {now.toLocaleTimeString([], { hour: "numeric", minute: "2-digit", second: "2-digit" })}
            </span>
          </p>
          <h1 className="mt-2 font-display text-5xl font-semibold leading-[1.05] text-foreground sm:text-6xl">
            {greeting(now)}.
          </h1>
          <p className="mt-4 max-w-xl text-lg leading-relaxed text-foreground/80">
            {state.connected
              ? open.length
                ? `You have ${open.length} open ${open.length === 1 ? "task" : "tasks"} and ${upcoming.length} ${
                    upcoming.length === 1 ? "event" : "events"
                  } this week. Say “Jarvis” and tell me what you need.`
                : "Your list is clear. Say “Jarvis” and tell me what you need."
              : "I can't reach my backend. Start it with python run.py, then try again."}
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link
              to="/assistant"
              className="inline-flex min-h-12 items-center rounded-xl bg-primary px-6 font-medium text-primary-foreground hover:bg-primary/90"
            >
              Open the console
            </Link>
            {state.connected && (
              <button
                type="button"
                onClick={() => void requestBriefing()}
                className="inline-flex min-h-12 items-center rounded-xl border border-border px-6 text-foreground hover:border-primary/60"
              >
                Brief me
              </button>
            )}
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

      {briefing && (
        <section className="panel mt-16 p-5" aria-label="Latest briefing">
          <div className="mb-2 flex items-baseline justify-between gap-3">
            <h2 className="text-lg font-semibold">Your briefing</h2>
            <span className="text-sm text-muted-foreground">
              {new Date(briefing.at).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" })}
            </span>
          </div>
          <div className="prose-jarvis break-words">
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
              {briefing.reply}
            </ReactMarkdown>
          </div>
        </section>
      )}

      <section className={`${briefing ? "mt-6" : "mt-16"} grid grid-cols-1 gap-6 lg:grid-cols-3`}>
        <div className="panel p-5">
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="text-lg font-semibold">Today</h2>
            <Link to="/calendar" className="text-sm text-muted-foreground hover:text-foreground">
              Calendar
            </Link>
          </div>
          {todayEvents.length === 0 && dueToday.length === 0 && overdue.length === 0 ? (
            <p className="text-muted-foreground">Nothing scheduled today. Try “schedule team sync today at 4 pm”.</p>
          ) : (
            <ul className="space-y-3">
              {todayEvents.map((e) => {
                const past = Boolean(e.time) && e.time < nowHM;
                return (
                  <li key={e.id} className={`flex gap-3 ${past ? "opacity-60" : ""}`}>
                    <span className="tabular w-20 shrink-0 text-sm text-muted-foreground">{e.time ? friendlyTime(e.time) : "All day"}</span>
                    <span className="min-w-0 flex-1">{e.title}</span>
                  </li>
                );
              })}
              {dueToday.map((t) => (
                <li key={t.id} className="flex gap-3">
                  <span className="w-20 shrink-0 text-sm text-muted-foreground">Due</span>
                  <span className="min-w-0 flex-1">{t.title}</span>
                </li>
              ))}
              {overdue.map((t) => (
                <li key={t.id} className="flex gap-3">
                  <span className="w-20 shrink-0 text-sm text-jarvis-ember">Overdue</span>
                  <span className="min-w-0 flex-1">{t.title}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="panel p-5 lg:col-span-2">
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="text-lg font-semibold">Tech news</h2>
            <button type="button" onClick={() => ask("Latest tech news")} className="text-sm text-muted-foreground hover:text-foreground" disabled={!state.connected}>
              Read them to me
            </button>
          </div>
          {news.loading ? (
            <p className="text-muted-foreground">Getting the latest headlines…</p>
          ) : news.items.length === 0 ? (
            <p className="text-muted-foreground">{news.error ?? "No headlines right now."}</p>
          ) : (
            <ol className="space-y-2.5">
              {news.items.map((h) => (
                <li key={h.url} className="min-w-0">
                  <a href={h.url} target="_blank" rel="noreferrer noopener" className="text-foreground hover:text-primary">
                    {h.title}
                  </a>
                  <span className="ml-2 text-sm text-muted-foreground">{h.source}</span>
                </li>
              ))}
            </ol>
          )}
        </div>
      </section>

      <section className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
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
        <div className="mb-4 flex items-baseline justify-between gap-3">
          <h2 className="text-lg font-semibold">This computer</h2>
          {telemetry && <span className="text-sm text-muted-foreground">On for {uptime(telemetry.uptime_s)}, updated live</span>}
        </div>
        <TelemetryPanel data={telemetry} />
        {telemetry?.processes && telemetry.processes.length > 0 && (
          <div className="mt-6">
            <h3 className="mb-2 text-sm font-medium text-muted-foreground">Busiest apps</h3>
            <ul className="divide-y divide-border/70">
              {telemetry.processes.map((p) => (
                <li key={p.name} className="flex items-center gap-3 py-1.5 text-sm">
                  <span className="min-w-0 flex-1 truncate text-foreground">{p.name}</span>
                  <span className="tabular w-20 text-right text-muted-foreground">CPU {p.cpu_percent.toFixed(0)}%</span>
                  <span className="tabular w-24 text-right text-muted-foreground">{gb(p.memory)}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </section>
    </div>
  );
};

export default Index;
