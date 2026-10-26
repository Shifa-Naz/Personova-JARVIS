import { beforeEach, describe, expect, it } from "vitest";
import { matchLocalCommand } from "@/features/assistant/localCommands";
import { clearLegacy, friendlyDate, localDateString, readCache, readLegacy, writeCache } from "@/lib/storage";

describe("local UI commands", () => {
  it.each([
    ["go to notes", "/notes"],
    ["Jarvis, open the calendar page", "/calendar"],
    ["show tasks page", "/tasks"],
    ["take me to the dashboard", "/"],
  ])("navigates: %s", (text, path) => {
    expect(matchLocalCommand(text)).toMatchObject({ kind: "navigate", path });
  });

  it("leaves everything else to the backend", () => {
    expect(matchLocalCommand("open notepad")).toBeNull();
    expect(matchLocalCommand("open my notes")).toBeNull();
    expect(matchLocalCommand("add a task to call the bank")).toBeNull();
    expect(matchLocalCommand("show tasks")).toBeNull();
  });
});

describe("browser storage", () => {
  beforeEach(() => localStorage.clear());

  it("reads legacy jarvis_* and ultron_* data for one-time import", () => {
    localStorage.setItem("jarvis_tasks", JSON.stringify([{ id: "1", title: "old jarvis" }]));
    localStorage.setItem("ultron_tasks", JSON.stringify([{ id: "2", title: "old ultron" }]));
    expect(readLegacy<{ title: string }>("tasks").map((t) => t.title)).toEqual(["old jarvis", "old ultron"]);
    clearLegacy("tasks");
    expect(readLegacy("tasks")).toEqual([]);
  });

  it("survives malformed JSON", () => {
    localStorage.setItem("jarvis_cache_notes", "{not json");
    expect(readCache("notes")).toEqual([]);
    writeCache("notes", [{ id: "x" }]);
    expect(readCache("notes")).toEqual([{ id: "x" }]);
  });

  it("formats dates without UTC shifting", () => {
    expect(localDateString(new Date(2026, 0, 5, 1, 30))).toBe("2026-01-05");
    const now = new Date(2026, 9, 11, 9);
    expect(friendlyDate("2026-10-11", now)).toBe("Today");
    expect(friendlyDate("2026-10-12", now)).toBe("Tomorrow");
  });
});
