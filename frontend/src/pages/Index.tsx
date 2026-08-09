import { motion } from "framer-motion";
import { Mic, StickyNote, CalendarDays, ListChecks, Activity, Cpu, Shield, Zap } from "lucide-react";
import { Link } from "react-router-dom";
import HoloPanel from "@/components/HoloPanel";
import JarvisAvatar from "@/components/JarvisAvatar";
import jarvisBg from "@/assets/jarvis-bg.jpg";

const stats = [
  { label: "CPU LOAD", value: "12%", icon: Cpu },
  { label: "MEMORY", value: "4.2 GB", icon: Activity },
  { label: "SECURITY", value: "ACTIVE", icon: Shield },
  { label: "UPTIME", value: "99.97%", icon: Zap },
];

const quickLinks = [
  { to: "/assistant", label: "Voice Assistant", desc: "Talk to JARVIS", icon: Mic, glow: "glow-cyan" },
  { to: "/notes", label: "Notes", desc: "3 records stored", icon: StickyNote, glow: "glow-purple" },
  { to: "/calendar", label: "Calendar", desc: "2 upcoming events", icon: CalendarDays, glow: "glow-cyan" },
  { to: "/tasks", label: "Daily Tasks", desc: "4 tasks pending", icon: ListChecks, glow: "glow-purple" },
];

const Index = () => {
  return (
    <div className="relative min-h-screen pt-20 pb-8 overflow-hidden">
      {/* Background */}
      <div
        className="absolute inset-0 bg-cover bg-center opacity-30"
        style={{ backgroundImage: `url(${jarvisBg})` }}
      />
      <div className="absolute inset-0 bg-gradient-to-b from-background/80 via-background/60 to-background" />

      <div className="relative z-10 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto">
        {/* Hero */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-8 mb-10">
          <motion.div
            initial={{ opacity: 0, x: -30 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.7 }}
            className="flex flex-col justify-center"
          >
            <div className="flex items-center gap-2 mb-4">
              <div className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
              <span className="text-xs font-mono text-green-400 tracking-widest">ALL SYSTEMS OPERATIONAL</span>
            </div>
            <h1 className="font-display text-4xl md:text-5xl font-bold text-primary glow-text tracking-wider leading-tight">
              J.A.R.V.I.S
            </h1>
            <p className="font-display text-sm text-muted-foreground tracking-[0.3em] mt-2 mb-6">
              JUST A RATHER VERY INTELLIGENT SYSTEM
            </p>
            <p className="text-foreground/70 font-body text-lg leading-relaxed max-w-md">
              Your personal AI operating system. Voice-controlled, intelligent, and always ready to assist.
            </p>

            <div className="flex gap-3 mt-8">
              <Link
                to="/assistant"
                className="flex items-center gap-2 px-6 py-3 rounded-xl bg-primary/15 border border-primary/30 text-primary font-body font-semibold text-sm hover:bg-primary/25 transition-all glow-border"
              >
                <Mic className="w-4 h-4" /> Activate JARVIS
              </Link>
            </div>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.7, delay: 0.2 }}
            className="flex items-center justify-center"
          >
            <JarvisAvatar size="lg" />
          </motion.div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-8">
          {stats.map((stat, i) => {
            const Icon = stat.icon;
            return (
              <HoloPanel key={stat.label} delay={0.1 + i * 0.05} className="!p-4">
                <div className="flex items-center gap-3">
                  <Icon className="w-5 h-5 text-primary" />
                  <div>
                    <p className="text-xs font-mono text-muted-foreground">{stat.label}</p>
                    <p className="text-lg font-display font-bold text-foreground">{stat.value}</p>
                  </div>
                </div>
              </HoloPanel>
            );
          })}
        </div>

        {/* Quick Links */}
        <h2 className="font-display text-sm tracking-widest text-muted-foreground mb-4">QUICK ACCESS</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {quickLinks.map((link, i) => {
            const Icon = link.icon;
            return (
              <Link key={link.to} to={link.to}>
                <HoloPanel delay={0.3 + i * 0.05} className="h-full cursor-pointer group">
                  <Icon className="w-8 h-8 text-primary mb-3 group-hover:scale-110 transition-transform" />
                  <h3 className="font-display text-sm font-semibold text-foreground tracking-wide">{link.label}</h3>
                  <p className="text-xs text-muted-foreground font-body mt-1">{link.desc}</p>
                </HoloPanel>
              </Link>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default Index;
