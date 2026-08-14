import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { Link, useLocation } from "react-router-dom";
import { api } from "../api/client";
import type { ChatSessionResponse, MessageResponse } from "../types";
import { ArrowRightIcon, LoaderIcon, SendIcon, XIcon } from "./Icons";
import { AuremontMascot } from "./AuremontMascot";

const SUGGESTIONS = ["Còn căn 2PN dưới 3 tỷ không?", "Biệt thự song lập giá bao nhiêu?"];

export function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [sessionId, setSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<MessageResponse[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  // Ask for the customer's name at the moment they send their first message (not
  // right when the panel opens), so the Sale-side session list shows the customer's
  // name instead of defaulting to the first question's text as the title.
  // pendingMessage holds the in-flight question and is actually sent once this
  // step is resolved (name entered or skipped).
  const [pendingMessage, setPendingMessage] = useState<string | null>(null);
  const [askedName, setAskedName] = useState(false);
  const [customerName, setCustomerName] = useState("");
  const location = useLocation();
  const rootRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // The widget never unmounts on page change (App.tsx only toggles it via
  // showChatWidget), so a panel left open on one page would stay open when
  // navigating to another unless closed explicitly. Closing the panel is fine,
  // but the session state (sessionId/messages) is preserved so reopening the
  // widget doesn't lose an in-progress conversation.
  useEffect(() => {
    setOpen(false);
  }, [location.pathname]);

  // Clicking outside the panel closes it, matching every other popover/dropdown in the app.
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
    const session = await api.post<ChatSessionResponse>("/sale/sessions", {
      customer_name: customerName.trim() || undefined,
    });
    setSessionId(session.id);
    return session.id;
  };

  const sendMessage = async (content: string, skipNameGate = false) => {
    const trimmed = content.trim();
    if (!trimmed || loading) return;

    // First send (no session yet, name gate not passed): hold the question and
    // show the name form instead of sending immediately. skipNameGate=true when
    // called back from confirmName (the name step was just completed within the
    // same click, and the askedName state hasn't updated in this closure yet).
    if (!sessionId && !askedName && !skipNameGate) {
      setPendingMessage(trimmed);
      setInput("");
      return;
    }

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

  const confirmName = (e?: FormEvent) => {
    e?.preventDefault();
    setAskedName(true);
    const msg = pendingMessage;
    setPendingMessage(null);
    if (msg) sendMessage(msg, true);
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
            <AuremontMascot size={34} />
            <div>
              <p className="chat-widget-title">Trợ lý AI</p>
              <p className="chat-widget-sub">Hỏi nhanh về giá, pháp lý hoặc tồn kho</p>
            </div>
            <button className="chat-widget-close" type="button" onClick={() => setOpen(false)} aria-label="Đóng">
              <XIcon size={16} />
            </button>
          </div>

          {pendingMessage !== null ? (
            <form className="chat-widget-name-form" onSubmit={confirmName}>
              <p className="chat-widget-name-hint">Cho Auremont biết tên bạn để lưu lại cuộc trò chuyện này nhé.</p>
              <input
                autoFocus
                type="text"
                placeholder="Tên của bạn (có thể bỏ trống)"
                value={customerName}
                onChange={(e) => setCustomerName(e.target.value)}
              />
              <div className="chat-widget-name-actions">
                <button type="submit" className="btn btn-primary chat-widget-name-submit">
                  Gửi câu hỏi
                </button>
                <button type="button" className="chat-widget-name-skip" onClick={() => confirmName()}>
                  Bỏ qua
                </button>
              </div>
            </form>
          ) : (
            <>
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
            </>
          )}
        </div>
      )}

      <button
        className={`chat-widget-fab ${open ? "chat-widget-fab--open" : ""}`}
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label={open ? "Đóng trợ lý AI" : "Mở trợ lý AI"}
      >
        {open ? <XIcon size={22} /> : <AuremontMascot size={68} />}
      </button>
    </div>
  );
}
