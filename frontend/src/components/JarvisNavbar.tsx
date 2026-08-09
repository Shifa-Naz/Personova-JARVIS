import { Link, useLocation } from "react-router-dom";
import { motion } from "framer-motion";
import { LayoutDashboard, Mic, StickyNote, CalendarDays, ListChecks, Info } from "lucide-react";

const navItems = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard },
  { to: "/assistant", label: "Assistant", icon: Mic },
  { to: "/notes", label: "Notes", icon: StickyNote },
  { to: "/calendar", label: "Calendar", icon: CalendarDays },
  { to: "/tasks", label: "Tasks", icon: ListChecks },
  { to: "/about", label: "About", icon: Info },
];

const JarvisNavbar = () => {
  const location = useLocation();

  return (
    <motion.nav
      initial={{ y: -60, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.6, ease: "easeOut" }}
      className="fixed top-0 left-0 right-0 z-50 glass-panel border-b border-border/30"
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <Link to="/" className="flex items-center gap-3 group">
            <div className="relative w-8 h-8">
              <div className="absolute inset-0 rounded-full bg-primary/20 animate-pulse-glow" />
              <div className="absolute inset-1 rounded-full border border-primary/60 flex items-center justify-center">
                <div className="w-2 h-2 rounded-full bg-primary" />
              </div>
            </div>
            <span className="font-display text-xl font-bold tracking-widest text-primary glow-text">
              J.A.R.V.I.S
            </span>
          </Link>

          <div className="hidden md:flex items-center gap-1">
            {navItems.map((item) => {
              const isActive = location.pathname === item.to;
              const Icon = item.icon;
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  className={`relative flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-all duration-300 ${
                    isActive
                      ? "text-primary glow-text"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {isActive && (
                    <motion.div
                      layoutId="activeNav"
                      className="absolute inset-0 rounded-lg bg-primary/10 border border-primary/20 glow-border"
                      transition={{ type: "spring", bounce: 0.2, duration: 0.6 }}
                    />
                  )}
                  <Icon className="w-4 h-4 relative z-10" />
                  <span className="relative z-10 font-body tracking-wide">{item.label}</span>
                </Link>
              );
            })}
          </div>

          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full border border-primary/20 bg-primary/5">
              <div className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
              <span className="text-xs font-mono text-primary/80">ONLINE</span>
            </div>
          </div>
        </div>
      </div>
      <div className="holographic-line" />
    </motion.nav>
  );
};

export default JarvisNavbar;
