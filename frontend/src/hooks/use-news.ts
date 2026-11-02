import { useEffect, useState } from "react";
import { jarvis } from "@/lib/api";
import type { Headline } from "@/features/assistant/types";

const REFRESH_MS = 15 * 60 * 1000;

/** Latest tech headlines from the backend (cached there for 15 minutes). */
export function useNews(count = 5): { items: Headline[]; error: string | null; loading: boolean } {
  const [items, setItems] = useState<Headline[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const load = async () => {
      try {
        const r = await jarvis.news(count);
        if (!alive) return;
        setItems(r.items);
        setError(r.offline && !r.items.length ? "You're offline, so there's no news right now." : null);
      } catch {
        if (alive) setError("I couldn't get the news right now.");
      } finally {
        if (alive) setLoading(false);
      }
      if (alive) timer = setTimeout(load, REFRESH_MS);
    };
    void load();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [count]);

  return { items, error, loading };
}
