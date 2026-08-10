import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Link, useLocation } from "react-router-dom";
import { api } from "../api/client";
import type { ChatSessionResponse, MessageResponse } from "../types";
import { ArrowRightIcon, ChatIcon, LoaderIcon, SendIcon, SparkleIcon, XIcon } from "./Icons";

const SUGGESTIONS = ["Còn căn 2PN dưới 3 tỷ không?", "Biệt thự song lập giá bao nhiêu?"];

export function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<MessageResponse[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const location = useLocation();
  const rootRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Widget không unmount khi đổi trang (chỉ ẩn/hiện qua showChatWidget ở App.tsx),
  // nên panel mở ở trang này sẽ dính nguyên sang trang khác nếu không tự đóng.
  // Đóng panel thì hợp lý, nhưng phiên chat vẫn giữ nguyên (sessionId/messages)
  // để quay lại widget không mất hội thoại đang hỏi dở.
  useEffect(() => {
    setOpen(false);
  }, [location.pathname]);

  // Bấm ra ngoài panel thì đóng lại, giống mọi popover/dropdown khác trong app.
  useEffect(() => {
    if (!open) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  const ensureSession = async (): Promise<number> => {
    if (sessionId) return sessionId;
    const session = await api.post<ChatSessionResponse>("/sale/sessions", {});
    setSessionId(session.id);
    return session.id;
  };

  const sendMessage = async (content: string) => {
    const trimmed = content.trim();
    if (!trimmed || loading) return;

    setInput("");
    setLoading(true);

    const optimisticUser: MessageResponse = {
      id: -Date.now(),
      session_id: sessionId,
      sender: "sale",
      content: trimmed,
      citations: null,
      verifier_score: null,
      requires_hitl: false,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimisticUser]);

    try {
      const id = await ensureSession();
      const reply = await api.post<MessageResponse>(`/sale/sessions/${id}/messages`, { content: trimmed });
      setMessages((prev) => [...prev, reply]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: -Date.now() - 1,
          session_id: sessionId,
          sender: "agent",
          content: "Tạm thời không tra được tồn kho — vui lòng thử lại.",
          citations: null,
          verifier_score: null,
          requires_hitl: false,
          created_at: new Date().toISOString(),
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    sendMessage(input);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      sendMessage(input);
    }
  };

  const fullChatHref = sessionId ? `/chat/sessions/${sessionId}` : "/chat";

  return (
    <div className="chat-widget" ref={rootRef}>
      {open && (
        <div className="chat-widget-panel">
          <div className="chat-widget-head">
            <div className="chat-widget-icon">
              <SparkleIcon size={16} />
            </div>
            <div>
              <p className="chat-widget-title">Trợ lý AI</p>
              <p className="chat-widget-sub">Hỏi nhanh về giá, pháp lý hoặc tồn kho</p>
            </div>
            <button className="chat-widget-close" type="button" onClick={() => setOpen(false)} aria-label="Đóng">
              <XIcon size={16} />
            </button>
          </div>

          {messages.length === 0 ? (
            <div className="chat-widget-suggestions">
              {SUGGESTIONS.map((s) => (
                <button key={s} type="button" className="chat-widget-suggestion" onClick={() => sendMessage(s)}>
                  &ldquo;{s}&rdquo;
                </button>
              ))}
            </div>
          ) : (
            <div className="chat-widget-messages" ref={scrollRef}>
              {messages.map((m) => (
                <div key={m.id} className={`chat-widget-msg ${m.sender === "sale" ? "chat-widget-msg--user" : ""}`}>
                  {m.content}
                </div>
              ))}
              {loading && (
                <div className="chat-widget-msg">
                  <LoaderIcon size={14} className="icon-spin" />
                </div>
              )}
            </div>
          )}

          <form className="chat-widget-input" onSubmit={handleSubmit}>
            <input
              type="text"
              placeholder="Đặt câu hỏi cho Auremont AI..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
            />
            <button type="submit" disabled={!input.trim() || loading} aria-label="Gửi">
              <SendIcon size={15} />
            </button>
          </form>

          <Link to={fullChatHref} className="chat-widget-fulllink">
            Mở trợ lý đầy đủ
            <ArrowRightIcon size={13} />
          </Link>
        </div>
      )}

      <button
        className="chat-widget-fab"
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={open ? "Đóng trợ lý AI" : "Mở trợ lý AI"}
      >
        {open ? <XIcon size={22} /> : <ChatIcon size={22} />}
      </button>
    </div>
  );
}
