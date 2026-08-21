// Thin wrapper for the Sale live-inbox endpoints (backend/routers/sale_live.py). Sale is
// always authenticated with a Bearer token, so this reuses the generic `api` client rather
// than the visitor-token-aware `customerApi`.

import { api } from "./client";
import type { LiveInboxEntry, MessageResponse } from "../types";

export const saleLiveApi = {
  listWaiting: () => api.get<LiveInboxEntry[]>("/sale/live-inbox"),
  /** Sessions this Sale has already claimed and is still chatting through live — the way
   * back after navigating away or logging back in, since claiming removes a session from
   * `listWaiting`. */
  listMine: () => api.get<LiveInboxEntry[]>("/sale/live-inbox/mine"),
  claim: (sessionId: number) => api.post<LiveInboxEntry>(`/sale/live-inbox/${sessionId}/claim`),
  getMessages: (sessionId: number) => api.get<MessageResponse[]>(`/sale/live-inbox/${sessionId}/messages`),
  reply: (sessionId: number, content: string) =>
    api.post<MessageResponse>(`/sale/live-inbox/${sessionId}/reply`, { content }),
  suggest: (sessionId: number) =>
    api.post<{ draft: string; requires_hitl: boolean }>(`/sale/live-inbox/${sessionId}/suggest`),
  /** Hand the session back to the AI — the customer can go back to chatting with Auremont. */
  end: (sessionId: number) => api.post<MessageResponse>(`/sale/live-inbox/${sessionId}/end`),
};
