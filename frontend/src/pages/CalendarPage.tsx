import { ChevronLeft, ChevronRight, Pencil, Trash2 } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { toast } from "sonner";
import PageHeader from "@/components/PageHeader";
import { useItems } from "@/hooks/use-items";
import { friendlyDate, friendlyTime, localDateString, type CalEvent } from "@/lib/storage";

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const REMINDER_KEY = "jarvis_reminded_for";
const field =
  "min-h-11 rounded-lg border border-border bg-background px-3 text-base text-foreground placeholder:text-muted-foreground focus:border-primary/60 focus:outline-none";

const EventRow = ({ ev, onSave, onDelete }: { ev: CalEvent; onSave: (p: Partial<CalEvent>) => void; onDelete: () => void }) => {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(ev.title);
  const [date, setDate] = useState(ev.date);
  const [time, setTime] = useState(ev.time || "");
  const [confirming, setConfirming] = useState(false);

  if (editing) {
    return (
      <li className="py-3">
        <form
          className="space-y-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!title.trim() || !date) return;
            onSave({ title: title.trim(), date, time });
            setEditing(false);
          }}
        >
          <input value={title} onChange={(e) => setTitle(e.target.value)} className={`${field} w-full`} aria-label="Event title" autoFocus />
          <div className="flex gap-2">
            <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className={`${field} flex-1`} aria-label="Date" />
            <input type="time" value={time} onChange={(e) => setTime(e.target.value)} className={field} aria-label="Time" />
          </div>
          <div className="flex gap-2">
            <button type="submit" className="min-h-11 rounded-lg bg-primary px-4 font-medium text-primary-foreground">
              Save
            </button>
            <button type="button" onClick={() => setEditing(false)} className="min-h-11 rounded-lg px-4 text-muted-foreground hover:text-foreground">
              Cancel
            </button>
          </div>
        </form>
      </li>
    );
  }
  return (
    <li className="flex items-start gap-3 py-2.5">
      <span className="tabular w-20 shrink-0 pt-0.5 text-sm text-muted-foreground">{ev.time ? friendlyTime(ev.time) : "All day"}</span>
      <span className="min-w-0 flex-1 break-words text-foreground">{ev.title}</span>
      {confirming ? (
        <span className="flex gap-1">
          <button type="button" onClick={onDelete} className="min-h-10 rounded-lg px-3 text-sm text-jarvis-red hover:bg-jarvis-red/10">
            Delete
          </button>
          <button type="button" onClick={() => setConfirming(false)} className="min-h-10 rounded-lg px-3 text-sm text-muted-foreground">
            Keep
          </button>
        </span>
      ) : (
        <span className="flex">
          <button type="button" onClick={() => setEditing(true)} aria-label={`Edit ${ev.title}`} className="flex h-10 w-10 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground">
            <Pencil className="h-4 w-4" />
          </button>
          <button type="button" onClick={() => setConfirming(true)} aria-label={`Delete ${ev.title}`} className="flex h-10 w-10 items-center justify-center rounded-lg text-muted-foreground hover:text-jarvis-red">
            <Trash2 className="h-4 w-4" />
          </button>
        </span>
      )}
    </li>
  );
};

const CalendarPage = () => {
  const { items: events, offline, error, create, update, remove } = useItems<CalEvent>("events");
  const [cursor, setCursor] = useState(() => new Date());
  const today = localDateString(new Date());
  const [selected, setSelected] = useState(today);
  const [title, setTitle] = useState("");
  const [time, setTime] = useState("");

  // One reminder a day about tomorrow's events (local date, not UTC; no repeats on re-render).
  useEffect(() => {
    const t = new Date();
    t.setDate(t.getDate() + 1);
    const tomorrow = localDateString(t);
    const due = events.filter((e) => e.date === tomorrow);
    if (!due.length) return;
    let already = "";
    try {
      already = localStorage.getItem(REMINDER_KEY) ?? "";
    } catch {
      already = "";
    }
    if (already === tomorrow) return;
    toast(`Tomorrow: ${due.map((e) => e.title).join(", ")}`);
    try {
      localStorage.setItem(REMINDER_KEY, tomorrow);
    } catch {
      // the reminder may repeat next visit; harmless
    }
  }, [events]);

  const year = cursor.getFullYear();
  const month = cursor.getMonth();
  const lead = (new Date(year, month, 1).getDay() + 6) % 7; // weeks start on Monday
  const days = new Date(year, month + 1, 0).getDate();
  const cells: (number | null)[] = [...Array(lead).fill(null), ...Array.from({ length: days }, (_, i) => i + 1)];
  const ds = (d: number) => localDateString(new Date(year, month, d));
  const dayEvents = events.filter((e) => e.date === selected).sort((a, b) => (a.time || "").localeCompare(b.time || ""));

  const add = (e: FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    void create({ title: title.trim(), date: selected, time });
    setTitle("");
    setTime("");
  };

  return (
    <div className="mx-auto max-w-6xl px-4 pb-28 pt-24 sm:px-6 lg:px-8">
      <PageHeader
        title="Calendar"
        lead="Pick a day to see or add events, or say “schedule team sync next Friday at 4 pm”."
        offline={offline}
        error={error}
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <section className="panel p-4 sm:p-5" aria-label="Month">
          <div className="mb-4 flex items-center justify-between">
            <button type="button" onClick={() => setCursor(new Date(year, month - 1, 1))} aria-label="Previous month" className="flex h-11 w-11 items-center justify-center rounded-lg hover:bg-secondary">
              <ChevronLeft className="h-5 w-5" />
            </button>
            <h2 className="text-xl font-semibold">{cursor.toLocaleDateString(undefined, { month: "long", year: "numeric" })}</h2>
            <button type="button" onClick={() => setCursor(new Date(year, month + 1, 1))} aria-label="Next month" className="flex h-11 w-11 items-center justify-center rounded-lg hover:bg-secondary">
              <ChevronRight className="h-5 w-5" />
            </button>
          </div>
          <div className="grid grid-cols-7 gap-1 text-center">
            {WEEKDAYS.map((d) => (
              <div key={d} className="pb-1 text-xs text-muted-foreground">
                {d}
              </div>
            ))}
            {cells.map((day, i) => {
              if (day === null) return <div key={`b-${i}`} />;
              const key = ds(day);
              const count = events.filter((e) => e.date === key).length;
              const isSel = key === selected;
              const isToday = key === today;
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => setSelected(key)}
                  aria-pressed={isSel}
                  aria-label={`${friendlyDate(key)}${count ? `, ${count} ${count === 1 ? "event" : "events"}` : ""}`}
                  className={`tabular relative flex aspect-square max-h-16 min-h-11 w-full flex-col items-center justify-center justify-self-center rounded-lg text-sm transition-colors ${
                    isSel ? "bg-primary font-semibold text-primary-foreground" : isToday ? "text-primary ring-1 ring-primary/50" : "text-foreground hover:bg-secondary"
                  }`}
                >
                  {day}
                  {count > 0 && <span className={`absolute bottom-1.5 h-1 w-1 rounded-full ${isSel ? "bg-primary-foreground" : "bg-jarvis-ember"}`} />}
                </button>
              );
            })}
          </div>
        </section>

        <section className="panel p-4 sm:p-5" aria-label="Selected day">
          <h2 className="text-xl font-semibold">{friendlyDate(selected)}</h2>
          <p className="text-sm text-muted-foreground">
            {new Date(`${selected}T00:00`).toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" })}
          </p>
          <ul className="mt-3 divide-y divide-border/70">
            {dayEvents.map((ev) => (
              <EventRow key={ev.id} ev={ev} onSave={(p) => void update(ev.id, p)} onDelete={() => void remove(ev.id)} />
            ))}
            {dayEvents.length === 0 && <li className="py-3 text-muted-foreground">Nothing planned.</li>}
          </ul>
          <form onSubmit={add} className="mt-4 space-y-2 border-t border-border pt-4">
            <label htmlFor="event-title" className="sr-only">
              Event title
            </label>
            <input id="event-title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Add an event on this day" maxLength={200} className={`${field} w-full`} />
            <div className="flex gap-2">
              <input type="time" value={time} onChange={(e) => setTime(e.target.value)} className={`${field} flex-1`} aria-label="Time (optional)" />
              <button type="submit" disabled={!title.trim() || offline} className="min-h-11 rounded-lg bg-primary px-5 font-medium text-primary-foreground disabled:bg-secondary disabled:text-muted-foreground">
                Add
              </button>
            </div>
          </form>
        </section>
      </div>
    </div>
  );
};

export default CalendarPage;
