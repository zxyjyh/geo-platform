import { describe, expect, it } from "vitest";
import { uploadInParts } from "./upload";

type Call = { method: string; url: string; size: number };

/** 假服务器：按 handler 决定每次 PUT 的响应；记录所有调用。 */
function fakeFetch(handler: (call: Call, n: number) => Response) {
  const calls: Call[] = [];
  const impl = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const body = init?.body as Blob | undefined;
    const call = { method: init?.method ?? "GET", url: String(input), size: body?.size ?? 0 };
    calls.push(call);
    return handler(call, calls.length - 1);
  }) as typeof fetch;
  return { impl, calls };
}
const json = (status: number, body: unknown) => new Response(JSON.stringify(body), { status });
const offsetOf = (url: string) => Number(new URL(url, "http://x").searchParams.get("offset"));
const noSleep = async () => undefined;
const file = () => new Blob([new Uint8Array(25)]);

describe("uploadInParts", () => {
  it("uploads all parts in order then completes", async () => {
    const { impl, calls } = fakeFetch((c) => (c.method === "PUT" ? json(200, { received_bytes: offsetOf(c.url) + c.size }) : json(200, {})));
    await uploadInParts(file(), 7, { partSize: 10, fetchImpl: impl, sleep: noSleep });
    expect(calls.map((c) => c.method)).toEqual(["PUT", "PUT", "PUT", "POST"]);
    expect(calls.slice(0, 3).map((c) => offsetOf(c.url))).toEqual([0, 10, 20]);
    expect(calls.slice(0, 3).map((c) => c.size)).toEqual([10, 10, 5]);
    expect(calls[0].url).toBe("/api/kb/docs/7/content?offset=0");
    expect(calls[3].url).toBe("/api/kb/docs/7/complete");
  });

  it("startOffset resumes an existing doc without resending data the server has", async () => {
    const { impl, calls } = fakeFetch((c) => (c.method === "PUT" ? json(200, { received_bytes: offsetOf(c.url) + c.size }) : json(200, {})));
    await uploadInParts(file(), 7, { partSize: 10, startOffset: 10, fetchImpl: impl, sleep: noSleep });
    expect(calls.map((c) => c.method)).toEqual(["PUT", "PUT", "POST"]);
    expect(calls.slice(0, 2).map((c) => offsetOf(c.url))).toEqual([10, 20]);
  });

  it("upload resumes from server offset on 409", async () => {
    const { impl, calls } = fakeFetch((c, n) => {
      if (c.method === "POST") return json(200, {});
      if (n === 1) return json(409, { detail: { message: "偏移量不对", received_bytes: 20 } });
      return json(200, { received_bytes: offsetOf(c.url) + c.size });
    });
    await uploadInParts(file(), 1, { partSize: 10, fetchImpl: impl, sleep: noSleep });
    expect(calls.filter((c) => c.method === "PUT").map((c) => offsetOf(c.url))).toEqual([0, 10, 20]);
    expect(calls[calls.length - 1].method).toBe("POST");
  });

  it("409 with received_bytes 0 restarts from the beginning", async () => {
    const { impl, calls } = fakeFetch((c, n) => {
      if (c.method === "POST") return json(200, {});
      if (n === 1) return json(409, { detail: { message: "临时文件已丢失", received_bytes: 0 } });
      return json(200, { received_bytes: offsetOf(c.url) + c.size });
    });
    await uploadInParts(file(), 1, { partSize: 10, fetchImpl: impl, sleep: noSleep });
    expect(calls.filter((c) => c.method === "PUT").map((c) => offsetOf(c.url))).toEqual([0, 10, 0, 10, 20]);
  });

  it("retries a failed part at most 3 times", async () => {
    const { impl, calls } = fakeFetch(() => json(500, { detail: "boom" }));
    await expect(uploadInParts(file(), 1, { partSize: 10, fetchImpl: impl, sleep: noSleep })).rejects.toThrow();
    expect(calls).toHaveLength(4); // 首次 + 重试 3 次
  });

  it("waits 1s, 2s, 4s before the three retries", async () => {
    const { impl } = fakeFetch(() => json(503, { detail: "busy" }));
    const waits: number[] = [];
    await expect(uploadInParts(file(), 1, { partSize: 10, fetchImpl: impl, sleep: async (ms) => { waits.push(ms); } })).rejects.toThrow();
    expect(waits).toEqual([1000, 2000, 4000]);
  });

  it("recovers when a transient network error succeeds on retry", async () => {
    let failed = false;
    const { impl, calls } = fakeFetch((c) => {
      if (c.method === "PUT" && !failed) { failed = true; throw new TypeError("network"); }
      return c.method === "PUT" ? json(200, { received_bytes: offsetOf(c.url) + c.size }) : json(200, {});
    });
    await expect(uploadInParts(file(), 1, { partSize: 10, fetchImpl: impl, sleep: noSleep })).resolves.toBeUndefined();
    // 失败的第一段重发一次，之后每段只发一次
    expect(calls.filter((c) => c.method === "PUT").map((c) => offsetOf(c.url))).toEqual([0, 0, 10, 20]);
  });

  it("after a lost response, the retry gets 409 and does not resend that part", async () => {
    let lost = false;
    let server = 0;
    const { impl, calls } = fakeFetch((c) => {
      if (c.method === "POST") return json(200, {});
      const off = offsetOf(c.url);
      if (off !== server) return json(409, { detail: { message: "偏移量不对", received_bytes: server } });
      server += c.size;
      if (off === 10 && !lost) { lost = true; throw new TypeError("response lost"); } // 服务器收到了但响应丢了
      return json(200, { received_bytes: server });
    });
    await uploadInParts(file(), 1, { partSize: 10, fetchImpl: impl, sleep: noSleep });
    expect(calls.filter((c) => c.method === "PUT").map((c) => offsetOf(c.url))).toEqual([0, 10, 10, 20]);
    expect(server).toBe(25);
  });

  it("does not retry client errors and surfaces the server message", async () => {
    const { impl, calls } = fakeFetch(() => json(422, { detail: "上传的字节数超过了声明的文件大小" }));
    await expect(uploadInParts(file(), 1, { partSize: 10, fetchImpl: impl, sleep: noSleep })).rejects.toThrow("超过了声明");
    expect(calls).toHaveLength(1);
  });

  it("surfaces complete errors such as duplicate file", async () => {
    const { impl } = fakeFetch((c) => (c.method === "PUT"
      ? json(200, { received_bytes: offsetOf(c.url) + c.size })
      : json(409, { detail: "这份文件已经上传过：2025年刊" })));
    await expect(uploadInParts(file(), 1, { partSize: 10, fetchImpl: impl, sleep: noSleep })).rejects.toThrow("已经上传过：2025年刊");
  });

  it("reports progress", async () => {
    const { impl } = fakeFetch((c) => (c.method === "PUT" ? json(200, { received_bytes: offsetOf(c.url) + c.size }) : json(200, {})));
    const seen: number[] = [];
    await uploadInParts(file(), 1, { partSize: 10, fetchImpl: impl, sleep: noSleep, onProgress: (n) => seen.push(n) });
    expect(seen).toEqual([10, 20, 25]);
  });
});
