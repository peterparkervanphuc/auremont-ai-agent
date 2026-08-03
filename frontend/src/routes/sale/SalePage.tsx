import { useCallback, useEffect, useState } from "react";
import { Route, Routes } from "react-router-dom";
import { api } from "../../api/client";
import type { ChatSessionResponse } from "../../types";
import { ChatWindow } from "./ChatWindow";
import { SessionList } from "./SessionList";
import { SparkleIcon } from "../../components/Icons";
import { useAuth } from "../../hooks/useAuth";

// Shell kiểu ChatGPT: sidebar Session bên trái + khung chat chính.
export function SalePage() {
  const { username } = useAuth();
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

  return (
    <div className="chat-shell">
      <SessionList sessions={sessions} loading={loading} onChange={setSessions} />
      <Routes>
        <Route path="sessions/:sessionId" element={<ChatWindow onSessionsChange={reload} />} />
        <Route
          path="*"
          element={
            <div className="chat-page">
              <div className="chat-messages">
                <div className="chat-messages-inner">
                  <div className="chat-empty">
                    <div className="chat-empty-icon">
                      <SparkleIcon size={26} />
                    </div>
                    <h2 className="chat-empty-title">SalesMate có thể giúp gì?</h2>
                    <p className="chat-empty-text">
                      Chào {username ?? "bạn"}, chọn một phiên tư vấn ở thanh bên hoặc tạo phiên khách hàng mới để bắt
                      đầu.
                    </p>
                  </div>
                </div>
              </div>
            </div>
          }
        />
      </Routes>
    </div>
  );
}
