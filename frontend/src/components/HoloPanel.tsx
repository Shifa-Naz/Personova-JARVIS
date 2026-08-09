import { ReactNode } from "react";
import { motion } from "framer-motion";

interface HoloPanelProps {
  children: ReactNode;
  title?: string;
  className?: string;
  delay?: number;
}

const HoloPanel = ({ children, title, className = "", delay = 0 }: HoloPanelProps) => {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.5, delay, ease: "easeOut" }}
      className={`floating-card relative ${className}`}
    >
      <div className="scan-line" />
      {title && (
        <div className="flex items-center gap-3 mb-4">
          <div className="w-1.5 h-6 rounded-full bg-primary/60" />
          <h3 className="font-display text-sm tracking-widest uppercase text-primary glow-text">
            {title}
          </h3>
          <div className="flex-1 holographic-line" />
        </div>
      )}
      {children}
    </motion.div>
  );
};

export default HoloPanel;
