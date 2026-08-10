import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useLocation, useParams } from "react-router-dom";
import { api } from "../../api/client";
import type { MessageResponse } from "../../types";
import { HitlCard } from "./HitlCard";
import { BotIcon, DocumentIcon, LoaderIcon, SendIcon, SparkleIcon, TrashIcon, UserIcon } from "../../components/Icons";
import { FeedbackButtons } from "../../components/FeedbackButtons";

function formatTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

interface Props {
  /** Gọi lại khi danh sách phiên có thể đã đổi (ví dụ sau khi xoá lịch sử). */
  onSessionsChange?: () => void;
}

// Agent Pipeline: text input -> câu trả lời + trích nguồn, hoặc Thẻ HITL.
export function ChatWindow({ onSessionsChange }: Props = {}) {
  const { sessionId } = useParams<{ sessionId: string }>();
  const location = useLocation();
  const [messages, setMessages] = useState<MessageResponse[]>([]);
  const [input, setInput] = useState(() => (location.state as { prefill?: string } | null)?.prefill ?? "");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!sessionId) return;
    setError(null);
    api
.get<MessageResponse[]>(`/sale/sessions/${sessionId}/messages`)
.then(setMessages)
.catch(() => setError("Không tải được lịch sử phiên tư vấn."));
  }, [sessionId]);

  // Luôn cuộn xuống tin nhắn mới nhất.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  // Textarea tự giãn theo nội dung, tối đa 160px.
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [input]);

  // TODO: add voice input (STT provider TBD —).

  const sendMessage = useCallback(async () => {
    if (!sessionId || !input.trim() || loading) return;
    const content = input.trim();
    // Tin đầu tiên trong phiên -> backend tự đặt tên session từ nội dung này,
    // báo cho SalePage load lại sidebar để tên mới hiện ra ngay.
    const isFirstMessage = messages.length === 0;

    // Optimistic UI: server chỉ trả về câu trả lời của agent (response_model=MessageResponse,
    // không phải list), nên tin của Sale phải tự thêm ngay — không thì user gõ xong sẽ không
    // thấy gì cho tới khi AI trả lời xong, giống như tin nhắn "biến mất".
    const optimisticUser: MessageResponse = {
      id: -Date.now(),
      session_id: Number(sessionId) || null,
      sender: "sale",
      content,
      citations: null,
      verifier_score: null,
      requires_hitl: false,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimisticUser]);
    setInput("");
    setLoading(true);
    setError(null);
    try {
      const reply = await api.post<MessageResponse>(`/sale/sessions/${sessionId}/messages`, { content });
      setMessages((prev) => [...prev, reply]);
      if (isFirstMessage) onSessionsChange?.();
    } catch {
      setError("Tạm thời không tra được tồn kho — vui lòng thử lại.");
    } finally {
      setLoading(false);
    }
  }, [sessionId, input, loading, messages.length, onSessionsChange]);

  // HitlCard tự giữ state "đã xác nhận" cục bộ, nhưng nếu danh sách messages
  // re-render lại (đổi phiên rồi quay lại, v.v.) mà requires_hitl vẫn true trong
  // state cha, thẻ HITL sẽ hiện lại nút xác nhận dù đã confirm rồi.
  const handleHitlConfirmed = useCallback((messageId: number) => {
    setMessages((prev) => prev.map((m) => (m.id === messageId ? { ...m, requires_hitl: false } : m)));
  }, []);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    sendMessage();
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const clearChat = async () => {
    if (!sessionId) return;
    await api.delete(`/sale/sessions/${sessionId}/messages`).catch(() => {});
    setMessages([]);
    onSessionsChange?.();
  };

  const ready = Boolean(input.trim()) && !loading;

  return (
    <div className="chat-page">
      <header className="chat-topbar">
        <div className="chat-topbar-info">
          <div className="chat-topbar-icon">
            <BotIcon size={20} />
          </div>
          <div>
            <div className="chat-topbar-name">Trợ lý tư vấn Auremont</div>
            <div className="chat-topbar-status">
              <span className="chat-status-dot" />
              Sẵn sàng tra cứu tài liệu &amp; tồn kho
            </div>
          </div>
        </div>

        <button className="chat-clear-btn" onClick={clearChat} type="button">
          <TrashIcon size={15} />
          Xóa chat
        </button>
      </header>

      <div className="chat-messages" ref={scrollRef}>
        <div className="chat-messages-inner">
          {messages.length === 0 && !loading && (
            <div className="chat-empty">
              <div className="chat-empty-icon">
                <SparkleIcon size={26} />
              </div>
              <h2 className="chat-empty-title">Auremont có thể giúp gì?</h2>
              <p className="chat-empty-text">
                Hỏi về bảng giá, mặt bằng, chính sách bán hàng hoặc tồn kho căn.
                <br />
                Mọi câu trả lời đều kèm trích nguồn tài liệu.
              </p>
            </div>
          )}

          {messages.map((m) => {
            if (m.requires_hitl) {
              // Câu trả lời rủi ro vẫn nằm trong feedback loop như mọi câu khác.
              return (
                <div key={m.id} className="chat-hitl-row">
                  <HitlCard message={m} onConfirmed={() => handleHitlConfirmed(m.id)} />
                  <div className="chat-hitl-meta">
                    <span className="chat-timestamp">{formatTime(m.created_at)}</span>
                    <FeedbackButtons messageId={m.id} />
                  </div>
                </div>
              );
            }

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
                            {c.page != null && ` · tr.${c.page}`}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <span className="chat-timestamp">{formatTime(m.created_at)}</span>
                  {!isUser && <FeedbackButtons messageId={m.id} />}
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
        <form className="chat-input-area" onSubmit={handleSubmit}>
          <div className={`chat-input-box ${input.trim()? "chat-input-box--active" : ""}`}>
            <textarea
              ref={textareaRef}
              className="chat-input"
              placeholder="Nhập câu hỏi tư vấn..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
              rows={1}
            />
            <button type="submit" className={`chat-send-btn ${ready ? "chat-send-btn--ready" : ""}`} disabled={!ready} aria-label="Gửi">
              {loading ? <LoaderIcon size={18} className="icon-spin" /> : <SendIcon size={18} />}
            </button>
          </div>
          <p className="chat-input-hint">Enter để gửi · Shift + Enter để xuống dòng</p>
        </form>
      </div>
    </div>
  );
}
