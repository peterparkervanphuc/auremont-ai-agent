import { useState } from "react";
import { api } from "../../api/client";
import type { MessageResponse } from "../../types";

interface ChatbotAskResponse {
  answer: MessageResponse;
  suggest_livechat: boolean;
}

// CLAUDE.md §6.3.b — light OTP login gate, then direct bot answers (no HITL card).
export function ChatbotWidget() {
  const [customerId, setCustomerId] = useState<string | null>(localStorage.getItem("customer_id"));
  const [question, setQuestion] = useState("");
  const [answers, setAnswers] = useState<MessageResponse[]>([]);
  const [suggestLiveChat, setSuggestLiveChat] = useState(false);

  // TODO: gate this widget behind the OTP flow (POST /customer/otp/request + /verify) before
  // allowing a question to be asked, and persist the returned customer_id.

  const askQuestion = async () => {
    if (!customerId || !question.trim()) return;
    const result = await api.post<ChatbotAskResponse>("/chatbot/ask", { customer_id: customerId, question });
    setAnswers((prev) => [...prev, result.answer]);
    setSuggestLiveChat(result.suggest_livechat);
    setQuestion("");
  };

  if (!customerId) {
    // TODO: replace this button with the real OTP form (POST /customer/otp/request + /verify);
    // setCustomerId below should be called with the id returned from /customer/otp/verify.
    return (
      <div>
        <p>Bấm "Chat để hỏi thêm" để đăng nhập (SĐT/Email) và mở Chatbot.</p>
        <button
          onClick={() => {
            const id = localStorage.getItem("customer_id");
            if (id) setCustomerId(id);
          }}
        >
          Chat để hỏi thêm
        </button>
      </div>
    );
  }

  return (
    <div>
      <h3>Chat để hỏi thêm</h3>
      <ul>
        {answers.map((a) => (
          <li key={a.id}>{a.content}</li>
        ))}
      </ul>
      {suggestLiveChat && <p>Câu hỏi này cần Sale hỗ trợ trực tiếp — bấm "Liên hệ Sales" bên dưới.</p>}
      <input value={question} onChange={(e) => setQuestion(e.target.value)} placeholder="Nhập câu hỏi..." />
      <button onClick={askQuestion}>Gửi</button>
    </div>
  );
}
