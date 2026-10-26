import { Ear, Menu, RotateCw } from "lucide-react";
import { useState } from "react";
import { Link, NavLink } from "react-router-dom";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { useAssistant } from "@/features/assistant/context";
import { PHASES, phaseColor } from "@/features/assistant/phase";
import { WAKE_PHRASE } from "@/features/assistant/wake";

const navItems = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/assistant", label: "Console", end: false },
  { to: "/tasks", label: "Tasks", end: false },
  { to: "/calendar", label: "Calendar", end: false },
  { to: "/notes", label: "Notes", end: false },
  { to: "/about", label: "About", end: false },
];

/** The wordmark: a small core glyph and the name, set in the display face. */
export const Wordmark = () => (
  <span className="flex items-center gap-2.5">
    <svg viewBox="0 0 24 24" className="h-6 w-6 text-primary" aria-hidden>
      <circle cx="12" cy="12" r="10.5" fill="none" stroke="currentColor" strokeOpacity="0.45" strokeWidth="1" />
      <circle cx="12" cy="12" r="7" fill="none" stroke="currentColor" strokeWidth="1.5" strokeDasharray="9 3" />
      <circle cx="12" cy="12" r="2.6" fill="currentColor" />
    </svg>
    <span className="font-display text-xl font-semibold tracking-[0.08em] text-foreground">JARVIS</span>
  </span>
);

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `relative flex h-16 items-center px-3 text-[0.95rem] transition-colors ${
    isActive
      ? "text-foreground after:absolute after:inset-x-3 after:bottom-0 after:h-0.5 after:rounded-full after:bg-primary"
      : "text-muted-foreground hover:text-foreground"
  }`;

const JarvisNavbar = () => {
  const { state, reconnect, wakeListening } = useAssistant();
  const [open, setOpen] = useState(false);

  return (
    <nav className="fixed inset-x-0 top-0 z-50 border-b border-border bg-background/85 backdrop-blur-md" aria-label="Main">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
        <Link to="/" className="flex min-h-11 items-center" aria-label="JARVIS dashboard">
          <Wordmark />
        </Link>

        <div className="hidden items-center md:flex">
          {navItems.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end} className={linkClass}>
              {item.label}
            </NavLink>
          ))}
        </div>

        <div className="flex items-center gap-1">
          {state.connected ? (
            <span
              className="hidden items-center gap-2 px-2 text-sm text-muted-foreground sm:flex"
              title={wakeListening ? `Listening for “${WAKE_PHRASE}”` : PHASES[state.phase].label}
            >
              <span className="h-2 w-2 rounded-full" style={{ background: phaseColor(state.phase) }} />
              {state.phase === "IDLE" && wakeListening ? (
                <>
                  <Ear className="h-4 w-4 text-primary" aria-hidden /> Listening for your call
                </>
              ) : (
                PHASES[state.phase].label
              )}
            </span>
          ) : (
            <button
              type="button"
              onClick={reconnect}
              className="flex min-h-10 items-center gap-2 rounded-lg px-3 text-sm text-jarvis-ember hover:bg-secondary"
            >
              <RotateCw className="h-4 w-4" /> Offline, retry
            </button>
          )}

          <Sheet open={open} onOpenChange={setOpen}>
            <SheetTrigger asChild>
              <button
                type="button"
                className="flex h-11 w-11 items-center justify-center rounded-lg text-muted-foreground hover:text-foreground md:hidden"
                aria-label="Open menu"
              >
                <Menu className="h-6 w-6" />
              </button>
            </SheetTrigger>
            <SheetContent side="right" className="w-72 border-border bg-card">
              <SheetTitle>
                <Wordmark />
              </SheetTitle>
              <ul className="mt-8 space-y-1">
                {navItems.map((item) => (
                  <li key={item.to}>
                    <NavLink
                      to={item.to}
                      end={item.end}
                      onClick={() => setOpen(false)}
                      className={({ isActive }) =>
                        `flex min-h-12 items-center rounded-lg px-3 text-base ${
                          isActive ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground"
                        }`
                      }
                    >
                      {item.label}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </SheetContent>
          </Sheet>
        </div>
      </div>
    </nav>
  );
};

export default JarvisNavbar;
