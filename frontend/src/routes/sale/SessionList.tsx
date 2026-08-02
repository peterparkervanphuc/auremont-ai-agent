import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../../api/client";
import type { ChatSessionResponse } from "../../types";
import { PlusIcon } from "../../components/Icons";

function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleString("vi-VN", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

// sidebar: nút "+" tạo Session mới, danh sách "Session: Khách...".
export function SessionList() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const [sessions, setSessions] = useState<ChatSessionResponse[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
.get<ChatSessionResponse[]>("/sale/sessions")
.then(setSessions)
.catch(() => setSessions([]))
.finally(() => setLoading(false));
  }, []);

  const createSession = async () => {
    const session = await api.post<ChatSessionResponse>("/sale/sessions", {});
    setSessions((prev) => [session,...prev]);
  };

  return (
    <aside className="chat-sidebar">
      <div className="chat-sidebar-head">
        <div className="app-brand" style={{ marginBottom: 14 }}>
          <div className="app-brand-mark">S</div>
          <span className="app-brand-name">SalesMate</span>
        </div>
        <button onClick={createSession} className="chat-new-btn">
          <PlusIcon size={17} />
          Phiên khách hàng mới
        </button>
      </div>

      <div className="chat-conv-list">
        {loading ? (
          <>
            <div className="skeleton chat-conv-skeleton" />
            <div className="skeleton chat-conv-skeleton" />
            <div className="skeleton chat-conv-skeleton" />
          </>
        ) : sessions.length === 0 ? (
          <p className="chat-conv-empty">Chưa có phiên tư vấn nào.
            <br />Bấm "Phiên khách hàng mới" để bắt đầu.</p>
        ) : (
          sessions.map((s) => (
            <Link
              key={s.id}
              to={`/sale/sessions/${s.id}`}
              className={`chat-conv-item ${String(s.id) === sessionId ? "chat-conv-item--active" : ""}`}
            >
              <span className="chat-conv-title">{s.title ?? `Session: Khách #${s.id}`}</span>
              <span className="chat-conv-time">{formatDate(s.created_at)}</span>
            </Link>
          ))
        )}
      </div>
    </aside>
  );
}
