import { useEffect, useMemo, useState, type FormEvent, type KeyboardEvent } from "react";
import { Link, useMatch, useNavigate } from "react-router-dom";
import { api } from "../../api/client";
import type { ChatSessionResponse, ProjectResponse } from "../../types";
import { ArrowLeftIcon, ChatIcon, PlusIcon, SearchIcon, TrashIcon } from "../../components/Icons";

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
  // Nằm ngoài <Route path="sessions/:sessionId">, nên useParams() sẽ luôn undefined —
  // dùng useMatch để đọc sessionId trực tiếp từ URL hiện tại.
  const match = useMatch("/chat/sessions/:sessionId");
  const sessionId = match?.params.sessionId;
  const navigate = useNavigate();
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  const [picking, setPicking] = useState(false);

  const [naming, setNaming] = useState(false);
  const [customerName, setCustomerName] = useState("");
  const [historyQuery, setHistoryQuery] = useState("");

  useEffect(() => {
    api.get<ProjectResponse[]>("/projects").then(setProjects).catch(() => setProjects([]));
  }, []);

  const filteredSessions = useMemo(() => {
    const q = historyQuery.trim().toLowerCase();
    if (!q) return sessions;
    return sessions.filter((s) => (s.customer_name ?? s.title ?? `Session: Khách #${s.id}`).toLowerCase().includes(q));
  }, [sessions, historyQuery]);

  const closeNaming = () => {
    setNaming(false);
    setCustomerName("");
  };

  // A session must carry a project_id: without it the agent cannot query real-time
  // inventory. The customer name is asked for first, then the project — so a new
  // session is only created once both are known.
  const createSession = async (projectId: string) => {
    const name = customerName.trim();
    const session = await api.post<ChatSessionResponse>("/sale/sessions", {
      project_id: projectId,
      customer_name: name || undefined,
    });
    setPicking(false);
    onChange([session, ...sessions]);
    closeNaming();
    navigate(`/chat/sessions/${session.id}`);
  };

  const submitNewSession = (e: FormEvent) => {
    e.preventDefault();
    setNaming(false);
    if (projects.length === 1) {
      // Only one project to choose from — skip the picker.
      void createSession(projects[0].id);
      return;
    }
    setPicking(true);
  };

  const handleNameKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Escape") closeNaming();
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
        <Link to="/" className="chat-sidebar-home-link">
          <ArrowLeftIcon size={14} />
          Về trang chủ
        </Link>

        <div className="chat-sidebar-brand">
          <ChatIcon size={18} />
          Đoạn chat
        </div>

        {naming ? (
          <form className="chat-new-form" onSubmit={submitNewSession}>
            <input
              autoFocus
              className="chat-new-form-input"
              placeholder="Tên khách hàng (có thể bỏ trống)"
              value={customerName}
              onChange={(e) => setCustomerName(e.target.value)}
              onKeyDown={handleNameKeyDown}
            />
            <div className="chat-new-form-actions">
              <button type="submit" className="btn btn-primary chat-new-form-submit">
                Tạo phiên
              </button>
              <button type="button" className="chat-new-form-cancel" onClick={closeNaming}>
                Huỷ
              </button>
            </div>
          </form>
        ) : (
          <button
            onClick={() => setNaming(true)}
            className="chat-new-btn"
            type="button"
            disabled={projects.length === 0}
            title={projects.length === 0 ? "Chưa có dữ liệu dự án" : undefined}
          >
            <PlusIcon size={17} />
            Phiên khách hàng mới
          </button>
        )}

        <div className="chat-sidebar-search">
          <SearchIcon size={15} />
          <input
            value={historyQuery}
            onChange={(e) => setHistoryQuery(e.target.value)}
            placeholder="Tìm trong lịch sử"
          />
        </div>
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
        ) : filteredSessions.length === 0 ? (
          <p className="chat-conv-empty">Không tìm thấy phiên nào khớp &ldquo;{historyQuery}&rdquo;.</p>
        ) : (
          filteredSessions.map((s) => (
            <Link
              key={s.id}
              to={`/chat/sessions/${s.id}`}
              className={`chat-conv-item ${String(s.id) === sessionId ? "chat-conv-item--active" : ""}`}
            >
              <span className="chat-conv-title">
                {s.customer_name ?? s.title ?? `Session: Khách #${s.id}`}
              </span>
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
