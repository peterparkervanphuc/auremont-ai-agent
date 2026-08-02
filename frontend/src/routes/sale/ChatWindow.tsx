import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useParams } from "react-router-dom";
import { api } from "../../api/client";
import type { MessageResponse } from "../../types";
import { HitlCard } from "./HitlCard";
import { BotIcon, DocumentIcon, LoaderIcon, SendIcon, SparkleIcon, UserIcon } from "../../components/Icons";
import { FeedbackButtons } from "../../components/FeedbackButtons";

function formatTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

// Agent Pipeline: text input -> câu trả lời + trích nguồn, hoặc Thẻ HITL.
export function ChatWindow() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const [messages, setMessages] = useState<MessageResponse[]>([]);
  const [input, setInput] = useState("");
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
    setLoading(true);
    setError(null);
    try {
      const reply = await api.post<MessageResponse>(`/sale/sessions/${sessionId}/messages`, { content: input });
      setMessages((prev) => [...prev, reply]);
      setInput("");
    } catch {
      setError("Tạm thời không tra được tồn kho — vui lòng thử lại.");
    } finally {
      setLoading(false);
    }
  }, [sessionId, input, loading]);

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

  const ready = Boolean(input.trim()) && !loading;

  return (
    <div className="chat-page">
      <header className="chat-topbar">
        <div className="chat-topbar-info">
          <div className="chat-topbar-icon">
            <BotIcon size={20} />
          </div>
          <div>
            <div className="chat-topbar-name">Trợ lý tư vấn SalesMate</div>
            <div className="chat-topbar-status">
              <span className="chat-status-dot" />
              Sẵn sàng tra cứu tài liệu &amp; tồn kho
            </div>
          </div>
        </div>
      </header>

      <div className="chat-messages" ref={scrollRef}>
        <div className="chat-messages-inner">
          {messages.length === 0 && !loading && (
            <div className="chat-empty">
              <div className="chat-empty-icon">
                <SparkleIcon size={26} />
              </div>
              <h2 className="chat-empty-title">Bắt đầu phiên tư vấn</h2>
              <p className="chat-empty-text">
                Hỏi về bảng giá, mặt bằng, chính sách bán hàng hoặc tồn kho căn.
                <br />
                Mọi câu trả lời đều kèm trích nguồn tài liệu.
              </p>
            </div>
          )}

          {messages.map((m) => {
            if (m.requires_hitl) {
              return <HitlCard key={m.id} message={m} onConfirmed={() => {}} />;
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
