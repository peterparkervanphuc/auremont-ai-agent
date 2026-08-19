import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { saleLiveApi } from "../../api/saleLive";
import type { MessageResponse } from "../../types";
import { AnswerImageStrip } from "./AnswerImageStrip";
import { parseServerDate } from "../../utils/datetime";
import { AuremontAvatar } from "../../components/AuremontAvatar";
import {
  ArrowLeftIcon,
  DocumentIcon,
  LoaderIcon,
  SendIcon,
  SparklesIcon,
  UserIcon,
  UsersIcon,
} from "../../components/Icons";

function formatTime(iso: string): string {
  const d = parseServerDate(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

const POLL_INTERVAL_MS = 4000;

/** A Sale's view of a claimed live-handoff session: the full AI-era + human-era history,
 * a reply box that goes straight to the customer (no AI in between), and a "Gợi ý AI"
 * co-pilot that drafts a suggestion into the box without ever sending it automatically. */
export function LiveChatPage() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const [messages, setMessages] = useState<MessageResponse[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [ending, setEnding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const reload = useCallback(() => {
    if (!sessionId) return;
    saleLiveApi
      .getMessages(Number(sessionId))
      .then(setMessages)
      .catch(() => {});
  }, [sessionId]);

  useEffect(() => {
    reload();
    const interval = setInterval(reload, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [reload]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [input]);

  const sendReply = useCallback(async () => {
    if (!sessionId || !input.trim() || loading) return;
    const content = input.trim();
    setInput("");
    setLoading(true);
    setError(null);
    try {
      const reply = await saleLiveApi.reply(Number(sessionId), content);
      setMessages((prev) => [...prev, reply]);
    } catch {
      setError("Không gửi được tin nhắn — vui lòng thử lại.");
    } finally {
      setLoading(false);
    }
  }, [sessionId, input, loading]);

  const suggest = useCallback(async () => {
    if (!sessionId || suggesting) return;
    setSuggesting(true);
    setError(null);
    try {
      const { draft } = await saleLiveApi.suggest(Number(sessionId));
      if (draft) setInput(draft);
      else setError("AI chưa có đủ ngữ cảnh để gợi ý câu trả lời.");
    } catch {
      setError("Không lấy được gợi ý — vui lòng thử lại.");
    } finally {
      setSuggesting(false);
    }
  }, [sessionId, suggesting]);

  const endChat = useCallback(async () => {
    if (!sessionId || ending) return;
    if (!window.confirm("Kết thúc chat trực tiếp? Khách sẽ quay lại chat với Auremont AI.")) return;
    setEnding(true);
    setError(null);
    try {
      await saleLiveApi.end(Number(sessionId));
      navigate("/live-inbox");
    } catch {
      setError("Không kết thúc được phiên — vui lòng thử lại.");
    } finally {
      setEnding(false);
    }
  }, [sessionId, ending, navigate]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    sendReply();
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendReply();
    }
  };

  const ready = Boolean(input.trim()) && !loading;

  return (
    <div className="chat-page chat-page--standalone">
      <header className="chat-topbar">
        <div className="chat-topbar-info">
          <button className="btn btn-ghost btn-sm" type="button" onClick={() => navigate("/live-inbox")}>
            <ArrowLeftIcon size={14} />
          </button>
          <div className="chat-topbar-icon">
            <UsersIcon size={20} />
          </div>
          <div>
            <div className="chat-topbar-name">Chat trực tiếp với khách</div>
            <div className="chat-topbar-status">
              <span className="chat-status-dot" />
              Bạn đang chat trực tiếp — AI không tự trả lời trong phiên này
            </div>
          </div>
        </div>

        <button className="btn btn-outline" type="button" onClick={endChat} disabled={ending}>
          {ending ? <LoaderIcon size={15} className="icon-spin" /> : null}
          Kết thúc chat
        </button>
      </header>

      <div className="chat-messages" ref={scrollRef}>
        <div className="chat-messages-inner">
          {messages.map((m) => {
            const isCustomer = m.sender === "customer";
            const isSaleMessage = m.sender === "sale";
            return (
              <div key={m.id} className={`chat-message ${isCustomer ? "chat-message--bot" : "chat-message--user"}`}>
                <div className={`chat-avatar ${isCustomer ? "chat-avatar--bot" : "chat-avatar--user"}`}>
                  {isCustomer ? (
                    <UserIcon size={16} />
                  ) : isSaleMessage ? (
                    <UsersIcon size={16} />
                  ) : (
                    <AuremontAvatar size={20} emotion={m.emotion ?? "idle"} variant="face" />
                  )}
                </div>

                <div className="chat-bubble-wrap">
                  {!isCustomer && (
                    <span className="chat-sale-label">{isSaleMessage ? "Bạn" : "Auremont AI (trước khi chuyển giao)"}</span>
                  )}
                  <div className={`chat-bubble ${isCustomer ? "chat-bubble--bot" : "chat-bubble--user"}`}>
                    <p className="chat-bubble-text">{m.content}</p>

                    {isCustomer && m.citations && m.citations.length > 0 && (
                      <div className="chat-citations">
                        <span className="chat-citations-label">Nguồn</span>
                        {[...new Set(m.citations.map((c) => c.title))].map((title) => (
                          <span key={title} className="chat-citation chat-citation--static">
                            <DocumentIcon size={12} />
                            {title}
                          </span>
                        ))}
                      </div>
                    )}

                    {isCustomer && m.images && m.images.length > 0 && <AnswerImageStrip images={m.images} />}
                  </div>
                  <span className="chat-timestamp">{formatTime(m.created_at)}</span>
                </div>
              </div>
            );
          })}

          {error && <div className="alert alert-danger">{error}</div>}
        </div>
      </div>

      <div className="chat-input-wrapper">
        <form className="chat-input-area" onSubmit={handleSubmit}>
          <div className={`chat-input-box ${input.trim() ? "chat-input-box--active" : ""}`}>
            <textarea
              ref={textareaRef}
              className="chat-input"
              placeholder="Nhập tin nhắn gửi khách..."
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
          <div className="chat-input-hint" style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span>Enter để gửi · Shift + Enter để xuống dòng</span>
            <button type="button" className="btn btn-sm btn-outline" onClick={suggest} disabled={suggesting}>
              {suggesting ? <LoaderIcon size={13} className="icon-spin" /> : <SparklesIcon size={13} />}
              Gợi ý AI
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
