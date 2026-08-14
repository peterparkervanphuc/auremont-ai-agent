import { useState } from "react";
import { api } from "../../api/client";
import type { MessageResponse } from "../../types";
import { AlertIcon, CheckIcon, CopyIcon, DocumentIcon, LoaderIcon } from "../../components/Icons";

interface HitlCardProps {
  message: MessageResponse;
  onConfirmed: () => void;
}

// Commitment-risk warning card — confirmation is mandatory before send/copy.
export function HitlCard({ message, onConfirmed }: HitlCardProps) {
  const [confirming, setConfirming] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [copied, setCopied] = useState(false);

  const confirm = async () => {
    setConfirming(true);
    try {
      await api.post(`/hitl/${message.id}/confirm`, { confirmed_content: message.content });
      // Only allow copying the content to send to the customer after the Sale
      // has read and confirmed it.
      try {
        await navigator.clipboard.writeText(message.content);
        setCopied(true);
      } catch {
        // Clipboard access blocked (non-HTTPS context / permission not granted) —
        // still treat the confirmation as successful.
      }
      setConfirmed(true);
      onConfirmed();
    } finally {
      setConfirming(false);
    }
  };

  return (
    <div className="hitl-card">
      <div className="hitl-head">
        <AlertIcon size={16} />
        <span className="hitl-title">Cảnh báo thông tin cam kết</span>
      </div>

      <div className="hitl-body">{message.content}</div>

      {message.citations && message.citations.length > 0 && (
        <div className="hitl-sources">
          <span className="chat-citations-label">Tài liệu</span>
          {message.citations.map((c) => (
            <span key={`${c.document_id}-${c.page ?? 0}`} className="chat-citation">
              <DocumentIcon size={12} />
              {c.title}
              {c.page != null && ` · tr.${c.page}`}
            </span>
          ))}
        </div>
      )}

      <div className="hitl-actions">
        {confirmed ? (
          <span className="hitl-confirmed">
            <CheckIcon size={16} />
            {copied ? "Đã xác nhận & copy vào clipboard" : "Đã xác nhận"}
          </span>
        ) : (
          <button onClick={confirm} disabled={confirming} className="btn btn-primary" type="button">
            {confirming ? <LoaderIcon size={16} className="icon-spin" /> : <CopyIcon size={16} />}
            XÁC NHẬN &amp; COPY GỬI KHÁCH
          </button>
        )}
      </div>
    </div>
  );
}
