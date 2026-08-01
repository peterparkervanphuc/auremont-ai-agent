import { useState } from "react";
import { api } from "../../api/client";
import { useLiveChatSocket } from "../../hooks/useLiveChatSocket";
import type { LiveChatRequestResponse } from "../../types";

// CLAUDE.md §6.3.c — Khách bấm "Liên hệ Sales" -> chờ Sale accept -> real-time chat.
export function LiveChatWidget({ customerId }: { customerId: string }) {
  const [request, setRequest] = useState<LiveChatRequestResponse | null>(null);
  const { messages, isConnected, send } = useLiveChatSocket(request?.session_id ?? null);

  const requestLiveChat = async () => {
    const result = await api.post<LiveChatRequestResponse>("/livechat/request", { customer_id: customerId });
    setRequest(result);
  };

  // TODO: poll or subscribe for request status transitioning WAITING -> ACTIVE (Sale accepted),
  // and handle the "no Sale online" fallback (CLAUDE.md §7: chuyển sang form để lại thông tin).

  if (!request) {
    return <button onClick={requestLiveChat}>Liên hệ Sales</button>;
  }

  return (
    <div>
      <p>Trạng thái: {request.status} {isConnected ? "(đã kết nối)" : "(đang kết nối...)"}</p>
      <ul>
        {messages.map((m, i) => (
          <li key={i}>{JSON.stringify(m)}</li>
        ))}
      </ul>
      <button onClick={() => send({ content: "..." })}>Gửi</button>
    </div>
  );
}
