# CLAUDE.md — JARVIS Desktop AI Assistant

> Primary engineering instructions for Claude Code sessions in this repository.
>
> **Scope note:** a parent-directory file (`~/Downloads/CLAUDE.md`, "Belgaum Matrimony" Laravel project) is
> also loaded by Claude Code here. **It does not apply to this repository.** Ignore its stack, palette and modules.
>
> **Governing spec:** `Personova_JARVIS_Detailed_0_to_100_Claude_Handoff.pdf` (repo root). Section numbers in the form
> "PDF §n" below refer to it. §20 gives the status against it.

This file has three parts: rules (§0), what exists now (§1–§16, verified), and what is still missing (§17–§20).
Don't treat a planned item as implemented.

---

## 0. Operating rules (non-negotiable)

1. Inspect the existing implementation before modifying it.
2. Never rewrite working functionality without a measurable reason.
3. Prefer small, isolated changes; don't modify unrelated files.
4. No duplicate implementations. There is ONE action layer (`backend/jarvis/actions`), ONE intent matcher
   (`core/intent.py` + `core/personal.py`) and ONE assistant state machine (`frontend/src/features/assistant`).
5. Never hardcode API keys or credentials; config comes from env (`backend/.env`, `frontend/.env.local`).
6. **Never give the AI unrestricted shell access.** No `shell=True`, `eval`, `exec`, or string-built commands.
7. **All OS side effects go through a registered `ActionSpec` → `Pipeline` → platform adapter.**
8. SENSITIVE and DESTRUCTIVE actions require confirmation. That is enforced by the pipeline, not by callers.
9. Validate every AI-generated step with the action's pydantic schema (`extra="forbid"`).
10. Every feature has explicit error handling with a typed `error_code` and a speakable message.
11. Every major feature has tests. Backend tests use `FakeAdapter`/`FakeAI`/`FakeOcr`/`FakeSynth` and **never touch the
    real system**.
12. Don't break existing behaviour: run both test suites before finishing.
13. Keep UI, AI reasoning and OS execution decoupled. React never controls the OS (PDF §4).
14. Structured commands are typed: pydantic on the backend, TS interfaces in `features/assistant/types.ts` (keep in sync).
15. Don't use `sleep`/`setTimeout` for synchronization (cosmetic UI animation and polling an OS condition with a deadline
    are fine).
16. Don't hide errors: no bare `except` that swallows, no silent `return ""`.
17. Never silently perform destructive actions; deletion goes to the OS trash, never `os.remove`.
18. Never log or display secrets, clipboard contents, typed text, screen text or file contents (`sensitive_params`,
    `redact()`, `mask_secrets()`).
19. Prefer deterministic rules/actions over free-form AI output.
20. When intent is ambiguous, ask (`AMBIGUOUS` → `needs_clarification`) rather than guess.
21. Never claim success without checking the result (copy verifies size, app launch checks the process list, etc.).

**Core principle:** the AI decides *WHAT* should happen; the application decides *HOW* it safely happens.

### Feature workflow
Understand → find the existing implementation → read the surrounding code → check dependencies → plan → make the smallest
change → run tests/lint/build → fix regressions → review security (§9–§11) → report exactly what changed.

### Project decisions (set by the user)
- **Name:** **JARVIS** (renamed from ULTRON on 2026-10-11). Old `ULTRON_*` env vars, the `~/.local/share/ultron` data dir
  and `ultron_*` browser keys are migrated automatically. Don't remove those fallbacks. The visual identity stays original:
  no Marvel assets or logos.
- **Demo OS:** Linux and Windows. The dev machine is Fedora 44, GNOME 50 on Wayland, 16 GB RAM.
- **AI:** offline-first. Ollama runs the local LLM (`llama3.2:3b` fits; `qwen2.5vl:3b` needs ~4.9 GiB free and failed to
  load on the dev machine). faster-whisper does STT, Piper does TTS, RapidOCR does screen text.
- The user creates the Python env with **conda** and tests manually. Don't create envs in the repo.

---

## 1. Architecture

```
Browser (React, :8080) — dashboard, console, tasks, calendar, notes
  AssistantProvider (state machine) ── Space/mic ──► STT: offline Whisper (POST /transcribe) or browser recognition
     │  page navigation handled in-browser (localCommands.ts); everything else goes to the backend
     │  POST /plan → plan shown live (THINKING → EXECUTING) → POST /execute/stream (answer words appear as written) → reply (Markdown) + speech (short) → Piper
     │  needs_confirmation / needs_clarification → dialog or voice "yes|no" → POST /confirm
     │  results with data.changed → "jarvis-data-changed" event → pages refetch /items
     ▼
Flask API (127.0.0.1:5000 only)  host check · origin allow-list · per-launch X-Jarvis-Token
  Pipeline (core/pipeline.py)
    IntentMatcher (core/intent.py; productivity/memory/file rules in core/personal.py; dates in nlp/dates.py)
       ─UNKNOWN→ Ollama planner (ai/provider.py, JSON schema incl. confidence; < 0.45 → ask)
    ActionRegistry.validate (pydantic) → BLOCKED? refuse → online? → prepare (bind exact targets)
    → SENSITIVE/DESTRUCTIVE? ConfirmationStore (single-use, 60 s) → handler with timeout → ActionResult (+ Offer)
    → ExecResponse {success, response_type, reply, speech, results, confirmation, request_id}
  JsonStore (storage/store.py): memory, notes, tasks, events — atomic writes, corruption recovery
  Platform adapters: LinuxAdapter | WindowsAdapter (FakeAdapter in tests)
  FileSearchService (background index, ranked, root-confined) · OcrEngine · Transcriber · Synthesizer
  SessionContext: in-memory history + last file/media/search (resolves "it", "that song", "the first result")
```

## 2. Directory structure

```
backend/
  run.py                      python run.py [--check | --download-models]; migrates the legacy data dir
  requirements.txt · .env.example · jarvis.config.example.json · pyproject.toml (ruff + pytest)
  jarvis/
    app.py                    Flask factory, security guard, /api/v1 routes (incl. /items), build_services()
    config.py                 Settings, load_settings() (loopback only, ULTRON_* fallback), migrate_legacy_data_dir()
    logging_setup.py          JSON rotating log, redact(), recent_events ring buffer
    actions/                  base.py, registry.py, conversation.py, memory.py, productivity.py, web.py, apps.py,
                              browser.py, files.py, media.py, system.py, screen.py, automation.py; build_registry()
    core/                     intent.py, personal.py, pipeline.py, context.py
    nlp/                      dates.py (date/time extraction + ambiguity), speech.py (Markdown → short spoken text)
    storage/store.py          JsonStore
    ai/                       provider.py (answer, answer_with_memory, answer_from_sources, plan, describe_screen), prompts.py
    platform/                 base.py, linux.py (incl. Wayland portal screenshot), windows.py, fake.py, apps.py
    files/search.py · security/confirmation.py · vision/ocr.py · voice/stt.py · voice/tts.py
  tests/                      conftest (fakes, temp home) + test_intent, test_pipeline, test_files, test_api,
                              test_actions, test_screen, test_tts, test_dates, test_pdf_features
frontend/src/
  App.tsx                     router + AssistantProvider + navbar + overlay + global confirmation dialog
  lib/api.ts                  JarvisClient (token handshake, 401 refresh, typed calls incl. items CRUD/import)
  lib/storage.ts              shared Task/Note/CalEvent types, browser cache, legacy import helpers, date formatting
  hooks/                      use-items (backend data + offline cache + one-time import), use-telemetry
  features/assistant/         types.ts, machine.ts, AssistantProvider.tsx, context.ts, speech.ts, localCommands.ts,
                              phase.ts (state → label/colour), actionNames.ts
  components/hud/             CoreVisualizer, StatusReadout, Transcript (Markdown), PlanSteps (action card),
                              CommandBar, ConfirmationDialog, TelemetryPanel, SettingsPanel, LogsPanel
  components/                 JarvisNavbar (Wordmark), JarvisOverlay, HoloPanel (flat panel), PageHeader, ui/ (shadcn)
  pages/                      Index (dashboard), AssistantPage (console), TasksPage, CalendarPage, NotesPage, About, Startup
```

## 3. Commands

```bash
# backend (inside the user's conda env)
cd backend && python run.py --check          # capability report (LLM, STT, TTS, OCR, data folder, internet)
cd backend && python run.py                  # start API
cd backend && python -m pytest               # 234 tests (+1 that needs JARVIS_TEST_VOICE_DIR for real Piper)
cd backend && ruff check . && ruff format --check .
# frontend
cd frontend && npm ci && npm run dev         # :8080
cd frontend && npm run lint && npm test && npm run build    # 40 tests
```
Lint baseline: 0 errors, 7 `react-refresh` warnings, all in untouched shadcn `components/ui/*`.

## 4. API (all JSON, `/api/v1`)

| Endpoint | Auth | Purpose |
|---|---|---|
| `GET /health` | none | liveness |
| `GET /session` | origin-checked | per-launch token, platform, capabilities |
| `GET /status` · `GET /system` | token | capabilities · live telemetry |
| `POST /plan {text, session_id}` | token | intent, confidence, entities, risk, validated steps, `plan_id` (single use, 120 s) |
| `POST /execute {plan_id}` · `POST /execute/stream` (SSE: `delta` events, then `done` with the ExecResponse) · `POST /confirm {confirmation_id, decision}` · `POST /command {text}` | token | run / answer a confirmation / plan+run |
| `GET/POST /items/<notes\|tasks\|events>`, `PATCH/DELETE /items/<kind>/<id>`, `POST /items/<kind>/import` | token | the pages' data (same store the assistant uses); unknown fields dropped |
| `POST /transcribe` (audio) · `POST /speak {text}` (→ WAV) | token | offline STT / TTS; 503 when not installed |
| `GET /logs/recent` | token | redacted pipeline events |

`ExecResponse` (PDF §19): `success`, `response_type` (conversation | action | confirmation | clarification | error),
`reply` (Markdown for the page), `speech` (short plain text for the voice), `results[]`, `confirmation`, `request_id`.

## 5. Actions (the complete allow-list)

| Group | Actions | Permission |
|---|---|---|
| Conversation | `reply`, `answer_question` (memory-aware, Markdown), `calculate`, `web_answer` (online, with sources) | READ_ONLY |
| Memory | `memory_save` (explicit only, refuses secrets) SAFE · `memory_recall`, `memory_list` READ_ONLY · `memory_update`, `memory_forget` SENSITIVE | mixed |
| Tasks / events / notes | `*_create`, `*_update`, `task_complete/reopen` SAFE · `*_list`, `note_search/read` READ_ONLY · `*_delete` DESTRUCTIVE | mixed |
| Files | `find_file` RO · `open_file`, `open_folder`, `create_folder`, `create_file` (text types only, never overwrites), `copy_file` (verifies; offers overwrite) SAFE · `rename_file` SENSITIVE · `delete_files` (trash), `move_file` DESTRUCTIVE | mixed |
| Apps / web / media | `open_application` (verifies process), `open_url`, `search_web`, `search_youtube`, `play_youtube`, `open_first_result`, `play_media`, `media_control`, `volume_control` SAFE · `close_application` SENSITIVE | mixed |
| System / screen | `system_information`, `clipboard_read`, `describe_screen` RO · `screenshot` SAFE · `clipboard_write` SENSITIVE | mixed |
| Input automation | `scroll` SAFE · `type_text`, `press_key`, `click_text` (OCR match verified, never blind) SENSITIVE | mixed |
| Refused | `blocked_request` (shell, scripts, install, payments, messages, shutdown) | BLOCKED |

To add an action: a `Params` model + handler (+ `prepare` to bind targets before confirming) in `actions/*.py`, add it to
`SPECS`, add intent rules (`core/personal.py` for productivity-style phrasing), and add tests with the fakes.

## 6. Intent handling

Normalization strips "jarvis" (as a prefix, suffix, or "hey/ok jarvis"); "hello jarvis" stays a greeting. Matching runs
on lowercase text, and `restore_case()` puts the user's capitalisation back into titles, names and notes. Order inside a
segment:

1. **Storage matchers** (tasks, events, notes, memory). They only store text, so they run before the safety filter.
2. The BLOCKED filter.
3. Small talk, math, system info, media, screen.
4. File create/copy/rename.
5. First result, YouTube, web, sites, apps, folders, files, play, delete/move, keyboard.
6. Requests for written content (`_GENERATIVE`: write, translate, draft…, or create/make/give me a program, poem,
   email…), then questions. Anything that needs current information goes to `web_answer`.
7. Anything else that doesn't start with an action verb (`_ACTION_START`) is conversation → `answer_question`. Only
   action-like leftovers reach the LLM planner, which is slow on CPU. The planner uses
   `registry.catalog_compact()` (about 1.3k tokens, down from about 4.8k with the JSON catalog, which took about 3 min
   to read on the dev CPU).

Compound requests split only on `,`, `and` or `then` followed by a command verb (`_VERBS`). After splitting, "it"
resolves to the previous step's title, "open the first result" resolves to the previous search (web or YouTube), and
browser steps merge. Dates come from `nlp/dates.extract_when`; ambiguous ones ("at 5", "10/11") become a clarification.
Each plan carries `confidence`: rules use defaults by intent, and the LLM reports its own, with values below 0.45 turned
into a question.

## 7. Frontend state machine & voice

States: `OFFLINE, IDLE, LISTENING, PROCESSING, THINKING, EXECUTING, SPEAKING, SUCCESS, ERROR, CONFIRMATION_REQUIRED`
(labels and colours in `phase.ts`). Re-entry is guarded with refs (`busyRef`, `listeningRef`).
- Each JARVIS reply message carries its plan and per-step results, rendered by `PlanSteps` as an action card.
- Only the final `speech` is spoken (PDF §20). There are no "let me look" acknowledgements.
- After a question, a voice turn listens again automatically.
- Space interrupts speech, Esc cancels, the composer has a stop-speaking button, and the navbar has Retry when offline.
- **Wake word "Jarvis"** (`features/assistant/wake.ts`, loop in `AssistantProvider`). The name must come first:
  - "Jarvis" (or "Hey Jarvis") → "Yes?" (`NAME_REPLY`), then JARVIS listens.
  - "Jarvis, <anything>" → runs it directly.
  - "Jarvis, are you up?" → "For you, always ma'am.", then JARVIS listens.
  - **How it listens:** only while the phase is IDLE and offline Whisper is available. It records short speech bursts
    (`recordUtterance` uses `setInterval`, so it keeps working in background tabs) and sends them to
    `POST /transcribe?hint=wake`, which biases Whisper toward the name. It never runs while JARVIS speaks.
  - **What it does:** on a match it submits the phrase. The backend replies "For you, always ma'am." (`WAKE_REPLY` in
    `core/intent.py`). Speech bursts can be up to about 9 s, so long commands fit.
  - **Limits:** the setting is `wake` (on by default), and it works only while a JARVIS tab is open.
- TTS: the `local` engine is Piper via `/speak` on Web Audio, and the core follows the real output level. It falls back
  to `speechSynthesis`.

## 8. Design system

The concept is a "bridge console": a quiet, flat instrument surface where the reactor core is the one bold element. Tokens
live in `index.css` and are exposed through Tailwind.
- **Colours:**
  - Abyss `#0A1220` (page) and Hull `#111B2B` (panels), with Seam `#223349` hairlines.
  - Frost `#E8F0F8` text, Mist `#8DA2BA` secondary text.
  - **Ice `#9BE7FF` = JARVIS, voice and primary controls.**
  - **Ember `#FFB547` = actions on the computer, plans and confirmations.**
  - Signal `#FF5C5C` = destructive or error; Moss `#5BE49B` = done.
- **Type** (bundled with `@fontsource`, so it works offline):
  - **Chakra Petch** for the wordmark, headings and readings.
  - **IBM Plex Sans** for body text, chat and UI.
  - **IBM Plex Mono** only for code, log times and data.
- **Rules:**
  - Sentence-case labels; no tracked all-caps eyebrows, no "A · B" meta strings, no mono for small labels.
  - `.panel` is one surface with one hairline: no glows and no hover lifts.
  - Motion: the core's rings plus one boot-in (`.core-boot`). Respect `prefers-reduced-motion`.
  - Tap targets are at least 44 px. Pages were checked at 390 and 1280 px with zero horizontal overflow.
- **Copy:** plain verbs from the user's side ("Mark done", "Yes, do it"). Errors say what happened and what to do next.

## 9. Platform adapters

- **Linux:**
  - `xdg-open` for files and links; apps are found on PATH or as installed flatpaks.
  - Media via `playerctl` or `gdbus` MPRIS; volume via `wpctl` or `pactl`; clipboard via pyperclip.
  - **Screenshots on Wayland go through xdg-desktop-portal** (`portal_screenshot`, jeepney). Pillow's ImageGrab fails on
    GNOME Wayland (verified).
- **Windows:** `os.startfile` / argv `Popen`; media and volume via media keys. **Never run on Windows yet.**
- **Input automation** (pyautogui) is disabled on Wayland and reported as `AUTOMATION_UNAVAILABLE`.

## 10. Security model

- **Network exposure:**
  - Loopback bind only, and the Host header must be loopback (DNS-rebinding defence).
  - CORS plus a server-side Origin allow-list, and a per-launch token on every `/api` call except health/session.
- **Treating outside content as data:**
  - AI output is data. The JSON schema restricts action names, the registry rejects unknown actions and fields, and
    BLOCKED actions are excluded from the catalog.
  - Web search results are untrusted. They go to the model labelled as search results, with an instruction to ignore
    anything they say, and are never executed.
- **Privacy:**
  - Memory only saves what the user asks it to, and refuses passwords, PINs, card and account numbers.
  - Screen text is masked for token-like strings and never logged; the screenshot temp file is always deleted.
- **Files:** confined to the search roots (resolved paths, no symlinks); empty or short queries match nothing.

## 11. Confirmation rules

- READ_ONLY and SAFE run directly.
- The LLM planner never gets `reply`, and a planner "answer" that claims it did something is refused: only executed
  steps change anything (rule 21).
- SENSITIVE and DESTRUCTIVE: `prepare` binds the exact targets, then the user confirms with the button or by voice within
  60 s. Confirmations are single-use and bound to the session, and any new command abandons them.
- Offers ("Search online?", "Replace it?") use the same mechanism with `kind: "offer"`.
- An `AMBIGUOUS` error becomes `needs_clarification`.

## 12. Logging & configuration

- **Logs:** JSON lines in `<data_dir>/logs/jarvis.log`, with events `plan`, `action`, `confirmation_required`,
  `confirmation`, `blocked` and `llm_plan_rejected`.
- **Data:** the data dir is `~/.local/share/jarvis` (or `%APPDATA%\jarvis`). It contains `data/*.json` (store),
  `voices/`, `models/` and `tmp/`.
- **Settings:** all are in `backend/.env.example`: `JARVIS_HOST/PORT/DEBUG/ALLOWED_ORIGINS`, `JARVIS_LLM_*` (incl. `JARVIS_LLM_THREADS`),
  `JARVIS_VISION_MODEL`, `JARVIS_STT_*`, `JARVIS_TTS_*`, `JARVIS_SEARCH_ROOTS`, `JARVIS_DATA_DIR`,
  `JARVIS_TESSERACT_CMD` and `JARVIS_CONFIG_FILE`.
- **Frontend:** `VITE_JARVIS_API_URL`.

## 13. Offline vs online

| Works offline | Needs internet |
|---|---|
| Everything except the items on the right: apps, files, media, system, screen reading, memory, tasks/calendar/notes, rule commands, Ollama, Whisper, Piper | `web_answer`, `open_first_result`, web and YouTube search, browser STT |

Online actions fail with `OFFLINE` and a spoken explanation.

## 14. Testing

- **Backend** (pytest, 234): an intent table including regressions of the original bugs and the PDF acceptance phrases.
  Also covered:
  - the pipeline: confirmations, offers, offline, blocked, LLM validation, confidence, speech and the contract fields;
  - files, including create/copy/rename and ambiguity;
  - API security and the items API;
  - the date parser;
  - memory, including secrets and context;
  - productivity, the web parser (ads and redirects), OCR/screen and TTS;
  - the store's corruption recovery.
- **Frontend** (vitest, 40): wake-phrase matching, state machine, local navigation, the storage cache and legacy import, malformed JSON, the API
  client token refresh, and the TTS fallback.
- **Manual end-to-end** (2026-10-11, Fedora, headless Chrome, real backend and `llama3.2:3b`):
  - voice-style commands created tasks and events, and a Markdown answer with a code block rendered;
  - the destructive dialog appeared, and pages showed zero overflow at 390 and 1280 px with no console errors.
- **Earlier checks:** a live portal capture plus RapidOCR (about 4 s) and Piper speech.

## 15. Coding standards & naming

- **Python:** 3.11+, type hints, ruff, pydantic/dataclasses, `logging` not `print`, argv lists only.
- **Naming:** actions are `snake_case` verbs, error codes are `UPPER_SNAKE`, env vars are `JARVIS_*`.
- **TypeScript:** no `any`; UI never calls `fetch` directly (use `lib/api.ts`); use Tailwind tokens, never raw hex in
  components.

## 16. Git

Small, scoped commits. Never commit `.env`, logs, `node_modules` or `dist`. **Commit or push only when the user asks.**
Note: nothing after the initial commit has been committed yet, so new files are untracked and `git mv` fails on them.

---

## 17. Known limitations

- **Windows:** never run there. Exact volume is approximate, and Piper playback and screen capture are untested.
- **qwen2.5vl:3b:** needs about 4.9 GiB free, so on the 16 GB dev machine use `llama3.2:3b`. The vision path is untested
  with a real model.
- **Wake phrase limits:** it needs offline Whisper and an open JARVIS tab, and it's verified only with synthetic speech so
  far (about 0.45 s per check). In a noisy room, background speech is transcribed locally, which costs CPU, and
  near-misses of the name may need adding to `wake.ts`.
- **No in-page browser automation:** there's no Playwright, so JARVIS can't click inside pages. Search, play and
  first-result are URL-based, and `play_youtube` parses YouTube's HTML, which is fragile.
- **Web retrieval** depends on DuckDuckGo's HTML endpoint, which can change or rate-limit.
- **Speed** (qwen2.5vl:3b, i5-1240P, measured 2026-10-14 in the browser): answers stream, first word after about 7 s,
  a full short answer in about 12 s (capped at 320 tokens). The model is warmed up at start and kept loaded 30 min, with
  8 threads. "What's on my screen" takes about 30 s: OCR 6–12 s plus about 18 s of the model. The screenshot goes to the
  vision model only when OCR finds fewer than 4 lines, at 448 px, because a 1280 px image took over 4 min.
- **Concurrency:** one global pipeline lock, so a long LLM answer blocks other `/plan` calls. Timeouts stop waiting but
  can't kill the worker thread.
- **Tests:** there are no committed Playwright e2e specs, and no Windows acceptance run.

## 18. Roadmap / next priorities

1. Run the PDF §25 acceptance list on Windows.
3. Playwright e2e specs in `frontend/e2e/` (the console flow, confirmations, the pages).
4. Optional Playwright browser automation for in-page actions.
5. Stream LLM answers to the UI to cut the perceived latency.

## 19. Acceptance — final demo scenario

1. Start the backend and frontend. The dashboard greets you with today's tasks and events and live readings.
2. Say "Jarvis, are you up?" → "For you, always ma'am." → LISTENING (or press Space). Say "Open YouTube and search for Java DSA tutorials". You see the plan card, the results open, and
   JARVIS asks "play the first one?" → "yes".
3. "What is polymorphism?" → a Markdown answer with code on screen and a short spoken version. "Explain that more
   simply" → uses the context.
4. "Remember that I prefer C++" → "What language do I prefer?" → "You prefer C++."
5. "Add a JARVIS task tomorrow" → it appears on Tasks and the dashboard. "Schedule team sync Friday at 4 pm" → it
   appears on Calendar.
6. "Read my screen" → useful text. "Copy report.pdf to Documents" → the copy exists. "Delete report.pdf" → a dialog
   first.
7. "What's the weather in Belgaum today?" → an answer with sources. With the internet off, you get OFFLINE and local
   commands still work.
8. Mic denied, backend offline, AI unavailable → each gives a clear message and the UI stays usable.

## 20. Status against the PDF

| PDF section | Status |
|---|---|
| §5 Assistant UI | Done: typed input with Enter, mic start/stop, state machine, history, Markdown/code, loading, stop speaking, retry/offline, voice, context, action and confirmation cards, configurable URL |
| §6 Frontend defects | Fixed: stale state, retry loops, overlapping recognisers, navigation from raw text, duplicate speech, missing offline state |
| §7 Productivity | Done: notes, tasks and calendar CRUD by voice and on the pages, dates/priority, ambiguity questions, malformed-JSON safety, one reminder per day |
| §8, §19 Backend and API contract | Done |
| §9, §11 NLP and planner | Done (rules-first): intent, confidence, entities, steps, risk, context, clarification |
| §10 Splitter bug | Fixed |
| §12 Conversation | Done: Ollama, Markdown, follow-ups, memory context, provider abstraction |
| §13, §14 Commands and files | Done: copy verifies, trash-based delete, structured move/rename/copy with overwrite handling, never a blind click, typed results |
| §15 Vision/OCR | Done, except "find text on screen" as a separate action and OCR word boxes in the API |
| §16 Memory | Done: explicit only, categories, update/forget, corruption recovery, used as context |
| §17 Tools | Done (names differ; same capabilities), except `browser_click/type` |
| §18 Current information | Done (`web_answer`, separate from the conversation model) |
| §21, §22 Security and setup | Done |
| §23 Testing | Partial: no committed browser e2e specs, no Windows run |
| §25 Acceptance | Passes on Linux, with fakes for OS side effects plus manual checks. Windows is pending |
| §4 "Preserve the JARVIS theme/avatar" | The user chose to restyle the UI. Routes, Notes/Tasks/Calendar and their data (migrated) are preserved |
