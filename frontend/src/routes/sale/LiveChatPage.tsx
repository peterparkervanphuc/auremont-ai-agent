import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { saleLiveApi } from "../../api/saleLive";
import type { LeadDetail, MessageResponse } from "../../types";
import { AnswerImageStrip } from "./AnswerImageStrip";
import { LeadContextCard } from "./LeadContextCard";
import { LeadInsightPanel } from "./LeadInsightPanel";
import { PropertyListingCarousel } from "../PropertyListingCarousel";
import { parseServerDate } from "../../utils/datetime";
import { AuremontAvatar } from "../../components/AuremontAvatar";
import { MessageContent } from "../../components/MessageContent";
import { CitationList } from "../../components/CitationList";
import {
  AlertTriangleIcon,
  ArrowLeftIcon,
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
  const [lead, setLead] = useState<LeadDetail | null>(null);
  const [leadLoading, setLeadLoading] = useState(true);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [suggesting, setSuggesting] = useState(false);
  const [ending, setEnding] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Holds an AI draft that tripped the price/commitment detector and has not been
  // acknowledged yet. Replies here reach the customer directly, with none of the HITL card
  // the AI-consult flow puts in the way, so an AI-authored commitment gets the same
  // read-it-first obligation before it can be sent.
  const [unacknowledgedDraft, setUnacknowledgedDraft] = useState<string | null>(null);

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

  // Re-fetched whenever the message count changes rather than on its own timer: a lead is
  // only ever re-scored after a customer message (see backend/routers/customer_chat.py), so
  // tying this to `messages.length` keeps the panel in sync exactly when it can change and
  // skips a poll on every tick where nothing new was said.
  useEffect(() => {
    if (!sessionId) return;
    setLeadLoading(true);
    saleLiveApi
      .getLead(Number(sessionId))
      .then(setLead)
      .catch(() => setLead(null))
      .finally(() => setLeadLoading(false));
  }, [sessionId, messages.length]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [input]);

  // Still the untouched risky draft: the acknowledgement banner shows and sending is
  // blocked until the Sale either confirms it or edits it into their own words.
  const awaitingAck = unacknowledgedDraft !== null && input.trim() === unacknowledgedDraft;

  const sendReply = useCallback(async () => {
    if (!sessionId || !input.trim() || loading || awaitingAck) return;
    const content = input.trim();
    setInput("");
    setLoading(true);
    setError(null);
    try {
      const reply = await saleLiveApi.reply(Number(sessionId), content);
      setMessages((prev) => [...prev, reply]);
      setUnacknowledgedDraft(null);
    } catch {
      setError("Không gửi được tin nhắn — vui lòng thử lại.");
    } finally {
      setLoading(false);
    }
  }, [sessionId, input, loading, awaitingAck]);

  const suggest = useCallback(async () => {
    if (!sessionId || suggesting) return;
    setSuggesting(true);
    setError(null);
    try {
      const { draft, requires_hitl } = await saleLiveApi.suggest(Number(sessionId));
      if (draft) {
        setInput(draft);
        setUnacknowledgedDraft(requires_hitl ? draft : null);
      } else setError("AI chưa có đủ ngữ cảnh để gợi ý câu trả lời.");
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

  const ready = Boolean(input.trim()) && !loading && !awaitingAck;

  // Previously hardcoded to "Chat trực tiếp với khách" — the lead lookup already carries
  // the customer's real name (or their label as a fallback), so the topbar can finally show
  // WHO the Sale is talking to instead of nothing at all.
  const topbarName = lead?.customer_name ?? lead?.customer_label ?? "Chat trực tiếp với khách";

  return (
    <div className="live-chat-layout">
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
            <div className="chat-topbar-name">{topbarName}</div>
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
          <LeadContextCard lead={lead} />
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
                    <MessageContent content={m.content} className="chat-bubble-text" />

                    {!isCustomer && m.citations && m.citations.length > 0 && (
                      <CitationList citations={m.citations} className="chat-citations" label="Nguồn" />
                    )}

                    {!isCustomer && m.images && m.images.length > 0 && <AnswerImageStrip images={m.images} />}

                    {!isCustomer && m.listings && m.listings.length > 0 && (
                      <PropertyListingCarousel listings={m.listings} />
                    )}
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
        {awaitingAck && (
          <div className="live-hitl-ack">
            <AlertTriangleIcon size={16} />
            <p>
              Gợi ý này có thông tin giá/cam kết và sẽ gửi thẳng cho khách. Hãy đọc kỹ trước khi gửi.
            </p>
            <button type="button" className="btn btn-sm btn-primary" onClick={() => setUnacknowledgedDraft(null)}>
              Tôi đã đọc, cho phép gửi
            </button>
          </div>
        )}
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

      <LeadInsightPanel lead={lead} loading={leadLoading} />
    </div>
  );
}
