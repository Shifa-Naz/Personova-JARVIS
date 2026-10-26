import { useCallback, useEffect, useRef, useState } from "react";
import { jarvis } from "@/lib/api";
import { clearLegacy, DATA_CHANGED_EVENT, readCache, readLegacy, writeCache } from "@/lib/storage";
import type { ItemKind } from "@/features/assistant/types";

export interface ItemsState<T> {
  items: T[];
  /** True while the backend is unreachable and `items` comes from the browser cache. */
  offline: boolean;
  loading: boolean;
  error: string | null;
  create: (item: Partial<T>) => Promise<void>;
  update: (id: string, patch: Partial<T>) => Promise<void>;
  remove: (id: string) => Promise<void>;
  reload: () => Promise<void>;
}

/**
 * Notes / tasks / events from the backend store (shared with the assistant), cached in the
 * browser for offline viewing. Old browser-only data is imported once, then removed.
 */
export function useItems<T extends { id: string }>(kind: ItemKind): ItemsState<T> {
  const [items, setItems] = useState<T[]>(() => readCache<T>(kind));
  const [offline, setOffline] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);

  const reload = useCallback(async () => {
    try {
      const legacy = readLegacy<T>(kind);
      let next: T[];
      if (legacy.length) {
        next = (await jarvis.importItems<T>(kind, legacy)).items;
        clearLegacy(kind);
      } else {
        next = await jarvis.listItems<T>(kind);
      }
      if (!alive.current) return;
      setItems(next);
      writeCache(kind, next);
      setOffline(false);
      setError(null);
    } catch {
      if (alive.current) setOffline(true);
    } finally {
      if (alive.current) setLoading(false);
    }
  }, [kind]);

  useEffect(() => {
    alive.current = true;
    void reload();
    // The assistant changed this data by voice: refresh.
    const onChange = (e: Event) => {
      if (e instanceof CustomEvent && e.detail && e.detail !== kind) return;
      void reload();
    };
    window.addEventListener(DATA_CHANGED_EVENT, onChange);
    return () => {
      alive.current = false;
      window.removeEventListener(DATA_CHANGED_EVENT, onChange);
    };
  }, [kind, reload]);

  const mutate = useCallback(
    async (fn: () => Promise<unknown>) => {
      try {
        await fn();
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "That change didn't save.");
      }
      await reload();
    },
    [reload],
  );

  return {
    items,
    offline,
    loading,
    error,
    reload,
    create: (item) => mutate(() => jarvis.createItem<T>(kind, item)),
    update: (id, patch) => mutate(() => jarvis.updateItem<T>(kind, id, patch)),
    remove: (id) => mutate(() => jarvis.deleteItem(kind, id)),
  };
}
