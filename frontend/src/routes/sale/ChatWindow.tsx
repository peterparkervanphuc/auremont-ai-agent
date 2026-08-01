import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../../api/client";
import type { MessageResponse } from "../../types";
import { HitlCard } from "./HitlCard";

// CLAUDE.md §6.4.d — Agent Pipeline: text/voice input -> câu trả lời + trích nguồn, hoặc Thẻ HITL.
export function ChatWindow() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const [messages, setMessages] = useState<MessageResponse[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!sessionId) return;
    api.get<MessageResponse[]>(`/sale/sessions/${sessionId}/messages`).then(setMessages);
  }, [sessionId]);

  // TODO: add voice input (STT provider TBD — CLAUDE.md §12.4).

  const sendMessage = async () => {
    if (!sessionId || !input.trim()) return;
    setLoading(true);
    try {
      const reply = await api.post<MessageResponse>(`/sale/sessions/${sessionId}/messages`, { content: input });
      setMessages((prev) => [...prev, reply]);
      setInput("");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <ul>
        {messages.map((m) =>
          m.requires_hitl ? (
            <HitlCard key={m.id} message={m} onConfirmed={() => {}} />
          ) : (
            <li key={m.id}>
              <strong>{m.sender}:</strong> {m.content}
            </li>
          ),
        )}
      </ul>
      {loading && <p>Đang đọc tài liệu bảng giá...</p>}
      <input value={input} onChange={(e) => setInput(e.target.value)} placeholder="Nhập câu hỏi..." />
      <button onClick={sendMessage} disabled={loading}>
        Gửi
      </button>
    </div>
  );
}
