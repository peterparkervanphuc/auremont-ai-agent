import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { AlertIcon, ChartIcon } from "../../components/Icons";

interface FailedQuestion {
  message_id: number;
  question: string;
  feedback_count: number;
}

interface EvalScores {
  faithfulness_avg: number | null;
  answer_relevancy_avg: number | null;
  top_failed_questions: FailedQuestion[];
}

function ScoreCard({ label, value }: { label: string; value: number | null }) {
  const pct = value == null ? 0 : Math.round(value * 100);
  return (
    <div className="stat-card">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value == null ? "—" : `${pct}%`}</div>
      <div className="stat-bar">
        <div className="stat-bar-fill" style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

// Điểm chất lượng trả lời (Verifier Agent chấm tự động) + top câu hỏi AI trả lời chưa tốt.
export function EvalTab() {
  const [scores, setScores] = useState<EvalScores | null>(null);

  useEffect(() => {
    api.get<EvalScores>("/admin/eval/scores").then(setScores).catch(() => {});
  }, []);

  const failed = scores?.top_failed_questions ?? [];

  return (
    <div className="page">
      <h2 className="page-title">Chất lượng trả lời</h2>
      <p className="page-sub">Điểm tự động đo mức độ bám sát nguồn tài liệu và độ liên quan của câu trả lời AI.</p>

      <section className="section-block">
        <div className="stat-grid">
          <ScoreCard label="Bám sát nguồn" value={scores?.faithfulness_avg ?? null} />
          <ScoreCard label="Độ liên quan" value={scores?.answer_relevancy_avg ?? null} />
        </div>
      </section>

      <section>
        <h3 className="section-title">Top câu hỏi AI trả lời thất bại</h3>
        <p className="page-sub" style={{ marginBottom: 12 }}>
          Tổng hợp từ nút Feedback của Sale — ưu tiên bổ sung tài liệu cho các câu hỏi này.
        </p>
        {failed.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">
              <ChartIcon size={26} />
            </div>
            <p>Chưa có câu hỏi thất bại nào được ghi nhận.</p>
          </div>
        ) : (
          <div className="data-list">
            {failed.map((f, i) => (
              <div key={f.message_id} className="data-row">
                <span className="badge badge-warning">
                  <AlertIcon size={12} />#{i + 1}
                </span>
                <span style={{ flex: 1, minWidth: 0 }}>{f.question}</span>
                <span className="badge badge-muted">{f.feedback_count} báo cáo</span>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
