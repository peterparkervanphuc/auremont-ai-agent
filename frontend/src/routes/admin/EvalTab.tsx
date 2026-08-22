import { useCallback, useEffect, useState, type CSSProperties } from "react";
import { api } from "../../api/client";
import { AdminMetricCard } from "../../components/admin/AdminMetricCard";
import { AdminPageHeader } from "../../components/admin/AdminPageHeader";
import { AlertIcon, ChartIcon, CheckIcon, RefreshIcon, ShieldCheckIcon, XIcon } from "../../components/Icons";

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

function percent(value: number | null): string {
  return value == null ? "—" : `${Math.round(value * 100)}%`;
}

function QualityGauge({ label, value, description }: { label: string; value: number | null; description: string }) {
  const score = value == null ? 0 : Math.round(value * 100);
  const tone = score >= 85 ? "is-good" : score >= 70 ? "is-warning" : "is-danger";

  return (
    <article className={`eval-gauge ${tone}`} tabIndex={0}>
      <div className="eval-gauge-ring" style={{ "--score": `${score * 3.6}deg` } as CSSProperties}>
        <div><strong>{value == null ? "—" : `${score}%`}</strong><span>trung bình</span></div>
      </div>
      <div className="eval-gauge-copy"><h3>{label}</h3><p>{description}</p><span>Rê chuột để làm nổi bật chỉ số</span></div>
    </article>
  );
}

export function EvalTab() {
  const [scores, setScores] = useState<EvalScores | null>(null);
  const [failedToLoad, setFailedToLoad] = useState(false);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<FailedQuestion | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setScores(await api.get<EvalScores>("/admin/eval/scores"));
      setFailedToLoad(false);
    } catch {
      setFailedToLoad(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const failed = scores?.top_failed_questions ?? [];
  const totalReports = failed.reduce((sum, item) => sum + item.feedback_count, 0);

  return (
    <div className="page admin-dashboard-page business-dashboard admin-workspace admin-eval-page">
      <AdminPageHeader
        eyebrow="AI quality assurance"
        title="Chất lượng trả lời"
        description="Theo dõi mức độ bám nguồn, độ liên quan và các câu trả lời bị Sale đánh dấu cần cải thiện."
        actions={<button className="business-refresh" type="button" disabled={loading} onClick={() => void load()}><RefreshIcon size={15} className={loading ? "is-spinning" : ""} /> Làm mới</button>}
      />

      {failedToLoad ? <div className="alert alert-danger">Không tải được điểm đánh giá từ backend.</div> : null}

      <div className="admin-metric-grid admin-workspace-metrics">
        <AdminMetricCard label="Bám sát nguồn" value={percent(scores?.faithfulness_avg ?? null)} hint="Faithfulness trung bình" icon={<ShieldCheckIcon size={20} />} tone={(scores?.faithfulness_avg ?? 0) >= 0.85 ? "success" : "warning"} tooltip="Điểm trung bình từ Verifier Agent trên các câu đã được đánh giá." />
        <AdminMetricCard label="Độ liên quan" value={percent(scores?.answer_relevancy_avg ?? null)} hint="Answer relevancy" icon={<ChartIcon size={20} />} tone={(scores?.answer_relevancy_avg ?? 0) >= 0.85 ? "success" : "warning"} tooltip="Mức độ câu trả lời đáp ứng đúng trọng tâm câu hỏi." />
        <AdminMetricCard label="Câu hỏi cần xử lý" value={failed.length} hint="Top phản hồi tiêu cực" icon={<AlertIcon size={20} />} tone={failed.length ? "danger" : "success"} tooltip="Số câu hỏi xuất hiện trong danh sách ưu tiên hiện tại." />
        <AdminMetricCard label="Lượt báo cáo" value={totalReports} hint="Sai hoặc chưa đầy đủ" icon={<AlertIcon size={20} />} tone={totalReports ? "warning" : "success"} tooltip="Tổng số feedback gắn với các câu hỏi ưu tiên." />
      </div>

      <div className="admin-two-column eval-overview-grid">
        <section className="business-panel admin-ui-panel">
          <div className="business-panel-head"><div><h3>Quality score overview</h3><p>Hai tín hiệu Verifier quan trọng nhất của câu trả lời AI.</p></div><span className="ops-caption-badge">Live scores</span></div>
          <div className="eval-gauge-grid">
            <QualityGauge label="Bám sát nguồn" value={scores?.faithfulness_avg ?? null} description="Đo mức độ các khẳng định được hỗ trợ bởi tài liệu truy xuất." />
            <QualityGauge label="Độ liên quan" value={scores?.answer_relevancy_avg ?? null} description="Đo mức độ câu trả lời tập trung đúng nhu cầu của người hỏi." />
          </div>
        </section>

        <section className="business-panel admin-ui-panel eval-priority-panel">
          <div className="business-panel-head"><div><h3>Ưu tiên cải thiện</h3><p>Nhấn một dòng để mở thông tin xử lý.</p></div><span className={`admin-count-badge ${failed.length ? "is-danger" : ""}`}>{failed.length} câu</span></div>
          {loading && !scores ? <div className="admin-empty compact">Đang tải điểm đánh giá…</div> : failed.length === 0 ? (
            <div className="ops-empty-state compact"><CheckIcon size={24} /><strong>Chưa có câu hỏi thất bại</strong><span>Feedback tiêu cực mới sẽ xuất hiện tại đây.</span></div>
          ) : (
            <div className="eval-failed-list">
              {failed.map((item, index) => (
                <button type="button" key={item.message_id} className={selected?.message_id === item.message_id ? "is-active" : ""} onClick={() => setSelected(item)}>
                  <span>#{index + 1}</span><strong>{item.question}</strong><em>{item.feedback_count} báo cáo</em>
                  <i>Nhấn để xem chi tiết</i>
                </button>
              ))}
            </div>
          )}
        </section>
      </div>

      {selected ? (
        <aside className="business-detail-drawer eval-detail-drawer" aria-live="polite">
          <div><div><p>Chi tiết phản hồi</p><h3>Câu hỏi #{selected.message_id}</h3><span>Ưu tiên kiểm tra tài liệu và câu trả lời gốc.</span></div><button type="button" onClick={() => setSelected(null)} aria-label="Đóng chi tiết"><XIcon size={17} /></button></div>
          <blockquote>{selected.question}</blockquote>
          <dl><div><dt>Số lượt báo cáo</dt><dd>{selected.feedback_count}</dd></div><div><dt>Hướng xử lý</dt><dd>Kiểm tra nguồn / bổ sung tài liệu</dd></div></dl>
        </aside>
      ) : null}
    </div>
  );
}
