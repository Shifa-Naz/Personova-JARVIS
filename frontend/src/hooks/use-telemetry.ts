import { useEffect, useState } from "react";
import { jarvis } from "@/lib/api";
import type { Telemetry } from "@/features/assistant/types";

/** Polls real system telemetry from the backend; null while unavailable. `processes` adds the busiest apps. */
export function useTelemetry(intervalMs = 3000, processes = false): Telemetry | null {
  const [data, setData] = useState<Telemetry | null>(null);

  useEffect(() => {
    let alive = true;
    let timer: ReturnType<typeof setTimeout>;
    const poll = async () => {
      try {
        const t = await jarvis.system(processes);
        if (alive) setData(t);
      } catch {
        if (alive) setData(null);
      }
      if (alive) timer = setTimeout(poll, intervalMs);
    };
    void poll();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [intervalMs, processes]);

  return data;
}
