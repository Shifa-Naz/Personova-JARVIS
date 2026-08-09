import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Plus, Trash2, Search } from "lucide-react";
import HoloPanel from "@/components/HoloPanel";

interface Note {
  id: string;
  title: string;
  content: string;
  date: string;
  color: string;
}

const colors = [
  "border-jarvis-cyan/30 bg-jarvis-cyan/5",
  "border-jarvis-purple/30 bg-jarvis-purple/5",
  "border-jarvis-teal/30 bg-jarvis-teal/5",
  "border-jarvis-blue/30 bg-jarvis-blue/5",
];

const NotesPage = () => {

  const [notes, setNotes] = useState<Note[]>([]);
  const [search, setSearch] = useState("");
  const [newTitle, setNewTitle] = useState("");
  const [newContent, setNewContent] = useState("");
  const [showAdd, setShowAdd] = useState(false);

  // LOAD NOTES FROM STORAGE
  useEffect(() => {
    const saved = localStorage.getItem("jarvis_notes");

    if (saved) {
      setNotes(JSON.parse(saved));
    }
  }, []);

  // SAVE NOTES TO STORAGE
  useEffect(() => {
    localStorage.setItem("jarvis_notes", JSON.stringify(notes));
  }, [notes]);


  const filteredNotes = notes.filter(
    (n) =>
      n.title.toLowerCase().includes(search.toLowerCase()) ||
      n.content.toLowerCase().includes(search.toLowerCase())
  );


  const addNote = () => {

    if (!newTitle.trim()) return;

    const note: Note = {
      id: Date.now().toString(),
      title: newTitle,
      content: newContent,
      date: new Date().toLocaleString(),
      color: colors[notes.length % colors.length],
    };

    setNotes((prev) => [note, ...prev]);

    setNewTitle("");
    setNewContent("");
    setShowAdd(false);
  };


  const deleteNote = (id: string) => {
    setNotes((prev) => prev.filter((n) => n.id !== id));
  };


  return (

    <div className="min-h-screen pt-20 pb-8 px-4 max-w-7xl mx-auto">


      {/* HEADER */}

      <div className="flex justify-between mb-6">

        <div>
          <h1 className="text-2xl font-bold text-primary">
            NOTES DATABASE
          </h1>

          <p>{notes.length} notes stored</p>
        </div>


        <div className="flex gap-2">

          <div className="relative">

            <Search className="absolute left-2 top-2 w-4 h-4" />

            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search"
              className="pl-8 border rounded-lg px-3 py-1"
            />

          </div>


          <button
            onClick={() => setShowAdd(!showAdd)}
            className="px-3 py-1 border rounded-lg"
          >
            <Plus className="w-4 h-4 inline" /> Add
          </button>

        </div>

      </div>



      {/* ADD NOTE */}

      <AnimatePresence>

        {showAdd && (

          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
          >

            <HoloPanel>

              <input
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder="Title"
                className="w-full border mb-2"
              />

              <textarea
                value={newContent}
                onChange={(e) => setNewContent(e.target.value)}
                placeholder="Content"
                className="w-full border mb-2"
              />

              <button
                onClick={addNote}
                className="border px-3 py-1"
              >
                Save
              </button>

            </HoloPanel>

          </motion.div>

        )}

      </AnimatePresence>



      {/* NOTES */}

      <div className="grid grid-cols-3 gap-3">

        {filteredNotes.map((note) => (

          <div
            key={note.id}
            className={`p-3 border ${note.color}`}
          >

            <div className="flex justify-between">

              <h3>{note.title}</h3>

              <Trash2
                className="w-4 h-4 cursor-pointer"
                onClick={() => deleteNote(note.id)}
              />

            </div>

            <p>{note.content}</p>

            <small>{note.date}</small>

          </div>

        ))}

      </div>


    </div>

  );
};

export default NotesPage;