import { ApiError } from "./api";

export interface UploadOpts {
  partSize?: number;
  onProgress?: (received: number) => void;
  /** 续传时从服务器已收到的字节数开始，避免白发一段服务器已有的数据 */
  startOffset?: number;
  fetchImpl?: typeof fetch;
  /** 重试前的等待，测试里注入假的以免真等 */
  sleep?: (ms: number) => Promise<void>;
}

const MAX_RETRY = 3;
const realSleep = (ms: number) => new Promise<void>((res) => setTimeout(res, ms));

/** 从错误响应里取出给人看的话：detail 是字符串或 {message, ...}。 */
async function errorText(r: Response): Promise<string> {
  try {
    const j = await r.json();
    const d = j.detail;
    if (typeof d === "string") return d;
    if (d && typeof d.message === "string") return d.message;
    return JSON.stringify(d ?? j);
  } catch {
    return r.statusText || `HTTP ${r.status}`;
  }
}

/**
 * 分段上传到 /api/kb/docs/{id}/content，全部传完后调 /complete。
 * 偏移量以服务器为准：409 返回 received_bytes（含 0，表示服务器丢了临时文件要从头传），就从那里继续。
 * 网络错误或 5xx 同一段最多重试 3 次；重试时仍发当前 offset，服务器若已收到会用 409 告知真实位置。
 */
export async function uploadInParts(file: Blob, docId: number, opts: UploadOpts = {}): Promise<void> {
  const partSize = opts.partSize ?? 8 * 1024 * 1024;
  const doFetch = opts.fetchImpl ?? fetch;
  const sleep = opts.sleep ?? realSleep;
  const backoff = () => sleep(1000 * 2 ** (failures - 1)); // 第 n 次重试前等 1s、2s、4s
  const base = `/api/kb/docs/${docId}`;
  let offset = opts.startOffset ?? 0;
  let failures = 0; // 当前这段连续失败（网络错误 / 5xx / 没推进的 409）次数
  while (offset < file.size) {
    const body = file.slice(offset, offset + partSize);
    let r: Response;
    try {
      r = await doFetch(`${base}/content?offset=${offset}`, {
        method: "PUT", credentials: "include", headers: { "Content-Type": "application/octet-stream" }, body,
      });
    } catch (e) {
      if (++failures > MAX_RETRY) throw new ApiError(0, `网络错误：${(e as Error).message || e}`);
      await backoff();
      continue;
    }
    if (r.status === 401) {
      if (window.location.pathname !== "/login") window.location.assign("/login");
      throw new ApiError(401, "未登录");
    }
    if (r.ok) {
      const j = await r.json();
      offset = typeof j.received_bytes === "number" ? j.received_bytes : offset + body.size;
      failures = 0;
      opts.onProgress?.(offset);
      continue;
    }
    if (r.status === 409) {
      let received: unknown;
      let msg = "";
      try {
        const j = await r.json();
        received = j.detail?.received_bytes;
        msg = typeof j.detail === "string" ? j.detail : j.detail?.message ?? "";
      } catch { /* 非 JSON */ }
      if (typeof received !== "number") throw new ApiError(409, msg || "上传状态冲突");
      if (received === offset) {
        if (++failures > MAX_RETRY) throw new ApiError(409, msg || "服务器偏移量一直对不上");
        await backoff();
      }
      offset = received;
      opts.onProgress?.(offset);
      continue;
    }
    if (r.status >= 500) {
      const msg = await errorText(r);
      if (++failures > MAX_RETRY) throw new ApiError(r.status, msg);
      await backoff();
      continue;
    }
    throw new ApiError(r.status, await errorText(r)); // 其他 4xx 重试没有意义
  }
  const done = await doFetch(`${base}/complete`, { method: "POST", credentials: "include" });
  if (!done.ok) throw new ApiError(done.status, await errorText(done));
}
