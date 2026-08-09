import { useEffect, useState } from "react";
import JarvisAvatar from "@/components/JarvisAvatar";

const JarvisOverlay = () => {

  const [time, setTime] = useState("");
  const [date, setDate] = useState("");
  const [pulse, setPulse] = useState(false);

  useEffect(() => {

    const update = () => {

      const now = new Date();

      setTime(now.toLocaleTimeString());
      setDate(now.toDateString());

    };

    update();

    const t = setInterval(update, 1000);

    const p = setInterval(() => {
      setPulse(v => !v);
    }, 700);

    const speech =
      new SpeechSynthesisUtterance(
        "Welcome back sir. All systems online."
      );

    window.speechSynthesis.speak(speech);

    return () => {
      clearInterval(t);
      clearInterval(p);
    };

  }, []);

  return (

    <div
      style={{
        position: "fixed",
        bottom: 0,
        right: 40,
        zIndex: 9999,
        pointerEvents: "none",
        textAlign: "center",
      }}
    >

      {/* hologram glow */}

      <div
        style={{
          transform: pulse
            ? "scale(1.05)"
            : "scale(1)",

          transition: "0.4s",

          filter:
            "drop-shadow(0 0 25px cyan)",

          animation:
            "float 4s ease-in-out infinite",
        }}
      >

        <JarvisAvatar
          size="lg"
          speaking={pulse}
        />

      </div>


      {/* time */}

      <div
        style={{
          color: "cyan",
          fontFamily: "monospace",
          fontSize: 12,
          marginTop: -10,
          textShadow:
            "0 0 10px cyan",
        }}
      >
        {time}
      </div>


      {/* date */}

      <div
        style={{
          color: "white",
          fontSize: 10,
          opacity: 0.7,
        }}
      >
        {date}
      </div>

    </div>

  );

};

export default JarvisOverlay;