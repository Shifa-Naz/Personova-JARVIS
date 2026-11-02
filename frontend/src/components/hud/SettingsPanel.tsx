import { Check, Minus } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import type { AssistantSettings, SttPreference, TtsPreference } from "@/features/assistant/context";
import type { SttEngine, TtsEngine } from "@/features/assistant/speech";
import type { Capabilities } from "@/features/assistant/types";
import { WAKE_PHRASE } from "@/features/assistant/wake";

interface Props {
  settings: AssistantSettings;
  capabilities: Capabilities | null;
  activeStt: SttEngine | null;
  activeTts: TtsEngine | null;
  wakeListening: boolean;
  wakeError: string | null;
  onChange: (patch: Partial<AssistantSettings>) => void;
}

function Choice<T extends string>({
  label,
  value,
  options,
  onPick,
}: {
  label: string;
  value: T;
  options: { value: T; label: string }[];
  onPick: (v: T) => void;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-lg border border-border p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onPick(o.value)}
          className={`min-h-10 rounded-md px-3 text-sm transition-colors ${
            value === o.value ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

const STT: { value: SttPreference; label: string }[] = [
  { value: "auto", label: "Automatic" },
  { value: "local", label: "On this computer" },
  { value: "browser", label: "Browser" },
];
const TTS: { value: TtsPreference; label: string }[] = [
  { value: "auto", label: "Automatic" },
  { value: "local", label: "JARVIS voice" },
  { value: "browser", label: "System voice" },
];

const Row = ({ ok, label, hint }: { ok: boolean; label: string; hint?: string | null }) => (
  <li className="flex items-start gap-2.5">
    <span className={`mt-1 flex h-4 w-4 shrink-0 items-center justify-center rounded-full ${ok ? "bg-jarvis-green/20" : "bg-secondary"}`}>
      {ok ? <Check className="h-3 w-3 text-jarvis-green" /> : <Minus className="h-3 w-3 text-muted-foreground" />}
    </span>
    <span className="text-sm">
      <span className={ok ? "text-foreground" : "text-muted-foreground"}>{label}</span>
      {!ok && hint && <span className="block text-xs text-muted-foreground">{hint}</span>}
    </span>
  </li>
);

const SettingsPanel = ({ settings, capabilities, activeStt, activeTts, wakeListening, wakeError, onChange }: Props) => (
  <div className="grid gap-8 md:grid-cols-2">
    <div className="space-y-6">
      <div>
        <p className="mb-2 text-sm font-medium text-foreground">Listening</p>
        <Choice label="Speech recognition" value={settings.stt} options={STT} onPick={(stt) => onChange({ stt })} />
        <p className="mt-2 text-sm text-muted-foreground">
          {activeStt === "local"
            ? "Your voice is transcribed on this computer, even offline."
            : activeStt === "browser"
              ? "Using the browser's recognition, which needs internet."
              : "No speech recognition is available. You can still type."}
        </p>
      </div>
      <div>
        <div className="mb-2 flex items-center justify-between gap-3">
          <p className="text-sm font-medium text-foreground">Wake word “Jarvis”</p>
          <Switch checked={settings.wake} onCheckedChange={(v) => onChange({ wake: v })} aria-label="Wake phrase" />
        </div>
        <p className="text-sm text-muted-foreground">
          {!settings.wake
            ? "Off. Press Space or the mic to talk."
            : wakeError
              ? wakeError
              : activeStt !== "local"
                ? "Needs speech recognition on this computer (faster-whisper)."
                : wakeListening
                  ? `Listening now, on this computer only. Say “Jarvis” and your request, “Jarvis” alone, or “${WAKE_PHRASE}”`
                  : "Starts listening whenever JARVIS is ready and this page is open."}
        </p>
      </div>
      <div>
        <div className="mb-2 flex items-center justify-between gap-3">
          <p className="text-sm font-medium text-foreground">Briefing when I open the laptop</p>
          <Switch checked={settings.briefing} onCheckedChange={(v) => onChange({ briefing: v })} aria-label="Briefing on wake-up" />
        </div>
        <p className="text-sm text-muted-foreground">
          {settings.briefing
            ? "When the laptop wakes up or you unlock the screen, JARVIS reads today's schedule and the top tech headlines."
            : "Off. Say “brief me” any time."}
        </p>
      </div>
      <div>
        <div className="mb-2 flex items-center justify-between gap-3">
          <p className="text-sm font-medium text-foreground">Spoken replies</p>
          <Switch checked={settings.voice} onCheckedChange={(v) => onChange({ voice: v })} aria-label="Spoken replies" />
        </div>
        {settings.voice && <Choice label="Voice" value={settings.tts} options={TTS} onPick={(tts) => onChange({ tts })} />}
        <p className="mt-2 text-sm text-muted-foreground">
          {!settings.voice
            ? "JARVIS answers on screen only."
            : activeTts === "local"
              ? "JARVIS speaks with its offline voice."
              : settings.tts === "local"
                ? "The JARVIS voice isn't installed yet, so the system voice is used."
                : "JARVIS speaks with your system's voice."}
        </p>
      </div>
    </div>

    <div>
      <p className="mb-3 text-sm font-medium text-foreground">What's available</p>
      {capabilities ? (
        <ul className="space-y-2.5">
          <Row ok={capabilities.llm} label={`Language model${capabilities.llm_model ? ` (${capabilities.llm_model})` : ""}`} hint={capabilities.llm_error} />
          <Row ok={capabilities.stt} label="Speech recognition on this computer" hint="pip install faster-whisper" />
          <Row ok={capabilities.tts} label="JARVIS voice" hint="pip install piper-tts, then python run.py --download-models" />
          <Row ok={Boolean(capabilities.screen_ocr)} label="Reading the screen" hint="pip install rapidocr_onnxruntime" />
          <Row ok={capabilities.online} label="Internet, for web lookups" hint="Local commands still work offline." />
          <Row ok={capabilities.automation} label="Typing and clicking for you" hint="Not available on Wayland desktops." />
        </ul>
      ) : (
        <p className="text-sm text-muted-foreground">Connect to the backend to see what's available.</p>
      )}
    </div>
  </div>
);

export default SettingsPanel;
