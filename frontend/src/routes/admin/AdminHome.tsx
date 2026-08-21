import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { useAuth } from "../../hooks/useAuth";

interface BusinessDashboard {
  period_days: number;
  applied_filters: { project_id: string | null; sale_id: number | null };
  filter_options: { projects: { id: string; name: string }[]; sales: { id: number; username: string }[] };
  verifier_threshold: number;
  summary: { sessions: number; customers: number; questions: number; active_sales: number; helpful_rate: number | null; verifier_avg: number | null; hitl_required: number; hitl_confirmed: number };
  activity: { date: string; sessions: number; questions: number }[];
  top_projects: { project_id: string | null; name: string; sessions: number }[];
  top_sales: { sale_id: number; username: string; sessions: number; customers: number; questions: number }[];
  feedback_distribution: { helpful: number; wrong: number; incomplete: number; unrated: number };
  quality_trend: { date: string; faithfulness: number | null; relevancy: number | null }[];
  hitl_funnel: { answers: number; required: number; confirmed: number };
  document_coverage: { project_id: string; name: string; ready_count: number; categories: Record<string, "ready" | "pending_review" | "unavailable" | "missing"> }[];
}

const EMPTY: BusinessDashboard = {
  period_days: 14,
  applied_filters: { project_id: null, sale_id: null },
  filter_options: { projects: [], sales: [] }, verifier_threshold: .7,
  summary: { sessions: 0, customers: 0, questions: 0, active_sales: 0, helpful_rate: null, verifier_avg: null, hitl_required: 0, hitl_confirmed: 0 },
  activity: [], top_projects: [], top_sales: [],
  feedback_distribution: { helpful: 0, wrong: 0, incomplete: 0, unrated: 0 },
  quality_trend: [], hitl_funnel: { answers: 0, required: 0, confirmed: 0 }, document_coverage: [],
};

type DashboardDetail = { title: string; subtitle: string; rows: { label: string; value: string | number }[] };

const percent = (value: number | null) => value == null ? "Chưa có dữ liệu" : `${Math.round(value * 100)}%`;
function shortDate(value: string) { const d = new Date(`${value}T00:00:00`); return `${d.getDate()}/${d.getMonth() + 1}`; }

const CATEGORY_LABELS: Record<string, string> = {
  sales_policy: "Chính sách", price_list: "Bảng giá", floor_plan: "Mặt bằng", legal_document: "Pháp lý", payment_schedule: "Thanh toán",
};

function QualityChart({ points, threshold, onSelect }: { points: BusinessDashboard["quality_trend"]; threshold: number; onSelect: () => void }) {
  const valid = points.some((point) => point.faithfulness != null || point.relevancy != null);
  if (!valid) return <div className="business-empty">Chưa có điểm chất lượng trong kỳ này.</div>;
  const path = (key: "faithfulness" | "relevancy") => points.map((point, index) => {
    const value = point[key];
    if (value == null) return null;
    const x = points.length === 1 ? 50 : index / (points.length - 1) * 100;
    const y = 100 - value * 100;
    return `${x},${y}`;
  }).filter(Boolean).join(" ");
  return <button type="button" className="business-quality-chart" onClick={onSelect} aria-label="Xem chi tiết xu hướng chất lượng AI">
    <svg viewBox="0 0 100 100" preserveAspectRatio="none" role="img" aria-label="Xu hướng faithfulness và relevancy">
      <line x1="0" y1={100 - threshold * 100} x2="100" y2={100 - threshold * 100} className="business-threshold" />
      <polyline points={path("faithfulness")} className="business-quality-line business-quality-line--faith" />
      <polyline points={path("relevancy")} className="business-quality-line business-quality-line--relevant" />
    </svg>
    <div className="business-quality-axis"><span>{shortDate(points[0].date)}</span><span>{shortDate(points[points.length - 1].date)}</span></div>
  </button>;
}

export function AdminHome() {
  const { username } = useAuth();
  const [dashboard, setDashboard] = useState<BusinessDashboard | null>(null);
  const [failed, setFailed] = useState(false);
  const [days, setDays] = useState(14);
  const [projectId, setProjectId] = useState("");
  const [saleId, setSaleId] = useState("");
  const [detail, setDetail] = useState<DashboardDetail | null>(null);

  useEffect(() => {
    const params = new URLSearchParams({ days: String(days) });
    if (projectId) params.set("project_id", projectId);
    if (saleId) params.set("sale_id", saleId);
    setFailed(false);

    // Filter changes fire faster than the dashboard query returns, and the responses can
    // land out of order — without this flag a slower earlier request overwrites a newer
    // one, leaving numbers on screen that belong to filters the Admin already moved off.
    let cancelled = false;
    api
      .get<BusinessDashboard>(`/admin/stats/business?${params}`)
      .then((result) => {
        if (!cancelled) setDashboard(result);
      })
      .catch(() => {
        if (!cancelled) setFailed(true);
      });
    return () => {
      cancelled = true;
    };
  }, [days, projectId, saleId]);

  const data = dashboard ?? EMPTY;
  const maxActivity = useMemo(() => Math.max(1, ...data.activity.map((d) => Math.max(d.sessions, d.questions))), [data.activity]);
  const maxProject = Math.max(1, ...data.top_projects.map((p) => p.sessions));
  const hitlRate = data.summary.hitl_required ? data.summary.hitl_confirmed / data.summary.hitl_required : null;
  const feedbackTotal = Object.values(data.feedback_distribution).reduce((sum, value) => sum + value, 0);
  const feedbackAngles = {
    helpful: feedbackTotal ? data.feedback_distribution.helpful / feedbackTotal * 360 : 0,
    wrong: feedbackTotal ? data.feedback_distribution.wrong / feedbackTotal * 360 : 0,
    incomplete: feedbackTotal ? data.feedback_distribution.incomplete / feedbackTotal * 360 : 0,
  };
  const resetFilters = () => { setDays(14); setProjectId(""); setSaleId(""); setDetail(null); };
  const showDetail = (title: string, subtitle: string, rows: DashboardDetail["rows"]) => setDetail({ title, subtitle, rows });

  return (
    <div className="page business-dashboard">
      <div className="page-head business-dashboard-head">
        <div>
          <p className="business-eyebrow">Tổng quan 14 ngày gần nhất</p>
          <h2 className="page-title">Tổng quan kinh doanh</h2>
          <p className="page-sub">Chào {username ?? "bạn"}, theo dõi hoạt động tư vấn và mức độ quan tâm dự án từ dữ liệu SalesMate.</p>
        </div>
        <div className="business-period">Cập nhật theo dữ liệu hệ thống</div>
      </div>

      <div className="business-filters" aria-label="Bộ lọc dashboard">
        <label>Thời gian<select value={days} onChange={(event) => setDays(Number(event.target.value))}><option value={7}>7 ngày</option><option value={14}>14 ngày</option><option value={30}>30 ngày</option></select></label>
        <label>Dự án<select value={projectId} onChange={(event) => setProjectId(event.target.value)}><option value="">Tất cả dự án</option>{data.filter_options.projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label>
        <label>Nhân viên Sale<select value={saleId} onChange={(event) => setSaleId(event.target.value)}><option value="">Tất cả Sale</option>{data.filter_options.sales.map((sale) => <option key={sale.id} value={sale.id}>{sale.username}</option>)}</select></label>
        {(days !== 14 || projectId || saleId) && <button type="button" onClick={resetFilters}>Đặt lại</button>}
      </div>

      {failed && <div className="business-notice">Không thể tải số liệu. Vui lòng thử lại sau.</div>}

      <div className="business-kpi-grid">
        <article className="business-kpi business-kpi--primary"><span>Phiên tư vấn</span><strong>{dashboard ? data.summary.sessions : "—"}</strong><small>Trong {data.period_days} ngày gần nhất</small></article>
        <article className="business-kpi"><span>Khách hàng có thông tin</span><strong>{dashboard ? data.summary.customers : "—"}</strong><small>Phiên có nhập tên khách hàng</small></article>
        <article className="business-kpi"><span>Câu hỏi tư vấn</span><strong>{dashboard ? data.summary.questions : "—"}</strong><small>Được đội Sale gửi tới AI</small></article>
        <article className="business-kpi"><span>Sale hoạt động</span><strong>{dashboard ? data.summary.active_sales : "—"}</strong><small>Có ít nhất một phiên tư vấn</small></article>
      </div>

      <div className="business-main-grid">
        <section className="business-panel business-activity-panel">
          <div className="business-panel-head"><div><h3>Xu hướng tư vấn</h3><p>Phiên tư vấn và câu hỏi theo ngày</p></div><div className="business-legend"><span><i className="legend-session" />Phiên</span><span><i className="legend-question" />Câu hỏi</span></div></div>
          {data.activity.length === 0 ? <div className="business-empty">Chưa có hoạt động trong kỳ này.</div> : (
            <div className="business-chart" aria-label="Biểu đồ hoạt động tư vấn 14 ngày">
              {data.activity.map((day, index) => <button type="button" className="business-chart-day" key={day.date} onClick={() => showDetail(`Hoạt động ngày ${shortDate(day.date)}`, "Số liệu trong phạm vi bộ lọc hiện tại", [{ label: "Phiên tư vấn", value: day.sessions }, { label: "Câu hỏi AI", value: day.questions }])}>
                <div className="business-chart-bars"><i className="business-bar business-bar--session" style={{ height: `${Math.max(3, day.sessions / maxActivity * 100)}%` }} title={`${day.sessions} phiên`} /><i className="business-bar business-bar--question" style={{ height: `${Math.max(3, day.questions / maxActivity * 100)}%` }} title={`${day.questions} câu hỏi`} /></div>
                {(index % 2 === 0 || index === data.activity.length - 1) && <span>{shortDate(day.date)}</span>}
              </button>)}
            </div>
          )}
        </section>

        <section className="business-panel business-quality-panel">
          <div className="business-panel-head"><div><h3>Chất lượng tư vấn</h3><p>Các chỉ số an toàn đang ghi nhận</p></div></div>
          <div className="business-quality-list">
            <div><span>Feedback hữu ích</span><strong>{percent(data.summary.helpful_rate)}</strong></div>
            <div><span>Điểm verifier trung bình</span><strong>{percent(data.summary.verifier_avg)}</strong></div>
            <div><span>Xác nhận nội dung rủi ro</span><strong>{percent(hitlRate)}</strong><small>{data.summary.hitl_confirmed}/{data.summary.hitl_required} câu cần HITL</small></div>
          </div>
        </section>
      </div>

      <div className="business-bottom-grid">
        <section className="business-panel">
          <div className="business-panel-head"><div><h3>Dự án được quan tâm</h3><p>Xếp theo số phiên có gắn dự án</p></div></div>
          {data.top_projects.length === 0 ? <div className="business-empty">Các phiên hiện chưa ghi nhận dự án.</div> : <div className="business-ranking">{data.top_projects.map((project, index) => <button type="button" className="business-rank-row" key={project.project_id ?? "unknown"} onClick={() => { if (project.project_id) setProjectId(project.project_id); showDetail(project.name, project.project_id ? "Dashboard đã được lọc theo dự án này" : "Các phiên chưa gắn dự án", [{ label: "Phiên tư vấn", value: project.sessions }]); }}><span className="business-rank-number">{index + 1}</span><span className="business-rank-main"><span><strong>{project.name}</strong><span>{project.sessions} phiên</span></span><span className="business-progress"><i style={{ width: `${project.sessions / maxProject * 100}%` }} /></span></span></button>)}</div>}
        </section>

        <section className="business-panel">
          <div className="business-panel-head"><div><h3>Hoạt động đội Sale</h3><p>Top nhân viên theo số phiên tư vấn</p></div></div>
          {data.top_sales.length === 0 ? <div className="business-empty">Chưa có Sale hoạt động trong kỳ này.</div> : <div className="business-sale-table"><div className="business-sale-table-head"><span>Nhân viên</span><span>Khách</span><span>Phiên</span><span>Hỏi AI</span></div>{data.top_sales.map((sale) => <button type="button" className="business-sale-row" key={sale.sale_id} onClick={() => { setSaleId(String(sale.sale_id)); showDetail(sale.username, "Dashboard đã được lọc theo nhân viên này", [{ label: "Khách hàng", value: sale.customers }, { label: "Phiên tư vấn", value: sale.sessions }, { label: "Câu hỏi AI", value: sale.questions }]); }}><span><i>{sale.username.slice(0, 1).toUpperCase()}</i>{sale.username}</span><strong>{sale.customers}</strong><strong>{sale.sessions}</strong><strong>{sale.questions}</strong></button>)}</div>}
        </section>
      </div>

      <div className="business-detail-grid">
        <section className="business-panel">
          <div className="business-panel-head"><div><h3>Phản hồi câu trả lời</h3><p>Bao gồm cả câu trả lời chưa được đánh giá</p></div></div>
          {feedbackTotal === 0 ? <div className="business-empty">Chưa có câu trả lời trong kỳ này.</div> : <div className="business-feedback-wrap">
            <div className="business-donut" style={{ background: `conic-gradient(var(--sage) 0 ${feedbackAngles.helpful}deg, var(--rose) ${feedbackAngles.helpful}deg ${feedbackAngles.helpful + feedbackAngles.wrong}deg, var(--amber) ${feedbackAngles.helpful + feedbackAngles.wrong}deg ${feedbackAngles.helpful + feedbackAngles.wrong + feedbackAngles.incomplete}deg, var(--bg-3) ${feedbackAngles.helpful + feedbackAngles.wrong + feedbackAngles.incomplete}deg 360deg)` }}><strong>{feedbackTotal}</strong><span>câu trả lời</span></div>
            <div className="business-feedback-legend"><button type="button" onClick={() => showDetail("Feedback hữu ích", "Câu trả lời được Sale đánh giá hữu ích", [{ label: "Số câu", value: data.feedback_distribution.helpful }])}><i className="feedback-helpful" />Hữu ích <strong>{data.feedback_distribution.helpful}</strong></button><button type="button" onClick={() => showDetail("Feedback sai", "Câu trả lời cần Admin kiểm tra", [{ label: "Số câu", value: data.feedback_distribution.wrong }])}><i className="feedback-wrong" />Sai <strong>{data.feedback_distribution.wrong}</strong></button><button type="button" onClick={() => showDetail("Feedback thiếu", "Câu trả lời thiếu thông tin", [{ label: "Số câu", value: data.feedback_distribution.incomplete }])}><i className="feedback-incomplete" />Thiếu <strong>{data.feedback_distribution.incomplete}</strong></button><button type="button" onClick={() => showDetail("Chưa đánh giá", "Câu trả lời chưa nhận feedback", [{ label: "Số câu", value: data.feedback_distribution.unrated }])}><i className="feedback-unrated" />Chưa đánh giá <strong>{data.feedback_distribution.unrated}</strong></button></div>
          </div>}
        </section>

        <section className="business-panel">
          <div className="business-panel-head"><div><h3>Phễu kiểm soát HITL</h3><p>Mức tuân thủ với nội dung giá và cam kết</p></div></div>
          <div className="business-funnel">
            <button type="button" style={{ width: "100%" }} onClick={() => showDetail("Câu trả lời AI", "Tổng câu trả lời trong phạm vi bộ lọc", [{ label: "Số câu", value: data.hitl_funnel.answers }])}><span>Câu trả lời AI</span><strong>{data.hitl_funnel.answers}</strong></button>
            <button type="button" style={{ width: `${Math.max(48, data.hitl_funnel.answers ? data.hitl_funnel.required / data.hitl_funnel.answers * 100 : 48)}%` }} onClick={() => showDetail("Cần xác nhận HITL", "Nội dung liên quan giá hoặc cam kết", [{ label: "Số câu", value: data.hitl_funnel.required }, { label: "Chưa xác nhận", value: Math.max(0, data.hitl_funnel.required - data.hitl_funnel.confirmed) }])}><span>Cần xác nhận</span><strong>{data.hitl_funnel.required}</strong></button>
            <button type="button" style={{ width: `${Math.max(32, data.hitl_funnel.required ? data.hitl_funnel.confirmed / data.hitl_funnel.required * 100 : 32)}%` }} onClick={() => showDetail("Đã xác nhận HITL", "Nội dung đã được Sale xác nhận", [{ label: "Số câu", value: data.hitl_funnel.confirmed }])}><span>Đã xác nhận</span><strong>{data.hitl_funnel.confirmed}</strong></button>
          </div>
        </section>

        <section className="business-panel business-quality-trend-panel">
          <div className="business-panel-head"><div><h3>Xu hướng chất lượng AI</h3><p>Faithfulness và độ liên quan theo ngày</p></div><div className="business-legend"><span><i className="legend-faith" />Bám nguồn</span><span><i className="legend-relevant" />Liên quan</span></div></div>
          <QualityChart points={data.quality_trend} threshold={data.verifier_threshold} onSelect={() => showDetail("Chất lượng AI", `Ngưỡng verifier hiện tại: ${percent(data.verifier_threshold)}`, [{ label: "Faithfulness trung bình", value: percent(data.summary.verifier_avg) }, { label: "Số ngày", value: data.quality_trend.length }])} />
        </section>
      </div>

      <section className="business-panel business-coverage-panel">
        <div className="business-panel-head"><div><h3>Độ phủ tài liệu theo dự án</h3><p>Tài liệu hiện hành phục vụ đội Sale; xanh là đã ingest xong và AI dùng được</p></div><div className="business-coverage-legend"><span><i className="coverage-ready" />Sẵn sàng</span><span><i className="coverage-missing" />Chưa có</span></div></div>
        {data.document_coverage.length === 0 ? <div className="business-empty">Chưa có dữ liệu dự án.</div> : <div className="business-coverage-table"><div className="business-coverage-head"><span>Dự án</span>{Object.values(CATEGORY_LABELS).map((label) => <span key={label}>{label}</span>)}</div>{data.document_coverage.map((project) => <div className="business-coverage-row" key={project.project_id}><strong>{project.name}</strong>{Object.keys(CATEGORY_LABELS).map((category) => <Link key={category} to={`/documents?project_id=${encodeURIComponent(project.project_id)}&category=${category}`} className={`coverage-cell coverage-${project.categories[category]}`} title={`Mở ${CATEGORY_LABELS[category]}: ${project.categories[category]}`} aria-label={`Mở tài liệu ${CATEGORY_LABELS[category]} của ${project.name}`}><i /></Link>)}</div>)}</div>}
      </section>

      {detail && <aside className="business-detail-drawer" aria-live="polite"><div><div><p>Chi tiết dashboard</p><h3>{detail.title}</h3><span>{detail.subtitle}</span></div><button type="button" onClick={() => setDetail(null)} aria-label="Đóng chi tiết">×</button></div><dl>{detail.rows.map((row) => <div key={row.label}><dt>{row.label}</dt><dd>{row.value}</dd></div>)}</dl></aside>}

      <p className="business-footnote">Dashboard phản ánh hoạt động tư vấn trong SalesMate; chưa bao gồm doanh thu, hợp đồng hoặc tỷ lệ chốt vì hệ thống chưa lưu các dữ liệu này.</p>
    </div>
  );
}
