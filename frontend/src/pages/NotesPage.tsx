import { Pencil, Search, Trash2, Undo2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import PageHeader from "@/components/PageHeader";
import { useItems } from "@/hooks/use-items";
import type { Note } from "@/lib/storage";

const field =
  "w-full rounded-lg border border-border bg-background px-3 text-base text-foreground placeholder:text-muted-foreground focus:border-primary/60 focus:outline-none";

const NoteCard = ({ note, onSave, onDelete }: { note: Note; onSave: (p: Partial<Note>) => void; onDelete: () => void }) => {
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(note.title);
  const [content, setContent] = useState(note.content ?? "");
  const [confirming, setConfirming] = useState(false);

  if (editing) {
    return (
      <li className="panel p-4">
        <form
          className="space-y-2"
          onSubmit={(e) => {
            e.preventDefault();
            if (!title.trim()) return;
            onSave({ title: title.trim(), content, previous: note.content });
            setEditing(false);
          }}
        >
          <input value={title} onChange={(e) => setTitle(e.target.value)} className={`${field} min-h-11`} aria-label="Title" autoFocus />
          <textarea value={content} onChange={(e) => setContent(e.target.value)} rows={6} className={`${field} py-2`} aria-label="Note text" />
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
    <li className="panel group flex flex-col p-4">
      <h3 className="break-words font-sans text-base font-semibold text-foreground">{note.title}</h3>
      {note.content && <p className="mt-2 flex-1 whitespace-pre-wrap break-words text-foreground/80">{note.content}</p>}
      <div className="mt-4 flex items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground">{note.date}</span>
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
            {note.previous !== undefined && note.previous !== note.content && (
              <button
                type="button"
                onClick={() => onSave({ content: note.previous ?? "", previous: note.content })}
                aria-label="Undo the last edit"
                title="Undo the last edit"
                className="flex h-10 w-10 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground"
              >
                <Undo2 className="h-4 w-4" />
              </button>
            )}
            <button type="button" onClick={() => setEditing(true)} aria-label={`Edit “${note.title}”`} className="flex h-10 w-10 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground">
              <Pencil className="h-4 w-4" />
            </button>
            <button type="button" onClick={() => setConfirming(true)} aria-label={`Delete “${note.title}”`} className="flex h-10 w-10 items-center justify-center rounded-lg text-muted-foreground hover:text-jarvis-red">
              <Trash2 className="h-4 w-4" />
            </button>
          </span>
        )}
      </div>
    </li>
  );
};

const NotesPage = () => {
  const { items, offline, error, create, update, remove } = useItems<Note>("notes");
  const [search, setSearch] = useState("");
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");

  const q = search.trim().toLowerCase();
  const shown = q ? items.filter((n) => `${n.title} ${n.content}`.toLowerCase().includes(q)) : items;

  const add = (e: FormEvent) => {
    e.preventDefault();
    if (!title.trim()) return;
    void create({ title: title.trim(), content: content.trim(), date: new Date().toLocaleString([], { dateStyle: "medium", timeStyle: "short" }) });
    setTitle("");
    setContent("");
  };

  return (
    <div className="mx-auto max-w-6xl px-4 pb-28 pt-24 sm:px-6 lg:px-8">
      <PageHeader
        title="Notes"
        lead="Write here, or say “take a note …”, “search notes for …” or “add … to the shopping note”."
        offline={offline}
        error={error}
      >
        <div className="relative w-full sm:w-72">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <label htmlFor="note-search" className="sr-only">
            Search notes
          </label>
          <input id="note-search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search notes" className={`${field} min-h-11 pl-9`} />
        </div>
      </PageHeader>

      <form onSubmit={add} className="panel mb-8 space-y-2 p-4">
        <label htmlFor="note-title" className="sr-only">
          Title
        </label>
        <input id="note-title" value={title} onChange={(e) => setTitle(e.target.value)} placeholder="New note title" maxLength={200} className={`${field} min-h-11`} />
        <label htmlFor="note-body" className="sr-only">
          Text
        </label>
        <textarea id="note-body" value={content} onChange={(e) => setContent(e.target.value)} placeholder="Write something (optional)" rows={3} className={`${field} py-2`} />
        <button type="submit" disabled={!title.trim() || offline} className="min-h-11 rounded-lg bg-primary px-5 font-medium text-primary-foreground disabled:bg-secondary disabled:text-muted-foreground">
          Save note
        </button>
      </form>

      {shown.length === 0 ? (
        <p className="text-muted-foreground">{items.length ? "No notes match that search." : "No notes yet."}</p>
      ) : (
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {shown.map((n) => (
            <NoteCard key={n.id} note={n} onSave={(p) => void update(n.id, p)} onDelete={() => void remove(n.id)} />
          ))}
        </ul>
      )}
    </div>
  );
};

export default NotesPage;
