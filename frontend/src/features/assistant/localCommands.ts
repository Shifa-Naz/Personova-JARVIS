/**
 * Commands handled entirely in the UI: switching pages. Everything else — including
 * notes, tasks and calendar — goes to the backend so it is validated and stored once.
 */

export interface LocalCommand {
  kind: "navigate";
  path: string;
  reply: string;
}

const PAGES: Record<string, string> = {
  dashboard: "/",
  home: "/",
  "home page": "/",
  console: "/assistant",
  assistant: "/assistant",
  notes: "/notes",
  calendar: "/calendar",
  tasks: "/tasks",
  "task list": "/tasks",
  about: "/about",
};

const clean = (t: string) =>
  t
    .toLowerCase()
    .replace(/^(?:hey |ok |okay )?jarvis[\s,]*/, "")
    .replace(/[\s,]+jarvis$/, "")
    .replace(/[.!?]+$/, "")
    .replace(/^(?:please |can you |could you )+/, "")
    .trim();

export function matchLocalCommand(raw: string): LocalCommand | null {
  const t = clean(raw);
  const nav =
    t.match(/^(?:go to|go back to|switch to|take me to)(?: the| my)? ([a-z ]+?)(?: page| screen| tab)?$/) ??
    t.match(/^(?:open|show)(?: the| my)? ([a-z ]+?) (?:page|screen|tab)$/) ??
    t.match(/^(?:open|show)(?: the)? (dashboard|console)$/);
  if (nav && PAGES[nav[1].trim()]) {
    const name = nav[1].trim();
    const label = name === "home" || name === "home page" ? "the dashboard" : name === "assistant" ? "the console" : name;
    return { kind: "navigate", path: PAGES[name], reply: `Opening ${label}.` };
  }
  return null;
}

export function applyLocalCommand(cmd: LocalCommand, navigate: (path: string) => void): void {
  navigate(cmd.path);
}
