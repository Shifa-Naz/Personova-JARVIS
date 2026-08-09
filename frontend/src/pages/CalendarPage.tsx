import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronLeft, ChevronRight, Plus, X } from "lucide-react";
import HoloPanel from "@/components/HoloPanel";

interface CalEvent {
  id: string;
  date: string;
  title: string;
  time: string;
}

const CalendarPage = () => {

  const [currentDate, setCurrentDate] = useState(new Date());
  const [events, setEvents] = useState<CalEvent[]>([]);
  const [selectedDate, setSelectedDate] = useState<string | null>(null);

  const [newEvent, setNewEvent] = useState({
    title: "",
    time: "",
  });

  const [showAdd, setShowAdd] = useState(false);


  // LOAD EVENTS

  useEffect(() => {
    const saved = localStorage.getItem("jarvis_events");

    if (saved) {
      setEvents(JSON.parse(saved));
    }
  }, []);


  // SAVE EVENTS

  useEffect(() => {
    localStorage.setItem(
      "jarvis_events",
      JSON.stringify(events)
    );
  }, [events]);


  // REMINDER CHECK

  useEffect(() => {

    const today = new Date();
    const tomorrow = new Date();

    tomorrow.setDate(today.getDate() + 1);

    const tStr =
      tomorrow.toISOString().split("T")[0];

    const tomorrowEvents = events.filter(
      (e) => e.date === tStr
    );

    if (tomorrowEvents.length > 0) {

      const text =
        "You have event tomorrow: " +
        tomorrowEvents[0].title;

      const speech =
        new SpeechSynthesisUtterance(text);

      window.speechSynthesis.speak(speech);

      alert(text);
    }

  }, [events]);


  const year = currentDate.getFullYear();
  const month = currentDate.getMonth();

  const firstDay =
    new Date(year, month, 1).getDay();

  const daysInMonth =
    new Date(year, month + 1, 0).getDate();


  const days = [];

  for (let i = 0; i < firstDay; i++) {
    days.push(null);
  }

  for (let i = 1; i <= daysInMonth; i++) {
    days.push(i);
  }


  const dateStr = (d: number) =>
    `${year}-${String(month + 1).padStart(
      2,
      "0"
    )}-${String(d).padStart(2, "0")}`;


  const eventsForDate = (d: number) =>
    events.filter(
      (e) => e.date === dateStr(d)
    );


  const addEvent = () => {

    if (!selectedDate) return;

    const ev: CalEvent = {
      id: Date.now().toString(),
      date: selectedDate,
      title: newEvent.title,
      time: newEvent.time,
    };

    setEvents((prev) => [
      ...prev,
      ev,
    ]);

    setNewEvent({
      title: "",
      time: "",
    });

    setShowAdd(false);
  };


  const removeEvent = (id: string) => {

    setEvents((prev) =>
      prev.filter(
        (e) => e.id !== id
      )
    );

  };


  const prevMonth = () =>
    setCurrentDate(
      new Date(year, month - 1, 1)
    );

  const nextMonth = () =>
    setCurrentDate(
      new Date(year, month + 1, 1)
    );


  const dayEvents = selectedDate
    ? events.filter(
        (e) =>
          e.date === selectedDate
      )
    : [];


  return (

    <div className="min-h-screen pt-20 px-4 max-w-7xl mx-auto">

      <h1 className="text-2xl font-bold mb-6">
        CALENDAR
      </h1>


      <div className="grid grid-cols-3 gap-4">


        {/* CALENDAR */}

        <HoloPanel className="col-span-2">

          <div className="flex justify-between mb-4">

            <button onClick={prevMonth}>
              <ChevronLeft />
            </button>

            <h2>
              {year} / {month + 1}
            </h2>

            <button onClick={nextMonth}>
              <ChevronRight />
            </button>

          </div>


          <div className="grid grid-cols-7 gap-1">

            {days.map((day, i) => {

              if (day === null)
                return (
                  <div key={i} />
                );

              const ds =
                dateStr(day);

              const hasEvents =
                eventsForDate(day)
                  .length > 0;

              return (

                <button
                  key={ds}
                  onClick={() =>
                    setSelectedDate(ds)
                  }
                  className="p-2 border"
                >

                  {day}

                  {hasEvents && (
                    <div className="w-1 h-1 bg-red-500" />
                  )}

                </button>

              );

            })}

          </div>

        </HoloPanel>



        {/* EVENTS */}

        <HoloPanel>

          {selectedDate && (

            <div>

              {dayEvents.map(
                (ev) => (

                  <div
                    key={ev.id}
                    className="flex justify-between"
                  >

                    <div>
                      {ev.title}
                      {ev.time}
                    </div>

                    <X
                      onClick={() =>
                        removeEvent(ev.id)
                      }
                    />

                  </div>

                )
              )}


              {showAdd ? (

                <div>

                  <input
                    value={newEvent.title}
                    onChange={(e) =>
                      setNewEvent({
                        ...newEvent,
                        title:
                          e.target.value,
                      })
                    }
                  />

                  <input
                    type="time"
                    value={newEvent.time}
                    onChange={(e) =>
                      setNewEvent({
                        ...newEvent,
                        time:
                          e.target.value,
                      })
                    }
                  />

                  <button
                    onClick={addEvent}
                  >
                    Save
                  </button>

                </div>

              ) : (

                <button
                  onClick={() =>
                    setShowAdd(true)
                  }
                >
                  Add Event
                </button>

              )}

            </div>

          )}

        </HoloPanel>

      </div>

    </div>

  );

};

export default CalendarPage;