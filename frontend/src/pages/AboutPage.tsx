import CoreVisualizer from "@/components/hud/CoreVisualizer";
import { useAssistant } from "@/features/assistant/context";

const PIPELINE = [
  ["You speak or type", "Speech is transcribed on this computer with Whisper, or by the browser."],
  ["JARVIS works out what you mean", "Fixed rules handle common requests; anything else goes to the offline language model, which may only answer with a plan of known actions."],
  ["The plan is checked", "Every step is validated against the list of allowed actions and their inputs. Shell commands, installs and payments are refused."],
  ["You confirm anything risky", "Deleting, renaming, closing apps or typing for you waits for your yes, and binds to exactly what was shown."],
  ["The action runs", "On Linux or Windows, with a time limit, and JARVIS checks the result before saying it worked."],
  ["You get the answer", "Shown on screen with formatting, and spoken in a short version."],
];

const CAN = [
  ["Answer questions", "Explanations, coding help and follow-ups, using an offline model."],
  ["Look things up", "Current information from the web, summarised with sources."],
  ["Run your computer", "Open and close apps, websites, files and folders; create, copy, rename and trash files."],
  ["Read your screen", "Describe what's open or read the text aloud. The screenshot is deleted right away."],
  ["Keep your day", "Tasks with due dates, calendar events and notes, by voice or on their pages."],
  ["Remember what you tell it", "Only when you say “remember that…”, and you can make it forget."],
];

const AboutPage = () => {
  const { state, levelRef } = useAssistant();
  return (
    <div className="mx-auto max-w-6xl px-4 pb-28 pt-24 sm:px-6 lg:px-8">
      <div className="grid grid-cols-1 items-center gap-10 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        <div>
          <h1 className="font-display text-5xl font-semibold text-foreground">About JARVIS</h1>
          <p className="mt-4 max-w-2xl text-lg leading-relaxed text-foreground/80">
            JARVIS is a desktop assistant you can talk to. It answers questions and does things on your computer, and it
            runs on this machine rather than in the cloud. The language model never controls the computer directly: it
            decides what should happen, and JARVIS decides how to do it safely.
          </p>
        </div>
        <div className="mx-auto w-[min(60vw,260px)]">
          <CoreVisualizer phase={state.phase} levelRef={levelRef} size={260} className="h-auto w-full" />
        </div>
      </div>

      <section className="mt-16">
        <h2 className="text-2xl font-semibold">What it can do</h2>
        <dl className="mt-6 grid grid-cols-1 gap-x-10 gap-y-6 sm:grid-cols-2 lg:grid-cols-3">
          {CAN.map(([t, d]) => (
            <div key={t}>
              <dt className="font-medium text-foreground">{t}</dt>
              <dd className="mt-1 text-muted-foreground">{d}</dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="mt-16">
        <h2 className="text-2xl font-semibold">What happens when you ask</h2>
        <ol className="mt-6 space-y-0">
          {PIPELINE.map(([t, d], i) => (
            <li key={t} className="grid grid-cols-[2.5rem_minmax(0,1fr)] gap-x-4 border-l border-border pb-6 pl-0 last:pb-0">
              <span className="tabular -ml-[1.0625rem] flex h-8 w-8 items-center justify-center rounded-full border border-border bg-background font-display text-sm text-primary">
                {i + 1}
              </span>
              <div className="-ml-4 max-w-2xl">
                <p className="font-medium text-foreground">{t}</p>
                <p className="mt-1 text-muted-foreground">{d}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section className="mt-16 max-w-3xl">
        <h2 className="text-2xl font-semibold">Built with</h2>
        <p className="mt-3 text-muted-foreground">
          React, TypeScript and Tailwind for this interface; Python and Flask for the assistant, bound to this computer
          only; Ollama for the language model; faster-whisper for listening; Piper for the voice; RapidOCR for reading the
          screen. A final-year engineering project.
        </p>
      </section>
    </div>
  );
};

export default AboutPage;
