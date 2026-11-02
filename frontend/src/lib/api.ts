import type {
  ItemKind,
  ExecResponse,
  LogEvent,
  PlanResponse,
  SessionInfo,
  Telemetry,
  Capabilities,
  Briefing,
  Headline,
  JarvisEvent,
} from "@/features/assistant/types";

export const API_BASE: string =
  (import.meta.env.VITE_JARVIS_API_URL as string | undefined) ??
  (import.meta.env.VITE_ULTRON_API_URL as string | undefined) ?? // legacy name
  "http://127.0.0.1:5000";

export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status = 0,
  ) {
    super(message);
  }
}

/** Thrown when the backend can't be reached at all (not started, crashed). */
export class BackendUnreachable extends ApiError {
  constructor() {
    super("BACKEND_UNREACHABLE", "I can't reach the JARVIS backend. Is it running?");
  }
}

type FetchLike = typeof fetch;

export class JarvisClient {
  private session: SessionInfo | null = null;
  private sessionPromise: Promise<SessionInfo> | null = null;

  constructor(
    private base = API_BASE,
    private fetchImpl: FetchLike = (input, init) => fetch(input, init),
    public sessionId = "ui",
  ) {}

  async connect(force = false): Promise<SessionInfo> {
    if (this.session && !force) return this.session;
    if (!this.sessionPromise || force) {
      this.sessionPromise = this.raw<SessionInfo>("GET", "/api/v1/session", undefined, false)
        .then((s) => {
          this.session = s;
          return s;
        })
        .finally(() => {
          this.sessionPromise = null;
        });
    }
    return this.sessionPromise;
  }

  private async raw<T>(
    method: string,
    path: string,
    body?: BodyInit | object,
    auth = true,
    contentType?: string,
    as: "json" | "blob" = "json",
  ): Promise<T> {
    const headers: Record<string, string> = {};
    if (auth && this.session) headers["X-Jarvis-Token"] = this.session.token;
    let payload: BodyInit | undefined;
    if (body instanceof Blob) {
      payload = body;
      headers["Content-Type"] = contentType ?? (body.type || "application/octet-stream");
    } else if (body !== undefined) {
      payload = JSON.stringify(body);
      headers["Content-Type"] = "application/json";
    }
    let res: Response;
    try {
      res = await this.fetchImpl(`${this.base}${path}`, { method, headers, body: payload });
    } catch {
      throw new BackendUnreachable();
    }
    if (res.ok && as === "blob") return (await res.blob()) as T;
    let data: unknown = null;
    try {
      data = await res.json();
    } catch {
      data = null;
    }
    if (!res.ok) {
      const d = (data ?? {}) as { error_code?: string; reply?: string };
      throw new ApiError(d.error_code ?? `HTTP_${res.status}`, d.reply ?? `Request failed (${res.status})`, res.status);
    }
    return data as T;
  }

  /** Authenticated call; re-fetches the token once if the backend restarted (401). */
  private async call<T>(
    method: string,
    path: string,
    body?: BodyInit | object,
    contentType?: string,
    as: "json" | "blob" = "json",
  ): Promise<T> {
    await this.connect();
    try {
      return await this.raw<T>(method, path, body, true, contentType, as);
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        await this.connect(true);
        return this.raw<T>(method, path, body, true, contentType, as);
      }
      throw err;
    }
  }

  plan(text: string) {
    return this.call<PlanResponse>("POST", "/api/v1/plan", { text, session_id: this.sessionId });
  }

  execute(planId: string) {
    return this.call<ExecResponse>("POST", "/api/v1/execute", { plan_id: planId, session_id: this.sessionId });
  }

  /**
   * Run a plan and receive answer text while the model is still writing it (Server-Sent Events).
   * `onDelta` gets each new piece; resolves with the final response.
   */
  async executeStream(planId: string, onDelta: (text: string) => void, onSay?: (sentence: string) => void): Promise<ExecResponse> {
    await this.connect();
    const send = () =>
      this.fetchImpl(`${this.base}/api/v1/execute/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Jarvis-Token": this.session?.token ?? "" },
        body: JSON.stringify({ plan_id: planId, session_id: this.sessionId }),
      });
    let res: Response;
    try {
      res = await send();
      if (res.status === 401) {
        await this.connect(true);
        res = await send();
      }
    } catch {
      throw new BackendUnreachable();
    }
    if (!res.ok || !res.body) throw new ApiError(`HTTP_${res.status}`, `Request failed (${res.status})`, res.status);

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let cut: number;
      while ((cut = buffer.indexOf("\n\n")) >= 0) {
        const event = buffer.slice(0, cut);
        buffer = buffer.slice(cut + 2);
        const line = event.split("\n").find((l) => l.startsWith("data: "));
        if (!line) continue;
        const msg = JSON.parse(line.slice(6)) as { type: string; text?: string; response?: ExecResponse };
        if (msg.type === "delta" && msg.text) onDelta(msg.text);
        if (msg.type === "say" && msg.text) onSay?.(msg.text);
        if (msg.type === "done" && msg.response) return msg.response;
      }
    }
    throw new ApiError("STREAM_ENDED", "The answer stopped before it finished.");
  }

  confirm(confirmationId: string, decision: "confirm" | "cancel") {
    return this.call<ExecResponse>("POST", "/api/v1/confirm", {
      confirmation_id: confirmationId,
      decision,
      session_id: this.sessionId,
    });
  }

  status() {
    return this.call<{ platform: string; capabilities: Capabilities }>("GET", "/api/v1/status");
  }

  system(processes = false) {
    return this.call<Telemetry>("GET", processes ? "/api/v1/system?processes=1" : "/api/v1/system");
  }

  /** Today's schedule, tech headlines and a machine check, ready to show and speak. */
  briefing() {
    return this.call<Briefing>("GET", "/api/v1/briefing");
  }

  news(count = 5) {
    return this.call<{ items: Headline[]; offline: boolean }>("GET", `/api/v1/news?count=${count}`);
  }

  /** Long-poll for backend events (the lid-open briefing). `after = -1` returns recent ones at once. */
  events(after: number, waitS = 25) {
    return this.call<{ seq: number; events: JarvisEvent[] }>("GET", `/api/v1/events?after=${after}&wait=${waitS}`);
  }

  logs() {
    return this.call<{ events: LogEvent[] }>("GET", "/api/v1/logs/recent");
  }

  // ---- notes / tasks / events (the same store the assistant uses) ----
  listItems<T>(kind: ItemKind) {
    return this.call<{ items: T[] }>("GET", `/api/v1/items/${kind}`).then((r) => r.items);
  }

  createItem<T>(kind: ItemKind, item: Partial<T>) {
    return this.call<{ item: T }>("POST", `/api/v1/items/${kind}`, item as object).then((r) => r.item);
  }

  updateItem<T>(kind: ItemKind, id: string, patch: Partial<T>) {
    return this.call<{ item: T }>("PATCH", `/api/v1/items/${kind}/${encodeURIComponent(id)}`, patch as object).then(
      (r) => r.item,
    );
  }

  deleteItem(kind: ItemKind, id: string) {
    return this.call<{ deleted: string }>("DELETE", `/api/v1/items/${kind}/${encodeURIComponent(id)}`);
  }

  importItems<T>(kind: ItemKind, items: T[]) {
    return this.call<{ imported: number; items: T[] }>("POST", `/api/v1/items/${kind}/import`, { items });
  }

  /** Offline TTS: returns a WAV blob synthesized by the backend's Piper voice. */
  speak(text: string): Promise<Blob> {
    return this.call<Blob>("POST", "/api/v1/speak", { text }, undefined, "blob");
  }

  /** `hint: "wake"` biases offline Whisper toward the wake phrase. Confidence is 0-1. */
  async transcribe(audio: Blob, hint?: "wake"): Promise<{ text: string; confidence: number }> {
    const path = hint ? `/api/v1/transcribe?hint=${hint}` : "/api/v1/transcribe";
    const res = await this.call<{ text: string; confidence?: number }>("POST", path, audio, audio.type.split(";")[0] || "audio/webm");
    return { text: res.text, confidence: res.confidence ?? 1 };
  }
}

export const jarvis = new JarvisClient();
