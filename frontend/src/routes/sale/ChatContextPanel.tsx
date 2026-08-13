import type { MessageResponse } from "../../types";
import { DocumentIcon, SparkleIcon } from "../../components/Icons";

interface Props {
  messages: MessageResponse[];
}

// Right-hand panel modeled on MOSO's "understanding your search" pattern — since
// Auremont is an internal document-lookup assistant (not a customer-facing AI
// search), the actual content here is the list of citations used for the most
// recent answer, not a fabricated "intent understanding" feature.
export function ChatContextPanel({ messages }: Props) {
  const lastBotWithCitations = [...messages].reverse().find((m) => m.sender !== "sale" && m.citations && m.citations.length > 0);

  return (
    <aside className="chat-context-panel">
      <div className="chat-context-head">
        <SparkleIcon size={14} />
        Auremont đang tra cứu
      </div>

      {lastBotWithCitations ? (
        <>
          <p className="chat-context-hint">Nguồn tài liệu dùng cho câu trả lời gần nhất:</p>
          <div className="chat-context-sources">
            {lastBotWithCitations.citations!.map((c) => (
              <div key={`${c.document_id}-${c.page ?? 0}`} className="chat-context-source">
                <DocumentIcon size={13} />
                <span>
                  {c.title}
                  {c.page != null && ` · tr.${c.page}`}
                </span>
              </div>
            ))}
          </div>
        </>
      ) : (
        <p className="chat-context-hint">
          Chưa có ngữ cảnh — hãy đặt câu hỏi về bảng giá, mặt bằng hoặc chính sách bán hàng, Auremont sẽ liệt kê nguồn
          tài liệu đã dùng ở đây.
        </p>
      )}
    </aside>
  );
}
