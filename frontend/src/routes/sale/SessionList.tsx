import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../../api/client";
import type { ChatSessionResponse, ProjectResponse } from "../../types";
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
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [picking, setPicking] = useState(false);

  useEffect(() => {
    api.get<ProjectResponse[]>("/projects").then(setProjects).catch(() => setProjects([]));
  }, []);

  // A session must carry a project_id: without it the agent cannot query real-time
  // inventory. So the "+" button opens the project picker instead of creating a
  // session straight away.
  const createSession = async (projectId: string) => {
    const session = await api.post<ChatSessionResponse>("/sale/sessions", { project_id: projectId });
    setPicking(false);
    onChange([session, ...sessions]);
    navigate(`/chat/sessions/${session.id}`);
  };

  const startNewSession = () => {
    if (projects.length === 1) {
      // Only one project to choose from — skip the picker.
      void createSession(projects[0].id);
      return;
    }
    setPicking(true);
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
        <button
          onClick={startNewSession}
          className="chat-new-btn"
          type="button"
          disabled={projects.length === 0}
          title={projects.length === 0 ? "Chưa có dữ liệu dự án" : undefined}
        >
          <PlusIcon size={17} />
          Phiên khách hàng mới
        </button>
      </div>

      {/* README §5.2a — no project data means Sale cannot consult anything yet. */}
      {projects.length === 0 && !loading && (
        <p className="chat-conv-empty">Chưa có dữ liệu dự án, vui lòng báo Admin cập nhật.</p>
      )}

      {picking && (
        <div className="chat-project-picker">
          <p className="chat-project-picker-label">Chọn dự án tư vấn</p>
          {projects.map((p) => (
            <button
              key={p.id}
              type="button"
              className="chat-project-option"
              onClick={() => void createSession(p.id)}
            >
              {p.name}
            </button>
          ))}
          <button type="button" className="chat-project-cancel" onClick={() => setPicking(false)}>
            Huỷ
          </button>
        </div>
      )}

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
