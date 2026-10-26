import { describe, expect, it, vi } from "vitest";
import { ApiError, BackendUnreachable, JarvisClient } from "@/lib/api";

const json = (status: number, body: unknown) =>
  Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));

const session = (token: string) => ({ token, platform: "linux", version: "x", capabilities: {} });

describe("JarvisClient", () => {
  it("sends the session token on authenticated calls", async () => {
    const fetchMock = vi.fn((url: string) => (url.endsWith("/session") ? json(200, session("t1")) : json(200, { status: "ready" })));
    const client = new JarvisClient("http://api", fetchMock as unknown as typeof fetch);
    await client.plan("open chrome");
    const [, init] = fetchMock.mock.calls[1] as unknown as [string, RequestInit];
    expect((init.headers as Record<string, string>)["X-Jarvis-Token"]).toBe("t1");
    expect(JSON.parse(init.body as string)).toEqual({ text: "open chrome", session_id: "ui" });
  });

  it("refreshes the token once after a backend restart (401)", async () => {
    let tokens = 0;
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (url.endsWith("/session")) return json(200, session(`t${++tokens}`));
      const tok = (init?.headers as Record<string, string>)["X-Jarvis-Token"];
      return tok === "t2" ? json(200, { ok: true }) : json(401, { error_code: "UNAUTHORIZED", reply: "bad" });
    });
    const client = new JarvisClient("http://api", fetchMock as unknown as typeof fetch);
    await expect(client.status()).resolves.toEqual({ ok: true });
    expect(tokens).toBe(2);
  });

  it("maps network failures to BackendUnreachable and HTTP errors to ApiError", async () => {
    const down = new JarvisClient("http://api", (() => Promise.reject(new TypeError("fetch failed"))) as unknown as typeof fetch);
    await expect(down.connect()).rejects.toBeInstanceOf(BackendUnreachable);

    const forbidden = new JarvisClient("http://api", (() => json(403, { error_code: "FORBIDDEN_ORIGIN", reply: "no" })) as unknown as typeof fetch);
    await expect(forbidden.connect()).rejects.toMatchObject({ code: "FORBIDDEN_ORIGIN", status: 403 });
    await expect(forbidden.connect()).rejects.toBeInstanceOf(ApiError);
  });
});

describe("executeStream", () => {
  it("passes answer pieces as they arrive, then returns the final response", async () => {
    const sse = [
      'data: {"type":"delta","text":"Hello"}\n\n',
      'data: {"type":"delta","text":", world."}\n\n',
      'data: {"type":"done","response":{"reply":"Hello, world.","status":"done"}}\n\n',
    ];
    const body = new ReadableStream({
      start(c) {
        sse.forEach((chunk) => c.enqueue(new TextEncoder().encode(chunk)));
        c.close();
      },
    });
    const fetchMock = vi.fn((url: string) =>
      url.endsWith("/session") ? json(200, session("t1")) : Promise.resolve(new Response(body, { status: 200 })),
    );
    const client = new JarvisClient("http://api", fetchMock as unknown as typeof fetch);
    const pieces: string[] = [];
    const resp = await client.executeStream("p1", (t) => pieces.push(t));
    expect(pieces).toEqual(["Hello", ", world."]);
    expect(resp.reply).toBe("Hello, world.");
  });
});
