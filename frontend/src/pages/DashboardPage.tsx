import { useEffect, useState } from "react";
import HoloPanel from "@/components/HoloPanel";

const DashboardPage = () => {

  const [time, setTime] = useState("");
  const [date, setDate] = useState("");

  const [tasks, setTasks] = useState(0);
  const [events, setEvents] = useState(0);

  useEffect(() => {

    const update = () => {

      const now = new Date();

      setTime(now.toLocaleTimeString());
      setDate(now.toDateString());

      const t =
        localStorage.getItem("jarvis_tasks");

      const e =
        localStorage.getItem("jarvis_events");

      if (t) setTasks(JSON.parse(t).length);
      if (e) setEvents(JSON.parse(e).length);

    };

    update();

    const i = setInterval(update, 1000);

    return () => clearInterval(i);

  }, []);

  return (

    <div className="min-h-screen pt-20 px-6">

      <h1 className="text-2xl font-bold mb-6">
        JARVIS DASHBOARD
      </h1>


      <div className="grid grid-cols-3 gap-4">


        <HoloPanel title="TIME">

          <h2>{time}</h2>
          <p>{date}</p>

        </HoloPanel>


        <HoloPanel title="TASKS">

          <h2>{tasks}</h2>
          <p>Pending tasks</p>

        </HoloPanel>


        <HoloPanel title="EVENTS">

          <h2>{events}</h2>
          <p>Saved events</p>

        </HoloPanel>


        <HoloPanel title="SYSTEM">

          <p>CPU OK</p>
          <p>Memory OK</p>
          <p>Network OK</p>
          <p>AI Core OK</p>

        </HoloPanel>


        <HoloPanel title="STATUS">

          <p>Jarvis Online</p>

        </HoloPanel>


      </div>

    </div>

  );

};

export default DashboardPage;