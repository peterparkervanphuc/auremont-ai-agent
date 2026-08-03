import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../../api/client";
import type { ChatSessionResponse } from "../../types";
import { ChatIcon, PlusIcon, TrashIcon } from "../../components/Icons";

function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? ""
    : d.toLocaleString("vi-VN", { hour: "2-digit", minute: "2-digit", day: "2-digit", month: "short" });
}

interface Props {
  sessions: ChatSessionResponse[];
  loading: boolean;
  onChange: (next: ChatSessionResponse[]) => void;
}

// Sidebar: nút tạo Session mới + danh sách "Session: Khách...".
export function SessionList({ sessions, loading, onChange }: Props) {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();

  const createSession = async () => {
    const session = await api.post<ChatSessionResponse>("/sale/sessions", {});
    onChange([session, ...sessions]);
    navigate(`/chat/sessions/${session.id}`);
  };

  const removeSession = async (e: React.MouseEvent, id: number) => {
    e.preventDefault();
    e.stopPropagation();
    await api.delete(`/sale/sessions/${id}`).catch(() => {});
    onChange(sessions.filter((s) => s.id !== id));
    if (String(id) === sessionId) navigate("/chat");
  };

  return (
    <aside className="chat-sidebar">
      <div className="chat-sidebar-head">
        <div className="chat-sidebar-brand">
          <ChatIcon size={18} />
          Đoạn chat
        </div>
        <button onClick={createSession} className="chat-new-btn" type="button">
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
          <p className="chat-conv-empty">
            Chưa có phiên tư vấn nào.
            <br />
            Bấm &ldquo;Phiên khách hàng mới&rdquo; để bắt đầu.
          </p>
        ) : (
          sessions.map((s) => (
            <Link
              key={s.id}
              to={`/chat/sessions/${s.id}`}
              className={`chat-conv-item ${String(s.id) === sessionId ? "chat-conv-item--active" : ""}`}
            >
              <span className="chat-conv-title">{s.title ?? `Session: Khách #${s.id}`}</span>
              <span className="chat-conv-time">{formatDate(s.created_at)}</span>
              <button
                className="chat-conv-delete"
                onClick={(e) => removeSession(e, s.id)}
                aria-label="Xoá phiên"
                type="button"
              >
                <TrashIcon size={14} />
              </button>
            </Link>
          ))
        )}
      </div>
    </aside>
  );
}
