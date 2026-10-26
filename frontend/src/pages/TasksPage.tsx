import { Check, Pencil, Trash2, Undo2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import PageHeader from "@/components/PageHeader";
import { useItems } from "@/hooks/use-items";
import { friendlyDate, friendlyTime, localDateString, type Task } from "@/lib/storage";

type Priority = Task["priority"];
const PRIORITY_LABEL: Record<Priority, string> = { high: "High", medium: "Normal", low: "Low" };

const field =
  "min-h-11 rounded-lg border border-border bg-background px-3 text-base text-foreground placeholder:text-muted-foreground focus:border-primary/60 focus:outline-none";

function groupOf(t: Task, today: string): string {
  if (t.completed) return "Done";
  if (!t.due) return "No date";
  if (t.due < today) return "Overdue";
  if (t.due === today) return "Today";
  return "Upcoming";
}
const ORDER = ["Overdue", "Today", "Upcoming", "No date", "Done"];
/** "Today"/"Tomorrow" read as words mid-sentence; real dates keep their capitals. */
const relative = (s: string) => (["Today", "Tomorrow", "Yesterday"].includes(s) ? s.toLowerCase() : s);

const TaskRow = ({
  task,
  today,
  onToggle,
  onSave,
  onDelete,
}: {
  task: Task;
  today: string;
  onToggle: () => void;
  onSave: (patch: Partial<Task>) => void;
  onDelete: () => void;
}) => {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(task.title);
  const [due, setDue] = useState(task.due ?? "");
  const [priority, setPriority] = useState<Priority>(task.priority ?? "medium");
  const [confirming, setConfirming] = useState(false);
  const overdue = !task.completed && task.due && task.due < today;

  if (editing) {
    return (
      <li className="py-3">
        <form
          className="flex flex-col gap-2 sm:flex-row"
          onSubmit={(e) => {
            e.preventDefault();
            if (!title.trim()) return;
            onSave({ title: title.trim(), due: due || null, priority });
            setEditing(false);
          }}
        >
          <label className="sr-only" htmlFor={`t-${task.id}`}>
            Task
          </label>
          <input id={`t-${task.id}`} value={title} onChange={(e) => setTitle(e.target.value)} className={`${field} flex-1`} autoFocus />
          <input type="date" value={due} onChange={(e) => setDue(e.target.value)} className={field} aria-label="Due date" />
          <select value={priority} onChange={(e) => setPriority(e.target.value as Priority)} className={field} aria-label="Priority">
            <option value="high">High</option>
            <option value="medium">Normal</option>
            <option value="low">Low</option>
          </select>
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
    <li className="group flex items-center gap-3 py-2.5">
      <button
        type="button"
        onClick={onToggle}
        aria-label={task.completed ? `Reopen “${task.title}”` : `Mark “${task.title}” done`}
        className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-md border transition-colors ${
          task.completed ? "border-jarvis-green/60 bg-jarvis-green/15 text-jarvis-green" : "border-border hover:border-primary"
        }`}
      >
        {task.completed ? <Check className="h-4 w-4" /> : null}
      </button>
      <div className="min-w-0 flex-1">
        <p className={`break-words ${task.completed ? "text-muted-foreground line-through" : "text-foreground"}`}>
          {task.priority === "high" && !task.completed && (
            <span className="mr-2 inline-block h-2 w-2 rounded-full bg-jarvis-ember align-middle" title="High priority" />
          )}
          {task.title}
        </p>
        {(task.due || task.priority !== "medium") && (
          <p className={`text-sm ${overdue ? "text-jarvis-ember" : "text-muted-foreground"}`}>
            {task.due && `${overdue ? "Was due " : "Due "}${relative(friendlyDate(task.due))}`}
            {task.due_time && ` at ${friendlyTime(task.due_time)}`}
            {task.priority !== "medium" && `${task.due ? ", " : ""}${PRIORITY_LABEL[task.priority].toLowerCase()} priority`}
          </p>
        )}
      </div>
      {confirming ? (
        <span className="flex items-center gap-1">
          <button type="button" onClick={onDelete} className="min-h-10 rounded-lg px-3 text-sm text-jarvis-red hover:bg-jarvis-red/10">
            Delete
          </button>
          <button type="button" onClick={() => setConfirming(false)} className="min-h-10 rounded-lg px-3 text-sm text-muted-foreground">
            Keep
          </button>
        </span>
      ) : (
        <span className="flex items-center opacity-100 transition-opacity sm:opacity-0 sm:group-focus-within:opacity-100 sm:group-hover:opacity-100">
          {task.completed ? (
            <button type="button" onClick={onToggle} aria-label="Reopen" className="flex h-10 w-10 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground">
              <Undo2 className="h-4 w-4" />
            </button>
          ) : (
            <button type="button" onClick={() => setEditing(true)} aria-label={`Edit “${task.title}”`} className="flex h-10 w-10 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground">
              <Pencil className="h-4 w-4" />
            </button>
          )}
          <button type="button" onClick={() => setConfirming(true)} aria-label={`Delete “${task.title}”`} className="flex h-10 w-10 items-center justify-center rounded-lg text-muted-foreground hover:text-jarvis-red">
            <Trash2 className="h-4 w-4" />
          </button>
        </span>
      )}
    </li>
  );
};

const TasksPage = () => {
  const { items, offline, error, create, update, remove } = useItems<Task>("tasks");
  const [title, setTitle] = useState("");
  const [due, setDue] = useState("");
  const [priority, setPriority] = useState<Priority>("medium");
  const today = localDateString(new Date());
  const pending = items.filter((t) => !t.completed).length;

  const add = (e: FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    void create({ title: title.trim(), completed: false, priority, due: due || null });
    setTitle("");
    setDue("");
    setPriority("medium");
  };

  const groups = ORDER.map((name) => ({
    name,
    tasks: items
      .filter((t) => groupOf(t, today) === name)
      .sort((a, b) => (a.due || "9999").localeCompare(b.due || "9999")),
  })).filter((g) => g.tasks.length);

  return (
    <div className="mx-auto max-w-3xl px-4 pb-28 pt-24 sm:px-6">
      <PageHeader
        title="Tasks"
        lead={`${pending} open. You can also say “remind me to call mom tomorrow at 6 pm” or “mark call mom as done”.`}
        offline={offline}
        error={error}
      />

      <form onSubmit={add} className="mb-10 flex flex-col gap-2 sm:flex-row">
        <label htmlFor="new-task" className="sr-only">
          New task
        </label>
        <input id="new-task" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="Add a task" maxLength={200} className={`${field} flex-1`} />
        <input type="date" value={due} onChange={(e) => setDue(e.target.value)} className={field} aria-label="Due date (optional)" />
        <select value={priority} onChange={(e) => setPriority(e.target.value as Priority)} className={field} aria-label="Priority">
          <option value="high">High priority</option>
          <option value="medium">Normal priority</option>
          <option value="low">Low priority</option>
        </select>
        <button type="submit" disabled={!title.trim() || offline} className="min-h-11 rounded-lg bg-primary px-5 font-medium text-primary-foreground disabled:bg-secondary disabled:text-muted-foreground">
          Add
        </button>
      </form>

      {groups.length === 0 && <p className="text-muted-foreground">No tasks yet.</p>}
      <div className="space-y-8">
        {groups.map((g) => (
          <section key={g.name} aria-labelledby={`g-${g.name}`}>
            <h2 id={`g-${g.name}`} className={`mb-1 text-base font-semibold ${g.name === "Overdue" ? "text-jarvis-ember" : "text-foreground"}`}>
              {g.name} <span className="font-sans text-sm font-normal text-muted-foreground">{g.tasks.length}</span>
            </h2>
            <ul className="divide-y divide-border/70">
              {g.tasks.map((t) => (
                <TaskRow
                  key={t.id}
                  task={t}
                  today={today}
                  onToggle={() => void update(t.id, { completed: !t.completed })}
                  onSave={(patch) => void update(t.id, patch)}
                  onDelete={() => void remove(t.id)}
                />
              ))}
            </ul>
          </section>
        ))}
      </div>
    </div>
  );
};

export default TasksPage;
