import { motion } from "framer-motion";
import { Mic, MicOff } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import JarvisAvatar from "@/components/JarvisAvatar";
import HoloPanel from "@/components/HoloPanel";

const AssistantPage = () => {

  const navigate = useNavigate();

  const [isListening, setIsListening] = useState(false);

  const [messages, setMessages] = useState<
    { role: "user" | "jarvis"; text: string }[]
  >([
    {
      role: "jarvis",
      text: "Jarvis online. How can I help you sir?",
    },
  ]);


  const speak = (text: string) => {

    window.speechSynthesis.cancel();

    const speech =
      new SpeechSynthesisUtterance(text);

    speech.onend = () => {
      startListening();
    };

    window.speechSynthesis.speak(speech);

  };


  const startListening = () => {

    const SpeechRecognition =
      (window as any).SpeechRecognition ||
      (window as any).webkitSpeechRecognition;

    if (!SpeechRecognition) return;

    const recognition =
      new SpeechRecognition();

    recognition.lang = "en-US";

    recognition.continuous = false;

    recognition.interimResults = false;

    setIsListening(true);

    recognition.start();


    recognition.onresult = async (event: any) => {

      const text =
        event.results[0][0].transcript;

      const lower =
        text.toLowerCase();

      console.log("User:", text);


      try {

        const res = await fetch(
          "http://127.0.0.1:5000/command",
          {
            method: "POST",
            headers: {
              "Content-Type":
                "application/json",
            },
            body: JSON.stringify({
              command: text,
            }),
          }
        );

        const data =
          await res.json();

        const reply =
          data.reply || "";

        setMessages((prev) => [
          ...prev,
          { role: "user", text },
          { role: "jarvis", text: reply },
        ]);

        if (reply) {
          speak(reply);
        } else {
          startListening();
        }

      } catch (e) {

        console.log(e);

        startListening();

      }


      // navigation

      if (lower.includes("note")) {
        navigate("/notes");
      }

      else if (lower.includes("calendar")) {
        navigate("/calendar");
      }

      else if (lower.includes("task")) {
        navigate("/tasks");
      }

      else if (
        lower.includes("dashboard") ||
        lower.includes("home")
      ) {
        navigate("/dashboard");
      }

      else if (
        lower.includes("assistant")
      ) {
        navigate("/assistant");
      }


      setIsListening(false);

    };


    recognition.onerror = () => {
      startListening();
    };


    recognition.onend = () => {

      if (isListening) {
        startListening();
      }

    };

  };


  return (

    <div className="min-h-screen pt-20 px-4 max-w-7xl mx-auto">

      <div className="grid grid-cols-3 gap-4">

        <HoloPanel>

          <JarvisAvatar
            size="lg"
            speaking={isListening}
          />

          <p>
            {isListening
              ? "Listening"
              : "Standby"}
          </p>

        </HoloPanel>


        <HoloPanel className="col-span-2">

          {messages.map(
            (m, i) => (

              <div key={i}>
                {m.role} : {m.text}
              </div>

            )
          )}


          <button
            onClick={startListening}
          >
            {isListening
              ? <MicOff />
              : <Mic />}
          </button>

        </HoloPanel>

      </div>

    </div>

  );

};

export default AssistantPage;