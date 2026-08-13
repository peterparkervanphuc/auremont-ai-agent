import type { MessageResponse } from "../../types";
import { DocumentIcon, SparkleIcon } from "../../components/Icons";

interface Props {
  messages: MessageResponse[];
}

// Panel ben phai kieu "MOSO hieu ban dang tim" — vi Auremont la tro ly noi bo
// tra cuu tai lieu (khong phai AI search khach hang), noi dung THAT o day la
// liet ke nguon tai lieu (citations) da dung cho cau tra loi gan nhat, khong
// bia ra 1 tinh nang "hieu y dinh" chua co that.
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
