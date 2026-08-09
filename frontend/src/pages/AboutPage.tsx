import { motion } from "framer-motion";
import { Cpu, Code2, Layers, Mic, Brain, Shield } from "lucide-react";
import HoloPanel from "@/components/HoloPanel";
import JarvisAvatar from "@/components/JarvisAvatar";

const techStack = [
  { name: "React + TypeScript", desc: "Core framework & type safety", icon: Code2 },
  { name: "Tailwind CSS", desc: "Utility-first styling system", icon: Layers },
  { name: "Framer Motion", desc: "Fluid animations & transitions", icon: Cpu },
  { name: "Voice API", desc: "Speech recognition & synthesis", icon: Mic },
  { name: "AI Engine", desc: "Natural language processing", icon: Brain },
  { name: "Lovable Cloud", desc: "Backend, auth & database", icon: Shield },
];

const AboutPage = () => {
  return (
    <div className="min-h-screen pt-20 pb-8 px-4 sm:px-6 lg:px-8 max-w-7xl mx-auto">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        <div>
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}>
            <h1 className="font-display text-3xl font-bold text-primary glow-text tracking-wider mb-2">PROJECT J.A.R.V.I.S</h1>
            <p className="text-muted-foreground font-body text-sm mb-6">Just A Rather Very Intelligent System</p>
          </motion.div>

          <HoloPanel title="OVERVIEW" delay={0.1}>
            <p className="text-sm font-body text-foreground/80 leading-relaxed">
              J.A.R.V.I.S is a futuristic AI operating system interface inspired by Marvel's iconic AI assistant. 
              This project serves as a holographic dashboard that combines voice-controlled interaction, 
              intelligent task management, note-taking, and calendar scheduling into a single, 
              seamlessly integrated experience.
            </p>
            <p className="text-sm font-body text-foreground/80 leading-relaxed mt-3">
              Designed to feel like an AI that boots up with your system, JARVIS provides a 
              sci-fi command center experience with glassmorphism panels, neon accents, 
              and smooth holographic animations.
            </p>
          </HoloPanel>

          <HoloPanel title="ARCHITECTURE" delay={0.2} className="mt-4">
            <div className="space-y-3">
              <div className="flex items-center gap-3 p-3 rounded-lg bg-primary/5 border border-primary/10">
                <div className="w-2 h-2 rounded-full bg-primary" />
                <span className="text-sm font-mono text-foreground/80">Frontend → React + Vite + TypeScript</span>
              </div>
              <div className="flex items-center gap-3 p-3 rounded-lg bg-accent/5 border border-accent/10">
                <div className="w-2 h-2 rounded-full bg-accent" />
                <span className="text-sm font-mono text-foreground/80">Styling → Tailwind CSS + Glassmorphism</span>
              </div>
              <div className="flex items-center gap-3 p-3 rounded-lg bg-jarvis-teal/5 border border-jarvis-teal/10">
                <div className="w-2 h-2 rounded-full bg-jarvis-teal" />
                <span className="text-sm font-mono text-foreground/80">Animation → Framer Motion</span>
              </div>
              <div className="flex items-center gap-3 p-3 rounded-lg bg-jarvis-blue/5 border border-jarvis-blue/10">
                <div className="w-2 h-2 rounded-full bg-jarvis-blue" />
                <span className="text-sm font-mono text-foreground/80">Backend → Lovable Cloud (Supabase)</span>
              </div>
            </div>
          </HoloPanel>
        </div>

        <div>
          <HoloPanel delay={0.15} className="flex items-center justify-center py-12">
            <JarvisAvatar size="lg" />
          </HoloPanel>

          <HoloPanel title="TECHNOLOGY STACK" delay={0.25} className="mt-4">
            <div className="grid grid-cols-2 gap-3">
              {techStack.map((tech, i) => {
                const Icon = tech.icon;
                return (
                  <motion.div
                    key={tech.name}
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: 0.3 + i * 0.05 }}
                    className="p-3 rounded-lg bg-secondary/50 border border-border/50 hover:border-primary/20 transition-all"
                  >
                    <Icon className="w-5 h-5 text-primary mb-2" />
                    <p className="text-sm font-body font-semibold text-foreground">{tech.name}</p>
                    <p className="text-xs text-muted-foreground">{tech.desc}</p>
                  </motion.div>
                );
              })}
            </div>
          </HoloPanel>
        </div>
      </div>
    </div>
  );
};

export default AboutPage;
