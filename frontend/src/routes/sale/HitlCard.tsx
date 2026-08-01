import { useState } from "react";
import { api } from "../../api/client";
import type { MessageResponse } from "../../types";

interface HitlCardProps {
  message: MessageResponse;
  onConfirmed: () => void;
}

// CLAUDE.md §6.4.e — "CẢNH BÁO THÔNG TIN CAM KẾT", bắt buộc xác nhận trước khi gửi/copy.
export function HitlCard({ message, onConfirmed }: HitlCardProps) {
  const [confirming, setConfirming] = useState(false);

  const confirm = async () => {
    setConfirming(true);
    try {
      await api.post(`/hitl/${message.id}/confirm`, { confirmed_content: message.content });
      onConfirmed();
    } finally {
      setConfirming(false);
    }
  };

  return (
    <div>
      <strong>CẢNH BÁO THÔNG TIN CAM KẾT</strong>
      <p>{message.content}</p>
      <ul>
        {message.citations?.map((c) => (
          <li key={c.document_id}>{c.title}</li>
        ))}
      </ul>
      <button onClick={confirm} disabled={confirming}>
        XÁC NHẬN &amp; GỬI
      </button>
    </div>
  );
}
