import { motion } from "framer-motion";
import jarvisAvatar from "@/assets/jarvis-avatar.png";

interface JarvisAvatarProps {
  size?: "sm" | "md" | "lg";
  speaking?: boolean;
}

const sizeMap = {
  sm: "h-32",
  md: "h-56",
  lg: "h-80",
};

const JarvisAvatar = ({ size = "md", speaking = false }: JarvisAvatarProps) => {
  return (
    <div className="relative flex items-center justify-center">
      {/* Outer glow ring */}
      <motion.div
        className="absolute rounded-full border border-primary/20"
        style={{ width: "110%", height: "110%" }}
        animate={speaking ? { scale: [1, 1.1, 1], opacity: [0.3, 0.6, 0.3] } : { scale: 1, opacity: 0.2 }}
        transition={{ duration: 1.5, repeat: speaking ? Infinity : 0 }}
      />
      
      {/* Inner pulse ring */}
      <motion.div
        className="absolute rounded-full bg-primary/5"
        style={{ width: "90%", height: "90%" }}
        animate={speaking ? { scale: [0.95, 1.05, 0.95] } : {}}
        transition={{ duration: 1, repeat: Infinity }}
      />

      <motion.img
        src={jarvisAvatar}
        alt="JARVIS AI"
        className={`${sizeMap[size]} object-contain drop-shadow-[0_0_30px_hsla(190,100%,50%,0.4)] relative z-10`}
        animate={{ y: [0, -8, 0] }}
        transition={{ duration: 4, repeat: Infinity, ease: "easeInOut" }}
      />

      {/* Base glow */}
      <div className="absolute bottom-0 w-3/4 h-4 bg-primary/20 rounded-full blur-xl" />
    </div>
  );
};

export default JarvisAvatar;
