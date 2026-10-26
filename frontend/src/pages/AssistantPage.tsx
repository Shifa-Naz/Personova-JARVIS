import CommandBar from "@/components/hud/CommandBar";
import CoreVisualizer from "@/components/hud/CoreVisualizer";
import LogsPanel from "@/components/hud/LogsPanel";
import SettingsPanel from "@/components/hud/SettingsPanel";
import StatusReadout from "@/components/hud/StatusReadout";
import TelemetryPanel from "@/components/hud/TelemetryPanel";
import Transcript from "@/components/hud/Transcript";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAssistant } from "@/features/assistant/context";
import { useTelemetry } from "@/hooks/use-telemetry";

const BUSY = ["THINKING", "EXECUTING", "PROCESSING"];

const AssistantPage = () => {
  const {
    state,
    settings,
    levelRef,
    activeStt,
    activeTts,
    submit,
    toggleListening,
    updateSettings,
    stopSpeaking,
    reconnect,
    wakeListening,
    wakeError,
    draft,
    setDraft,
  } = useAssistant();
  const telemetry = useTelemetry();
  const detail =
    state.lastDetail ??
    (state.phase === "ERROR"
      ? state.lastError
      : state.phase === "IDLE" && wakeListening
        ? "Say “Jarvis” and what you need, or press Space"
        : null);
  const busy = BUSY.includes(state.phase);

  return (
    <div className="mx-auto max-w-7xl px-4 pt-16 sm:px-6 lg:px-8">
      <div className="grid grid-cols-1 gap-6 lg:h-[calc(100dvh-4rem)] lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] lg:gap-10">
        {/* The core: the one bold element on the page */}
        <section aria-label="JARVIS status" className="flex flex-col items-center justify-center gap-5 pt-8 lg:pt-0">
          <div className="core-boot w-[min(72vw,320px)] lg:w-[min(30vw,380px)]">
            <CoreVisualizer phase={state.phase} levelRef={levelRef} size={380} className="h-auto w-full" />
          </div>
          <StatusReadout phase={state.phase} detail={detail} />
          {!state.connected && (
            <button
              type="button"
              onClick={reconnect}
              className="min-h-11 rounded-lg border border-border px-5 text-sm text-foreground hover:border-primary/60"
            >
              Try connecting again
            </button>
          )}
          <p className="hidden text-sm text-muted-foreground lg:block">
            <kbd className="rounded border border-border px-1.5 py-0.5 font-sans text-xs">Space</kbd> to talk,{" "}
            <kbd className="rounded border border-border px-1.5 py-0.5 font-sans text-xs">Esc</kbd> to cancel
          </p>
        </section>

        {/* Conversation */}
        <section aria-label="Conversation" className="flex flex-col pb-4 lg:min-h-0 lg:py-6 lg:pb-6">
          <div className="min-h-0 flex-1 overflow-y-auto pb-4 pr-1">
            <Transcript
              messages={state.messages}
              livePlan={state.plan}
              busy={busy}
              streamText={state.streamText}
              onSuggest={(t) => void submit(t)}
            />
          </div>
          {/* Phones: pinned to the bottom of the screen like a messaging app. Desktop: docked under the conversation. */}
          <div className="fixed inset-x-0 bottom-0 z-30 border-t border-border bg-background/95 px-4 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 backdrop-blur lg:static lg:z-auto lg:border-0 lg:bg-transparent lg:px-0 lg:pb-0 lg:pt-2 lg:backdrop-blur-none">
            <CommandBar
              phase={state.phase}
              canListen={activeStt !== null}
              onSubmit={(t) => void submit(t)}
              onToggleMic={toggleListening}
              onStopSpeaking={stopSpeaking}
              value={draft}
              onChange={setDraft}
            />
          </div>
        </section>
      </div>

      <section aria-label="System" className="border-t border-border pb-32 pt-10 lg:pb-10">
        <Tabs defaultValue="system">
          <TabsList className="h-auto gap-1 bg-transparent p-0">
            {[
              ["system", "System"],
              ["voice", "Voice and AI"],
              ["activity", "Activity"],
            ].map(([value, label]) => (
              <TabsTrigger
                key={value}
                value={value}
                className="min-h-10 rounded-lg px-4 text-sm text-muted-foreground data-[state=active]:bg-secondary data-[state=active]:text-foreground data-[state=active]:shadow-none"
              >
                {label}
              </TabsTrigger>
            ))}
          </TabsList>
          <TabsContent value="system" className="mt-6">
            <TelemetryPanel data={telemetry} />
          </TabsContent>
          <TabsContent value="voice" className="mt-6">
            <SettingsPanel
              settings={settings}
              capabilities={state.capabilities}
              activeStt={activeStt}
              activeTts={activeTts}
              wakeListening={wakeListening}
              wakeError={wakeError}
              onChange={updateSettings}
            />
          </TabsContent>
          <TabsContent value="activity" className="mt-6">
            <LogsPanel refreshKey={state.messages.length} />
          </TabsContent>
        </Tabs>
      </section>
    </div>
  );
};

export default AssistantPage;
