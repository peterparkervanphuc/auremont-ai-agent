import { ArrowRightIcon } from "../../components/Icons";

const SUGGESTED_QUESTIONS = [
  "Bảng giá căn hộ The Zurich hiện tại thế nào?",
  "Mặt bằng tòa BE1 The Beverly có những loại căn nào?",
  "Chính sách bán hàng, tiến độ thanh toán ra sao?",
  "Còn căn 2 ngủ nào trống ở The Sapphire không?",
];

interface Props {
  onPick: (question: string) => void;
}

// Card "Thu hoi" kieu MOSO — goi y san 4 cau hoi thuong gap cho sale, bam vao
// se dien vao o nhap (khong tu gui, de sale kip chinh sua truoc khi hoi).
export function ChatSuggestions({ onPick }: Props) {
  return (
    <div className="chat-suggest-card">
      <span className="chat-suggest-label">Thử hỏi</span>
      {SUGGESTED_QUESTIONS.map((q) => (
        <button key={q} type="button" className="chat-suggest-item" onClick={() => onPick(q)}>
          <span>{q}</span>
          <ArrowRightIcon size={15} />
        </button>
      ))}
    </div>
  );
}
