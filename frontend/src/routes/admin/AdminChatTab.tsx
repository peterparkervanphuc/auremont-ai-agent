import { useEffect, useState } from "react";
import { api } from "../../api/client";
import type { ChatSessionResponse, MessageResponse } from "../../types";
import { BotIcon, DocumentIcon, LoaderIcon, PlusIcon, SendIcon, SparkleIcon, UserIcon } from "../../components/Icons";

// Tab Chat cho Admin — tái sử dụng luồng hỏi-đáp giống Sale để test thử AI.
// LƯU Ý: backend hiện chỉ cho phép role SALE gọi /sale/sessions/* — Admin sẽ nhận lỗi 403
// cho tới khi router được cập nhật để chấp nhận cả 2 role (việc này thuộc backend, chưa làm ở đây).
export function AdminChatTab() {
  const [sessions, setSessions] = useState<ChatSessionResponse[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<MessageResponse[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<ChatSessionResponse[]>("/sale/sessions")
      .then(setSessions)
      .catch((err) => setError(err instanceof Error ? err.message : "Không tải được danh sách phiên"));
  }, []);

  useEffect(() => {
    if (activeSessionId === null) return;
    api
      .get<MessageResponse[]>(`/sale/sessions/${activeSessionId}/messages`)
      .then(setMessages)
      .catch((err) => setError(err instanceof Error ? err.message : "Không tải được tin nhắn"));
  }, [activeSessionId]);

  const createSession = async () => {
    setError(null);
    try {
      const session = await api.post<ChatSessionResponse>("/sale/sessions", {});
      setSessions((prev) => [session, ...prev]);
      setActiveSessionId(session.id);
      setMessages([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tạo được phiên mới");
    }
  };

  const sendMessage = async () => {
    if (activeSessionId === null || !input.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const reply = await api.post<MessageResponse>(`/sale/sessions/${activeSessionId}/messages`, { content: input });
      setMessages((prev) => [...prev, reply]);
      setInput("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Gửi câu hỏi thất bại");
    } finally {
      setLoading(false);
    }
  };

  const ready = Boolean(input.trim()) && !loading;

  return (
    <div style={{ display: "flex", height: "100svh" }}>
      <aside className="chat-sidebar" style={{ width: 268, flexShrink: 0 }}>
        <div className="chat-sidebar-head">
          <button onClick={createSession} className="chat-new-btn">
            <PlusIcon size={17} />
            Chat mới
          </button>
        </div>

        <div className="chat-conv-list">
          {sessions.length === 0 ? (
            <p className="chat-conv-empty">Chưa có phiên chat nào.</p>
          ) : (
            sessions.map((s) => (
              <button
                key={s.id}
                onClick={() => setActiveSessionId(s.id)}
                className={`chat-conv-item ${s.id === activeSessionId ? "chat-conv-item--active" : ""}`}
              >
                <span className="chat-conv-title">{s.title ?? `Phiên #${s.id}`}</span>
                <span className="chat-conv-time">{new Date(s.created_at).toLocaleString("vi-VN")}</span>
              </button>
            ))
          )}
        </div>
      </aside>

      <div className="chat-page" style={{ flex: 1 }}>
        <header className="chat-topbar">
          <div className="chat-topbar-info">
            <div className="chat-topbar-icon">
              <BotIcon size={20} />
            </div>
            <div>
              <div className="chat-topbar-name">Thử nghiệm Agent</div>
              <div className="chat-topbar-status">
                <span className="chat-status-dot" />
                Kiểm thử câu trả lời trước khi giao cho Sale
              </div>
            </div>
          </div>
        </header>

        {activeSessionId === null ? (
          <div className="chat-messages">
            <div className="chat-messages-inner">
              <div className="chat-empty">
                <div className="chat-empty-icon">
                  <SparkleIcon size={26} />
                </div>
                <h2 className="chat-empty-title">Chọn một phiên chat</h2>
                <p className="chat-empty-text">Tạo hoặc chọn phiên ở thanh bên để bắt đầu thử AI.</p>
              </div>
              {error && <div className="alert alert-danger">{error}</div>}
            </div>
          </div>
        ) : (
          <>
            <div className="chat-messages">
              <div className="chat-messages-inner">
                {messages.map((m) => {
                  const isUser = m.sender === "sale";
                  return (
                    <div key={m.id} className={`chat-message ${isUser ? "chat-message--user" : "chat-message--bot"}`}>
                      <div className={`chat-avatar ${isUser ? "chat-avatar--user" : "chat-avatar--bot"}`}>
                        {isUser ? <UserIcon size={16} /> : <BotIcon size={18} />}
                      </div>
                      <div className="chat-bubble-wrap">
                        <div className={`chat-bubble ${isUser ? "chat-bubble--user" : "chat-bubble--bot"}`}>
                          <p className="chat-bubble-text">{m.content}</p>
                          {!isUser && m.citations && m.citations.length > 0 && (
                            <div className="chat-citations">
                              <span className="chat-citations-label">Nguồn</span>
                              {m.citations.map((c) => (
                                <span key={`${c.document_id}-${c.page ?? 0}`} className="chat-citation">
                                  <DocumentIcon size={12} />
                                  {c.title}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}

                {loading && (
                  <div className="chat-thinking">
                    <div className="chat-avatar chat-avatar--bot">
                      <BotIcon size={18} />
                    </div>
                    <div className="thinking-bubble">
                      <div className="thinking-dots">
                        <span className="thinking-dot" />
                        <span className="thinking-dot" />
                        <span className="thinking-dot" />
                      </div>
                      <span className="thinking-label">Đang đọc tài liệu bảng giá...</span>
                    </div>
                  </div>
                )}

                {error && <div className="alert alert-danger">{error}</div>}
              </div>
            </div>

            <div className="chat-input-wrapper">
              <div className="chat-input-area">
                <div className={`chat-input-box ${input.trim() ? "chat-input-box--active" : ""}`}>
                  <input
                    className="chat-input"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && sendMessage()}
                    placeholder="Hỏi thử AI về quy định, tồn kho, chính sách..."
                    disabled={loading}
                  />
                  <button
                    onClick={sendMessage}
                    disabled={!ready}
                    className={`chat-send-btn ${ready ? "chat-send-btn--ready" : ""}`}
                    aria-label="Gửi"
                  >
                    {loading ? <LoaderIcon size={18} className="icon-spin" /> : <SendIcon size={18} />}
                  </button>
                </div>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
