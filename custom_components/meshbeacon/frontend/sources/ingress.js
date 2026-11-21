// SPDX-License-Identifier: Apache-2.0
import { HassMessaging } from "./messaging.js";

// Module path is assets/<content hash>/sources/ingress.js. Keep the entire ingress prefix.
const BASE = new URL("../../../", import.meta.url);
export async function api(path, body) {
  let response;
  try {
    response = await fetch(new URL(`api/${path}`, BASE), {
      method: body === undefined ? "GET" : "POST", cache: "no-store", credentials: "same-origin",
      headers: body === undefined ? {} : { "Content-Type": "application/json", "X-Ito-Request": "1" },
      body: body === undefined ? undefined : JSON.stringify(body), signal: AbortSignal.timeout(45_000),
    });
    const answer = await response.json();
    if (!response.ok || answer.ok === false) throw { code: answer.error || "unavailable", problems: answer.problems };
    return answer;
  } catch (error) {
    throw error && error.code ? error : { code: "unavailable" };
  }
}

// Reuse the proven message model, drafts, pagination and send idempotency. Only transport differs.
export class IngressMessaging extends HassMessaging {
  async _call(kind, fields = {}) {
    return api("messaging", { op: kind, ...(kind === "history" ? { limit: 50 } : {}), ...fields });
  }
  _subscribe() {
    // Bounded polling only while visible. No read notifications or refresh feedback loop.
    if (!this._active || this._timer) return;
    this._timer = this._setTimeout(() => {
      this._timer = null;
      this._scheduleRefresh();
      this._subscribe();
    }, 5_000);
  }
}
