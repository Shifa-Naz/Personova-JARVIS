import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

const messages = [
  "Initializing system...",
  "Loading modules...",
  "Checking memory...",
  "Starting AI core...",
  "Connecting interface...",
  "Jarvis online",
];

const StartupPage = () => {

  const navigate = useNavigate();

  const [index, setIndex] = useState(0);

  useEffect(() => {

  const playSound = () => {

    const audio = new Audio("/sounds/boot.mp3");

    audio.volume = 0.7;

    audio.play().catch(() => {
      console.log("blocked");
    });

    window.removeEventListener("click", playSound);

  };

  window.addEventListener("click", playSound);

}, []);

  useEffect(() => {

    if (index < messages.length - 1) {

      const t = setTimeout(() => {
        setIndex(index + 1);
      }, 800);

      return () => clearTimeout(t);

    } else {

      setTimeout(() => {
        navigate("/");
      }, 1000);

    }

  }, [index]);


  useEffect(() => {

    const speech =
      new SpeechSynthesisUtterance(
        "System starting. Welcome back sir."
      );

    window.speechSynthesis.speak(speech);

  }, []);


  return (

    <div
      style={{
        height: "100vh",
        background: "black",
        color: "cyan",
        fontFamily: "monospace",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexDirection: "column",
      }}
    >

      <h1>JARVIS OS</h1>

      <p>
        {messages[index]}
      </p>

    </div>

  );

};

export default StartupPage;