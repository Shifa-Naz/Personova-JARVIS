/**
 * Shared shapes for notes, tasks and events, plus browser-cache helpers.
 *
 * The backend store is the source of truth (the assistant edits the same data). The browser
 * keeps a cached copy so the pages still show something while the backend is offline, and
 * data the old frontend kept only in localStorage ("jarvis_*" / "ultron_*") is imported once.
 */

import type { ItemKind } from "@/features/assistant/types";

export interface Task {
  id: string;
  title: string;
  completed: boolean;
  priority: "high" | "medium" | "low";
  due?: string | null;
  due_time?: string | null;
}

export interface Note {
  id: string;
  title: string;
  content: string;
  date?: string;
  color?: string;
  previous?: string;
  created?: number;
}

export interface CalEvent {
  id: string;
  date: string;
  title: string;
  time: string;
}

const cacheKey = (kind: ItemKind) => `jarvis_cache_${kind}`;
const LEGACY_KEYS = (kind: ItemKind) => [`jarvis_${kind}`, `ultron_${kind}`];

function safeParse<T>(raw: string | null): T[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as T[]) : [];
  } catch {
    return []; // malformed JSON must never break a page
  }
}

export function readCache<T>(kind: ItemKind): T[] {
  try {
    return safeParse<T>(localStorage.getItem(cacheKey(kind)));
  } catch {
    return [];
  }
}

export function writeCache<T>(kind: ItemKind, items: T[]): void {
  try {
    localStorage.setItem(cacheKey(kind), JSON.stringify(items));
  } catch {
    // storage full or blocked: the page keeps working from memory
  }
}

/** Items the old frontend stored only in this browser, still waiting to be imported. */
export function readLegacy<T>(kind: ItemKind): T[] {
  try {
    return LEGACY_KEYS(kind).flatMap((k) => safeParse<T>(localStorage.getItem(k)));
  } catch {
    return [];
  }
}

export function clearLegacy(kind: ItemKind): void {
  try {
    LEGACY_KEYS(kind).forEach((k) => localStorage.removeItem(k));
  } catch {
    // ignore
  }
}

/** Local calendar date as YYYY-MM-DD (not UTC — toISOString() shifts the day in IST mornings). */
export function localDateString(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}

/** "Today", "Tomorrow", "Fri 16 Oct" — for due dates and event days. */
export function friendlyDate(iso: string | null | undefined, now = new Date()): string {
  if (!iso) return "";
  const [y, m, d] = iso.split("-").map(Number);
  const day = new Date(y, m - 1, d);
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const diff = Math.round((day.getTime() - today.getTime()) / 86_400_000);
  if (diff === 0) return "Today";
  if (diff === 1) return "Tomorrow";
  if (diff === -1) return "Yesterday";
  return day.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short" });
}

export function friendlyTime(hhmm: string | null | undefined): string {
  if (!hhmm) return "";
  const [h, m] = hhmm.split(":").map(Number);
  return new Date(2000, 0, 1, h, m).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}

export const DATA_CHANGED_EVENT = "jarvis-data-changed";
