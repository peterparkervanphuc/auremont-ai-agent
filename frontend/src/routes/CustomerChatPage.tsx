import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useLocation } from "react-router-dom";
import { customerApi } from "../api/customerChat";
import { clearVisitorSession, getVisitorSession, setVisitorSession } from "../hooks/useVisitorToken";
import { useAuth } from "../hooks/useAuth";
import type {
  AnonymousSessionResponse,
  CustomerAskResponse,
  CustomerChatSessionResponse,
  CustomerGate,
  MessageResponse,
  SessionStatus,
} from "../types";
import { RegisterGateModal } from "../components/RegisterGateModal";
import { AnswerImageStrip } from "./sale/AnswerImageStrip";
import { AuremontAvatar } from "../components/AuremontAvatar";
import { MessageContent } from "../components/MessageContent";
import { parseServerDate } from "../utils/datetime";
import {
  ArrowRightIcon,
  ClockIcon,
  LoaderIcon,
  SendIcon,
  TrashIcon,
  UserIcon,
  UsersIcon,
} from "../components/Icons";

function formatTime(iso: string): string {
  const d = parseServerDate(iso);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
}

const SUGGESTIONS = ["Dự án ở vị trí nào?", "Có những tiện ích gì?", "Căn hộ có mấy phòng ngủ?"];

// How often to poll for the Sale's side of a live conversation once a handoff is under way
// (see Context in the plan: polling first, WebSocket push is a documented future upgrade).
const LIVE_POLL_INTERVAL_MS = 4000;

/** Public/customer chat page — reachable with no account. Deliberately not a re-skin of
 * ChatWindow.tsx: it drops HitlCard entirely (the customer IS the one reading the answer
 * directly, so there is no second human to relay it to and confirm), and manages a single
 * continuous session per visitor/account rather than Sale's multi-session sidebar. */
export function CustomerChatPage() {
  const { isAuthenticated, role } = useAuth();
  const isCustomer = isAuthenticated && role === "customer";
  const location = useLocation();

  const [sessionId, setSessionId] = useState<number | null>(null);
  const [sessionStatus, setSessionStatus] = useState<SessionStatus>("bot_handling");
  const [messages, setMessages] = useState<MessageResponse[]>([]);
  // "Đặt lịch xem nhà" (ProjectOverviewPage.tsx) and the "Chat với chuyên viên tư vấn"
  // nav dropdown item (TopNavbar.tsx) both hand off here with a prefilled question via
  // router state — same pattern as ChatWindow.tsx's Sale flow.
  const [input, setInput] = useState(() => (location.state as { prefill?: string } | null)?.prefill ?? "");

  // The useState initializer above only runs on first mount — it misses a prefill that
  // arrives while this page is already open (e.g. clicking "Chat với chuyên viên tư vấn"
  // from the nav while already on /chat: same route, so React Router updates `location`
  // without remounting this component). React Router still assigns a new `location.key`
  // to every navigation, even a same-path one, so keying off that catches this case too.
  useEffect(() => {
    const prefill = (location.state as { prefill?: string } | null)?.prefill;
    if (prefill) setInput(prefill);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.key]);
  const [loading, setLoading] = useState(false);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [gate, setGate] = useState<CustomerGate | null>(null);
  const [requestingHuman, setRequestingHuman] = useState(false);
  const [returningToAi, setReturningToAi] = useState(false);
  const [clearingHistory, setClearingHistory] = useState(false);
  // True right after the customer taps "Quay lại chat với AI" — offers an immediate undo
  // (re-request a Sale) in case that was a misclick, instead of relying on them noticing
  // the header button reappeared. Cleared as soon as they act on it either way.
  const [justReturnedToAi, setJustReturnedToAi] = useState(false);

  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  // Two rapid first sends (or suggestion taps) must share one in-flight create request;
  // otherwise both can observe sessionId=null before React commits the first update.
  const sessionCreationRef = useRef<Promise<number> | null>(null);

  // Resume an existing conversation on load: a logged-in customer's most recent session,
  // or the anonymous session cached in this browser (see useVisitorToken).
  useEffect(() => {
    let cancelled = false;

    async function resume() {
      setHistoryLoading(true);
      try {
        let id: number | null = null;

        if (isCustomer) {
          const sessions = await customerApi.get<CustomerChatSessionResponse[]>("/customer/sessions");
          id = sessions[0]?.id ?? null;
          if (id && !cancelled) setSessionStatus(sessions[0].status);
        } else {
          id = getVisitorSession()?.sessionId ?? null;
          if (id && !cancelled) {
            const detail = await customerApi.get<CustomerChatSessionResponse>(`/customer/sessions/${id}`);
            setSessionStatus(detail.status);
          }
        }

        if (id && !cancelled) {
          setSessionId(id);
          const history = await customerApi.get<MessageResponse[]>(`/customer/sessions/${id}/messages`);
          if (!cancelled) setMessages(history);

          // A resumed ANONYMOUS conversation (not a brand-new one) only ever lives in this
          // browser's localStorage — surface the same register/login prompt normally shown
          // after a few messages (see RegisterGateModal's "turn_limit" copy, which already
          // says exactly this) right away, instead of waiting for the gate to trigger
          // naturally or leaving it to a passive banner the visitor can miss entirely.
          if (!isCustomer && !cancelled && history.length > 0) {
            setGate("turn_limit");
          }
        }
      } catch {
        // No existing session yet, or the cached one no longer resolves — start fresh
        // on the next message rather than blocking the page with an error.
      } finally {
        if (!cancelled) setHistoryLoading(false);
      }
    }

    resume();
    return () => {
      cancelled = true;
    };
  }, [isCustomer]);

  // Once a Sale is involved (or the customer is waiting for one), the AI stops replying
  // synchronously — poll for the status flip and the Sale's messages instead. Stopped as
  // soon as the tab is left, and never started for the common bot-only case.
  useEffect(() => {
    if (!sessionId || sessionStatus === "bot_handling") return;

    const poll = async () => {
      try {
        const [detail, history] = await Promise.all([
          customerApi.get<CustomerChatSessionResponse>(`/customer/sessions/${sessionId}`),
          customerApi.get<MessageResponse[]>(`/customer/sessions/${sessionId}/messages`),
        ]);
        setSessionStatus(detail.status);
        setMessages(history);
      } catch {
        // A transient network hiccup shouldn't stop future polls — just skip this tick.
      }
    };

    const interval = setInterval(poll, LIVE_POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [sessionId, sessionStatus]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [input]);

  const ensureSession = useCallback(async (): Promise<number> => {
    if (sessionId) return sessionId;
    if (sessionCreationRef.current) return sessionCreationRef.current;

    const creation = (async () => {
      if (isCustomer) {
        // Idempotent server-side: this returns the account's one durable session.
        const session = await customerApi.post<CustomerChatSessionResponse>("/customer/sessions", {});
        setSessionId(session.id);
        setSessionStatus(session.status);
        return session.id;
      }

      const anon = await customerApi.post<AnonymousSessionResponse>("/customer/sessions/anonymous");
      setVisitorSession(anon.session_id, anon.visitor_token);
      setSessionId(anon.session_id);
      return anon.session_id;
    })();
    sessionCreationRef.current = creation;
    try {
      return await creation;
    } finally {
      sessionCreationRef.current = null;
    }
  }, [sessionId, isCustomer]);

  const sendMessage = useCallback(
    async (content: string) => {
      const trimmed = content.trim();
      if (!trimmed || loading) return;

      const optimisticUser: MessageResponse = {
        id: -Date.now(),
        session_id: sessionId,
        sender: "customer",
        content: trimmed,
        citations: null,
        images: null,
        verifier_score: null,
        requires_hitl: false,
        hitl_confirmed: false,
        emotion: null,
        quick_replies: null,
      suggested_questions: null,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, optimisticUser]);
      setInput("");
      setLoading(true);
      setError(null);
      setJustReturnedToAi(false);

      try {
        const id = await ensureSession();
        // `null` once a Sale is involved — the AI stays silent, the next poll picks up
        // whatever the Sale sends back (see the polling effect above).
        const reply = await customerApi.post<CustomerAskResponse | null>(`/customer/sessions/${id}/messages`, {
          content: trimmed,
        });
        if (reply) {
          setMessages((prev) => [...prev, reply]);
          setSessionStatus(reply.status);
          if (reply.gate) setGate(reply.gate);
        }
      } catch {
        setError("Tạm thời không gửi được câu hỏi — vui lòng thử lại.");
      } finally {
        setLoading(false);
      }
    },
    [loading, sessionId, ensureSession],
  );

  const requestHuman = useCallback(async () => {
    if (requestingHuman) return;
    setRequestingHuman(true);
    setError(null);
    setJustReturnedToAi(false);
    try {
      const id = await ensureSession();
      const reply = await customerApi.post<CustomerAskResponse>(`/customer/sessions/${id}/request-human`);
      setMessages((prev) => [...prev, reply]);
      setSessionStatus(reply.status);
    } catch {
      setError("Tạm thời không kết nối được chuyên viên — vui lòng thử lại.");
    } finally {
      setRequestingHuman(false);
    }
  }, [requestingHuman, ensureSession]);

  const returnToAi = useCallback(async () => {
    if (!sessionId || returningToAi) return;
    setReturningToAi(true);
    setError(null);
    try {
      const reply = await customerApi.post<CustomerAskResponse>(`/customer/sessions/${sessionId}/return-to-ai`);
      setMessages((prev) => [...prev, reply]);
      setSessionStatus(reply.status);
      // Give an immediate way back in case that click was a mistake — see the banner
      // rendered below, cleared once the customer sends a message or re-requests a Sale.
      setJustReturnedToAi(true);
    } catch {
      setError("Tạm thời không quay lại được — vui lòng thử lại.");
    } finally {
      setReturningToAi(false);
    }
  }, [sessionId, returningToAi]);

  const clearHistory = useCallback(async () => {
    if (!sessionId || clearingHistory || messages.length === 0) return;
    const confirmed = window.confirm(
      "Xóa toàn bộ lịch sử trò chuyện? Thông tin Auremont đã ghi nhớ từ cuộc trò chuyện này cũng sẽ bị xóa. Nếu đang chat với chuyên viên, phiên hỗ trợ trực tiếp sẽ kết thúc.",
    );
    if (!confirmed) return;

    setClearingHistory(true);
    setError(null);
    try {
      await customerApi.delete<void>(`/customer/sessions/${sessionId}/messages`);
      setMessages([]);
      setInput("");
      setGate(null);
      setSessionStatus("bot_handling");
      setJustReturnedToAi(false);
    } catch {
      setError("Tạm thời chưa xóa được lịch sử trò chuyện — vui lòng thử lại.");
    } finally {
      setClearingHistory(false);
    }
  }, [sessionId, clearingHistory, messages.length]);

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    sendMessage(input);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  };

  // Registration claims the anonymous session onto the new account, so the same
  // session_id keeps working — just re-fetch history now that we're authenticated,
  // and drop the anonymous-visitor cache since it no longer applies.
  const handleAuthenticated = useCallback(async (preferredSessionId?: number) => {
    setGate(null);
    clearVisitorSession();
    try {
      let id = preferredSessionId ?? sessionId;
      if (!id) {
        const sessions = await customerApi.get<CustomerChatSessionResponse[]>("/customer/sessions");
        id = sessions[0]?.id ?? null;
      }
      if (!id) return;

      const [detail, history] = await Promise.all([
        customerApi.get<CustomerChatSessionResponse>(`/customer/sessions/${id}`),
        customerApi.get<MessageResponse[]>(`/customer/sessions/${id}/messages`),
      ]);
      setSessionId(id);
      setSessionStatus(detail.status);
      setMessages(history);
    } catch {
      // Non-fatal: the messages already rendered locally stay on screen and the normal
      // authenticated resume effect gets another chance to load the canonical session.
    }
  }, [sessionId]);

  const ready = Boolean(input.trim()) && !loading;
  const visitor = getVisitorSession();
  const isLive = sessionStatus !== "bot_handling";

  return (
    <div className="chat-page chat-page--standalone">
      <header className="chat-topbar">
        <div className="chat-topbar-info">
          <div className="chat-topbar-icon">
            {sessionStatus === "sale_handling" ? (
              <UsersIcon size={20} />
            ) : (
              <AuremontAvatar size={26} emotion={sessionStatus === "waiting_sale" ? "thinking" : "idle"} variant="face" />
            )}
          </div>
          <div>
            <div className="chat-topbar-name">
              {sessionStatus === "sale_handling" ? "Chuyên viên tư vấn" : "Trợ lý tư vấn Auremont"}
            </div>
            <div className="chat-topbar-status">
              <span className="chat-status-dot" />
              {sessionStatus === "waiting_sale"
                ? "Đang kết nối chuyên viên..."
                : sessionStatus === "sale_handling"
                  ? "Đang chat trực tiếp với bạn"
                  : "Sẵn sàng giải đáp thắc mắc về dự án"}
            </div>
          </div>
        </div>

        <div className="chat-topbar-actions">
          {isCustomer && !isLive && (
            <button className="btn btn-outline chat-request-human-btn" type="button" onClick={requestHuman} disabled={requestingHuman}>
              {requestingHuman ? <LoaderIcon size={15} className="icon-spin" /> : <UsersIcon size={15} />}
              Gặp chuyên viên tư vấn
            </button>
          )}
          {sessionId && messages.length > 0 && (
            <button
              className="chat-clear-btn"
              type="button"
              onClick={clearHistory}
              disabled={clearingHistory || loading}
            >
              {clearingHistory ? <LoaderIcon size={15} className="icon-spin" /> : <TrashIcon size={15} />}
              <span>Xóa lịch sử</span>
            </button>
          )}
        </div>
      </header>

      {sessionStatus === "waiting_sale" && (
        <div className="chat-live-banner chat-live-banner--waiting">
          <ClockIcon size={15} />
          <span>Đang kết nối chuyên viên tư vấn, vui lòng chờ trong giây lát...</span>
          <button type="button" className="chat-live-banner-action" onClick={returnToAi} disabled={returningToAi}>
            Quay lại chat với AI
          </button>
        </div>
      )}
      {sessionStatus === "sale_handling" && (
        <div className="chat-live-banner chat-live-banner--live">
          <UsersIcon size={15} />
          <span>Bạn đang chat trực tiếp với chuyên viên tư vấn.</span>
          <button type="button" className="chat-live-banner-action" onClick={returnToAi} disabled={returningToAi}>
            Quay lại chat với AI
          </button>
        </div>
      )}
      {/* Immediate undo right after "Quay lại chat với AI" — in case that was a misclick,
          instead of relying on the customer to notice the header button reappeared. */}
      {justReturnedToAi && sessionStatus === "bot_handling" && (
        <div className="chat-live-banner chat-live-banner--waiting">
          <UsersIcon size={15} />
          <span>Bạn vừa rời khỏi chat trực tiếp.</span>
          <button type="button" className="chat-live-banner-action" onClick={requestHuman} disabled={requestingHuman}>
            Chat lại với chuyên viên
          </button>
        </div>
      )}

      <div className="chat-messages" ref={scrollRef}>
        <div className="chat-messages-inner">
          {messages.length === 0 && !loading && !historyLoading && (
            <div className="chat-landing">
              <AuremontAvatar size={64} emotion="greeting" className="chat-landing-mascot" />
              <h2 className="chat-empty-title">Hỏi Auremont về dự án</h2>
              <p className="chat-empty-text">
                Vị trí, tiện ích, loại căn hộ... hỏi Auremont bất cứ điều gì bạn quan tâm về dự án.
              </p>
              <div className="chat-suggest-card">
                <span className="chat-suggest-label">Thử hỏi</span>
                {SUGGESTIONS.map((s) => (
                  <button key={s} type="button" className="chat-suggest-item" onClick={() => sendMessage(s)}>
                    <span>{s}</span>
                    <ArrowRightIcon size={15} />
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, index) => {
            const isUser = m.sender === "customer";
            const isSaleAgent = m.sender === "sale";
            // Options expire once superseded — only the single most recent AI message can
            // still be answered by tapping instead of typing, and only while the AI (not a
            // Sale) is the one who'd read the reply.
            const showQuickReplies =
              !isUser &&
              !isSaleAgent &&
              index === messages.length - 1 &&
              sessionStatus === "bot_handling" &&
              !!m.quick_replies?.length;
            // Same expiry rule as above, and never shown alongside quick replies: those
            // answer the question the AI just asked, these start a new one, and one row of
            // pills doing both at once is ambiguous.
            const showSuggestedQuestions =
              !isUser &&
              !isSaleAgent &&
              index === messages.length - 1 &&
              sessionStatus === "bot_handling" &&
              !showQuickReplies &&
              !!m.suggested_questions?.length;
            return (
              <div key={m.id} className={`chat-message ${isUser ? "chat-message--user" : "chat-message--bot"}`}>
                <div className={`chat-avatar ${isUser ? "chat-avatar--user" : "chat-avatar--bot"}`}>
                  {isUser ? (
                    <UserIcon size={16} />
                  ) : isSaleAgent ? (
                    <UsersIcon size={16} />
                  ) : (
                    <AuremontAvatar size={22} emotion={m.emotion ?? "idle"} variant="face" />
                  )}
                </div>

                <div className="chat-bubble-wrap">
                  {isSaleAgent && <span className="chat-sale-label">Chuyên viên tư vấn</span>}
                  <div className={`chat-bubble ${isUser ? "chat-bubble--user" : "chat-bubble--bot"}`}>
                    <MessageContent content={m.content} className="chat-bubble-text" />

                    {/* No source citations here, by design — that's a Sale-facing feature
                        (checking which internal doc backs an answer), not something a customer
                        should see or click through to the raw file. */}

                    {!isUser && m.images && m.images.length > 0 && <AnswerImageStrip images={m.images} />}
                  </div>

                  {showQuickReplies && (
                    <div className="chat-quick-replies">
                      {m.quick_replies?.map((option) => (
                        <button
                          key={option}
                          type="button"
                          className="chat-quick-reply"
                          disabled={loading}
                          onClick={() => sendMessage(option)}
                        >
                          {option}
                        </button>
                      ))}
                    </div>
                  )}

                  {showSuggestedQuestions && (
                    <div className="chat-suggested-questions">
                      {m.suggested_questions?.map((question) => (
                        <button
                          key={question}
                          type="button"
                          className="chat-suggested-question"
                          disabled={loading}
                          onClick={() => sendMessage(question)}
                        >
                          {question}
                        </button>
                      ))}
                    </div>
                  )}

                  <span className="chat-timestamp">{formatTime(m.created_at)}</span>
                </div>
              </div>
            );
          })}

          {loading && (
            <div className="chat-thinking">
              <div className="chat-avatar chat-avatar--bot">
                <AuremontAvatar size={22} emotion="thinking" variant="face" />
              </div>
              <div className="thinking-bubble">
                <div className="thinking-dots">
                  <span className="thinking-dot" />
                  <span className="thinking-dot" />
                  <span className="thinking-dot" />
                </div>
                <span className="thinking-label">Auremont đang trả lời...</span>
              </div>
            </div>
          )}

          {error && <div className="alert alert-danger">{error}</div>}
        </div>
      </div>

      <div className="chat-input-wrapper">
        <form className="chat-input-area" onSubmit={handleSubmit}>
          <div className={`chat-input-box ${input.trim() ? "chat-input-box--active" : ""}`}>
            <textarea
              ref={textareaRef}
              className="chat-input"
              placeholder="Nhập câu hỏi của bạn..."
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

      {gate && (
        <RegisterGateModal
          gate={gate}
          sessionId={sessionId}
          visitorToken={visitor?.visitorToken ?? null}
          onClose={() => setGate(null)}
          onAuthenticated={handleAuthenticated}
        />
      )}
    </div>
  );
}
