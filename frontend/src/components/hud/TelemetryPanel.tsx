import type { Telemetry } from "@/features/assistant/types";

const gb = (n: number) => `${(n / 1024 ** 3).toFixed(1)} GB`;

interface Reading {
  label: string;
  value: string;
  /** 0-100 fill for the gauge; null = no gauge. */
  fill: number | null;
  /** True when the reading needs attention (high load, low battery, offline). */
  warn: boolean;
  sub: string;
}

function readings(t: Telemetry): Reading[] {
  const out: Reading[] = [
    { label: "Processor", value: `${t.cpu_percent.toFixed(0)}%`, fill: t.cpu_percent, warn: t.cpu_percent > 85, sub: `${t.cpu_count} cores` },
    {
      label: "Memory",
      value: `${t.memory.percent.toFixed(0)}%`,
      fill: t.memory.percent,
      warn: t.memory.percent > 85,
      sub: `${gb(t.memory.used)} of ${gb(t.memory.total)}`,
    },
  ];
  if (t.disk) {
    out.push({ label: "Storage", value: `${t.disk.percent.toFixed(0)}%`, fill: t.disk.percent, warn: t.disk.percent > 90, sub: `${gb(t.disk.free)} free` });
  }
  if (t.battery) {
    out.push({
      label: "Battery",
      value: `${t.battery.percent}%`,
      fill: t.battery.percent,
      warn: t.battery.percent < 20 && !t.battery.plugged,
      sub: t.battery.plugged ? "Charging" : "On battery",
    });
  }
  out.push({ label: "Network", value: t.online ? "Online" : "Offline", fill: null, warn: !t.online, sub: t.hostname });
  return out;
}

/** Live readings as one quiet instrument strip. */
const TelemetryPanel = ({ data }: { data: Telemetry | null }) => {
  if (!data) {
    return <p className="text-sm text-muted-foreground">System readings appear once the backend is running.</p>;
  }
  return (
    <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3 lg:grid-cols-5">
      {readings(data).map((r) => (
        <div key={r.label} className="min-w-0">
          <dt className="text-sm text-muted-foreground">{r.label}</dt>
          <dd className={`tabular mt-0.5 font-display text-2xl font-semibold ${r.warn ? "text-jarvis-ember" : "text-foreground"}`}>
            {r.value}
          </dd>
          {r.fill !== null && (
            <div className="mt-1.5 h-1 w-full overflow-hidden rounded-full bg-secondary" role="presentation">
              <div
                className={`h-full rounded-full transition-[width] duration-700 ${r.warn ? "bg-jarvis-ember" : "bg-primary/80"}`}
                style={{ width: `${Math.min(100, Math.max(0, r.fill))}%` }}
              />
            </div>
          )}
          <dd className="mt-1 truncate text-xs text-muted-foreground">{r.sub}</dd>
        </div>
      ))}
    </dl>
  );
};

export default TelemetryPanel;
