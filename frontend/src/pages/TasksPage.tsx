import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Plus, Check, Trash2, Clock, AlertTriangle } from "lucide-react";
import HoloPanel from "@/components/HoloPanel";

interface Task {
  id: string;
  title: string;
  completed: boolean;
  priority: "high" | "medium" | "low";
  time?: string;
}

const priorityStyles = {
  high: "border-red-500/30 bg-red-500/5",
  medium: "border-yellow-500/30 bg-yellow-500/5",
  low: "border-cyan-500/30 bg-cyan-500/5",
};

const priorityLabels = {
  high: { label: "CRITICAL", icon: AlertTriangle },
  medium: { label: "STANDARD", icon: Clock },
  low: { label: "LOW", icon: Clock },
};

const TasksPage = () => {

  const [tasks, setTasks] = useState<Task[]>([]);
  const [newTitle, setNewTitle] = useState("");
  const [newPriority, setNewPriority] =
    useState<"high" | "medium" | "low">("medium");

  const [showAdd, setShowAdd] = useState(false);


  // LOAD TASKS

  useEffect(() => {

    const saved =
      localStorage.getItem("jarvis_tasks");

    if (saved) {
      setTasks(JSON.parse(saved));
    }

  }, []);


  // SAVE TASKS

  useEffect(() => {

    localStorage.setItem(
      "jarvis_tasks",
      JSON.stringify(tasks)
    );

  }, [tasks]);


  const toggle = (id: string) => {

    setTasks((prev) =>
      prev.map((t) =>
        t.id === id
          ? { ...t, completed: !t.completed }
          : t
      )
    );

  };


  const remove = (id: string) => {

    setTasks((prev) =>
      prev.filter((t) => t.id !== id)
    );

  };


  const addTask = () => {

    if (!newTitle.trim()) return;

    const t: Task = {
      id: Date.now().toString(),
      title: newTitle,
      completed: false,
      priority: newPriority,
    };

    setTasks((prev) => [t, ...prev]);

    setNewTitle("");

    setShowAdd(false);

  };


  const pending =
    tasks.filter((t) => !t.completed);

  const completed =
    tasks.filter((t) => t.completed);


  return (

    <div className="min-h-screen pt-20 px-4 max-w-7xl mx-auto">


      <h1 className="text-2xl font-bold mb-6">
        DAILY TASKS
      </h1>


      <button
        onClick={() => setShowAdd(!showAdd)}
        className="border px-3 py-1 mb-4"
      >
        Add Task
      </button>



      {showAdd && (

        <HoloPanel>

          <input
            value={newTitle}
            onChange={(e) =>
              setNewTitle(
                e.target.value
              )
            }
          />

          <select
            value={newPriority}
            onChange={(e) =>
              setNewPriority(
                e.target.value as any
              )
            }
          >

            <option value="high">
              High
            </option>

            <option value="medium">
              Medium
            </option>

            <option value="low">
              Low
            </option>

          </select>

          <button onClick={addTask}>
            Save
          </button>

        </HoloPanel>

      )}



      {/* PENDING */}

      <h2>Pending</h2>

      {pending.map((task) => {

        const P =
          priorityLabels[
            task.priority
          ];

        return (

          <div
            key={task.id}
            className={`p-3 border ${priorityStyles[task.priority]}`}
          >

            <button
              onClick={() =>
                toggle(task.id)
              }
            >
              <Check />
            </button>

            {task.title}

            <button
              onClick={() =>
                remove(task.id)
              }
            >
              <Trash2 />
            </button>

          </div>

        );

      })}



      {/* COMPLETED */}

      <h2 className="mt-6">
        Completed
      </h2>

      {completed.map((task) => (

        <div
          key={task.id}
          className="p-3 border opacity-50"
        >

          {task.title}

        </div>

      ))}

    </div>

  );

};

export default TasksPage;