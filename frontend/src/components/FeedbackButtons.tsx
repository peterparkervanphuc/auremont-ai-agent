import { useState } from "react";
import { api } from "../api/client";
import { CheckIcon } from "./Icons";

type FeedbackType = "helpful" | "wrong" | "incomplete";

const OPTIONS: { type: FeedbackType; label: string; title: string }[] = [
  { type: "helpful", label: "Hữu ích", title: "Câu trả lời đúng và đủ" },
  { type: "wrong", label: "Sai", title: "Câu trả lời sai" },
  { type: "incomplete", label: "Thiếu", title: "Câu trả lời thiếu thông tin" },
];

// Nút Feedback dưới mỗi câu trả lời — Sale báo cáo sai/thiếu, tạo feedback loop cho Admin.
export function FeedbackButtons({ messageId }: { messageId: number }) {
  const [sent, setSent] = useState<FeedbackType | null>(null);
  const [busy, setBusy] = useState(false);

  const send = async (type: FeedbackType) => {
    if (busy || sent) return;
    setBusy(true);
    try {
      await api.post("/feedback", { message_id: messageId, type });
      setSent(type);
    } catch {
      // Không chặn luồng tư vấn nếu gửi feedback lỗi.
    } finally {
      setBusy(false);
    }
  };

  if (sent) {
    return (
      <div className="feedback-row feedback-row--sent">
        <CheckIcon size={13} />
        Cảm ơn phản hồi của bạn
      </div>
    );
  }

  return (
    <div className="feedback-row">
      <span className="feedback-label">Câu trả lời này thế nào?</span>
      {OPTIONS.map((o) => (
        <button
          key={o.type}
          className="feedback-btn"
          title={o.title}
          disabled={busy}
          onClick={() => send(o.type)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
