import { useCallback, useEffect, useState } from "react";
import { Route, Routes, useNavigate } from "react-router-dom";
import { api } from "../../api/client";
import type { ChatSessionResponse } from "../../types";
import { ChatWindow } from "./ChatWindow";
import { SessionList } from "./SessionList";
import { ChatContextPanel } from "./ChatContextPanel";
import { ChatSuggestions } from "./ChatSuggestions";
import { AuremontMascot } from "../../components/AuremontMascot";
import { useAuth } from "../../hooks/useAuth";

// Shell kiểu ChatGPT: sidebar Session bên trái + khung chat chính + panel ngữ
// cảnh bên phải.
export function SalePage() {
  const { username } = useAuth();
  const navigate = useNavigate();
  const [sessions, setSessions] = useState<ChatSessionResponse[]>([]);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(() => {
    api
      .get<ChatSessionResponse[]>("/sale/sessions")
      .then(setSessions)
      .catch(() => setSessions([]))
      .finally(() => setLoading(false));
  }, []);

  useEffect(reload, [reload]);

  // Man hinh chua chon phien: tao phien moi ngay khi go/chon goi y, giong trai
  // nghiem "go la bat dau" cua mau thiet ke MOSO.
  const startSession = useCallback(
    async (prefill?: string) => {
      const session = await api.post<ChatSessionResponse>("/sale/sessions", {});
      setSessions((prev) => [session, ...prev]);
      navigate(`/chat/sessions/${session.id}`, prefill ? { state: { prefill } } : undefined);
    },
    [navigate],
  );

  return (
    <div className="chat-shell">
      <SessionList sessions={sessions} loading={loading} onChange={setSessions} />
      <Routes>
        <Route path="sessions/:sessionId" element={<ChatWindow onSessionsChange={reload} />} />
        <Route
          path="*"
          element={
            <>
              <div className="chat-page">
                <div className="chat-messages">
                  <div className="chat-messages-inner">
                    <div className="chat-landing">
                      <AuremontMascot size={64} className="chat-landing-mascot" />
                      <h2 className="chat-empty-title">Hỏi Auremont bằng câu nói của bạn</h2>
                      <p className="chat-empty-text">
                        Chào {username ?? "bạn"}, mô tả điều cần tra cứu — bảng giá, mặt bằng, chính sách bán hàng —
                        Auremont sẽ tự mở phiên khách hàng mới và trả lời kèm trích nguồn.
                      </p>
                      <ChatSuggestions onPick={startSession} />
                    </div>
                  </div>
                </div>
              </div>
              <ChatContextPanel messages={[]} />
            </>
          }
        />
      </Routes>
    </div>
  );
}
