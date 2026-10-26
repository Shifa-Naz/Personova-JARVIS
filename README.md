# JARVIS

A voice-controlled desktop assistant for **Linux and Windows** that runs on your own computer. You can talk to it or
type. It answers questions, looks things up, reads your screen, keeps your tasks, calendar and notes, remembers what you
ask it to, and does things on your computer.

The language model never controls the computer directly. Every request becomes a plan of **registered, typed actions**.
JARVIS checks each step, asks you before anything that can't be undone, and only then runs it.

```
voice/text → speech-to-text → intent rules ─┬→ action plan → validate → permission → confirm? → execute → speak
                                            └→ offline LLM (JSON plan only, with a confidence score)
```

## What you can say

| Area | Examples |
|---|---|
| Questions | “What is polymorphism?”, “Explain that more simply” (follows the conversation), “How do I write a loop in my preferred language?” |
| Current information | “What's the weather in Belgaum today?” looks it up on the web and answers with sources |
| Memory | “Remember that I prefer C++”, “What language do I prefer?”, “What do you remember about me?”, “Forget that I prefer C++” |
| Tasks | “Remind me to submit the report tomorrow at 5 pm”, “Add a JARVIS task tomorrow”, “What are my tasks?”, “Mark the report as done”, “Move the report task to Friday” |
| Calendar | “Schedule team sync next Friday at 4 pm”, “What's on my calendar this week?”, “Cancel the dentist appointment” |
| Notes | “Take a note ask Ravi for repo access”, “Search notes for repo”, “Add push the fix to the Ravi note” |
| Screen | “What's on my screen?”, “Read my screen”, “What does the error on my screen say?” |
| Apps and web | “Open Chrome”, “Search for C++ tutorials”, “Search Python tutorials and open the first result”, “Play Believer on YouTube” |
| Files | “Create folder College”, “Copy report.pdf to Documents”, “Rename report.pdf to final”, “Open my resume”, “Delete report.pdf” (asks first, then moves it to the trash) |
| Media and system | “Play Believer” (local first, then offers YouTube), “Pause”, “Volume up”, “What's the battery?”, “Take a screenshot” |
| Refused | “Run the command …”, “Install …”, payments, sending messages, shutting down |

If a request is ambiguous ("delete report" when there are two), or a time is unclear ("at 5": AM or PM?), JARVIS asks you
instead of guessing.

## Setup

### 1. Backend (Python, conda)

```bash
conda create -n jarvis python=3.11 -y      # an existing "ultron" env works too
conda activate jarvis
cd backend
pip install -r requirements.txt
cp .env.example .env                        # Windows: copy .env.example .env
python run.py --download-models             # one-time: speech model + voice (~200 MB, needs internet)
python run.py --check                       # shows what's ready
python run.py                               # API on http://127.0.0.1:5000
```

Old `ULTRON_*` settings in `.env` still work, and the old data folder (`~/.local/share/ultron`) moves to
`~/.local/share/jarvis` on first start, so the downloaded models are kept.

### 2. Offline language model (Ollama)

Install Ollama from https://ollama.com, then:

```bash
sudo systemctl enable --now ollama          # Linux service (or run: ollama serve)
ollama pull llama3.2:3b                     # needs ~2.5 GB of free RAM while running
```

Set `JARVIS_LLM_MODEL` in `backend/.env`. A larger model such as `qwen2.5vl:3b`, which can also see images, needs about
5 GB of free RAM. If Ollama reports there isn't enough memory, JARVIS tells you instead of failing silently. Without the
model, every built-in command still works; only open-ended questions need it.

### 3. Frontend

```bash
cd frontend
npm ci
npm run dev                                 # http://localhost:8080
```

Say **“Jarvis”** and your request (“Jarvis, open Chrome”), or just “Jarvis” and JARVIS answers “Yes?” and listens.
**“Jarvis, are you up?”** gets “For you, always ma'am.” You can also
press **Space** or the mic to talk, **Esc** to cancel, and Space again to interrupt the voice. The wake phrase needs
offline speech recognition (faster-whisper) and a JARVIS tab open in your browser; turn it off under Voice and AI. Notes, tasks and events
are stored by the backend (in the data folder). Anything the old version kept only in your browser is imported
automatically the first time a page opens.

### Platform notes

- **Linux:** needs `xdg-open`, plus `wpctl` (PipeWire) or `pactl` for volume. `playerctl` is optional (`gdbus` MPRIS is the
  fallback). Screen capture on Wayland uses the desktop's screenshot portal, which may ask for permission the first time.
  Typing and clicking for you are unavailable on Wayland, and JARVIS says so.
- **Windows:** apps launch via ShellExecute (`chrome`, `ms-settings:` …). Media and volume use the media keys, and an exact
  volume level is approximate.
- Add your own apps with `JARVIS_CONFIG_FILE` (see `backend/jarvis.config.example.json`).

## Development

```bash
cd backend  && python -m pytest && ruff check . && ruff format --check .
cd frontend && npm run lint && npm test && npm run build
```

See [CLAUDE.md](CLAUDE.md) for the architecture, security model, design system and engineering rules.
