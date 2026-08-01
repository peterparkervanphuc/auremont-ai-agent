import { useEffect, useState } from "react";
import { api } from "../../api/client";

interface EvalScores {
  channel: string;
  faithfulness_avg: number | null;
  answer_relevancy_avg: number | null;
  top_failed_questions: string[];
}

// CLAUDE.md §6.5 Tab 2 — điểm DeepEval tách riêng theo kênh Sale vs Chatbot công khai.
export function EvalTab() {
  const [saleScores, setSaleScores] = useState<EvalScores | null>(null);
  const [publicScores, setPublicScores] = useState<EvalScores | null>(null);

  useEffect(() => {
    api.get<EvalScores>("/admin/eval/scores?channel=sale").then(setSaleScores);
    api.get<EvalScores>("/admin/eval/scores?channel=public").then(setPublicScores);
  }, []);

  return (
    <div>
      <h3>Đánh giá & Phân tích AI</h3>
      <section>
        <h4>Agent nội bộ (Sale)</h4>
        <p>Faithfulness: {saleScores?.faithfulness_avg ?? "—"}</p>
        <p>Answer Relevancy: {saleScores?.answer_relevancy_avg ?? "—"}</p>
      </section>
      <section>
        <h4>Chatbot công khai (Khách hàng)</h4>
        <p>Faithfulness: {publicScores?.faithfulness_avg ?? "—"}</p>
        <p>Answer Relevancy: {publicScores?.answer_relevancy_avg ?? "—"}</p>
      </section>
    </div>
  );
}
