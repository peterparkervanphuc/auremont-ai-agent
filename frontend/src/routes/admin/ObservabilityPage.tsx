import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { adminDashboardApi } from "../../api/adminDashboard";
import { ActivityIcon, AlertIcon, ApiIcon, BotIcon, ChartIcon, RefreshIcon, ServerIcon, TerminalIcon, UsersIcon } from "../../components/Icons";
import { AdminMetricCard } from "../../components/admin/AdminMetricCard";
import { ApiTester } from "../../components/admin/ApiTester";
import { SwaggerConsoleModal } from "../../components/admin/SwaggerConsoleModal";
import { TraceTimeline } from "../../components/admin/TraceTimeline";
import type { ObservabilityOverview, TraceSummary } from "../../types/admin";
import { parseServerDate } from "../../utils/datetime";

const number = new Intl.NumberFormat("vi-VN");

function HorizontalBars({ rows }: { rows: { label: string; count: number }[] }) {
  const max = Math.max(...rows.map((row) => row.count), 1);
  if (!rows.some((row) => row.count)) return <div className="admin-empty compact">Chưa có dữ liệu trong kỳ.</div>;
  return <div className="horizontal-bars">{rows.map((row) => <div className="horizontal-bar" key={row.label}><div><span>{row.label}</span><strong>{row.count}</strong></div><i><span style={{ width: `${row.count / max * 100}%` }} /></i></div>)}</div>;
}

export function ObservabilityPage() {
  const [data, setData] = useState<ObservabilityOverview | null>(null);
  const [days, setDays] = useState(14);
  const [error, setError] = useState<string | null>(null);
  const [swaggerOpen, setSwaggerOpen] = useState(false);
  const [selectedTrace, setSelectedTrace] = useState<TraceSummary | null>(null);
  const [severity, setSeverity] = useState("ALL");
  const [module, setModule] = useState("ALL");

  const load = useCallback(async () => {
    try {
      setError(null);
      const next = await adminDashboardApi.observability(days);
      setData(next);
      setSelectedTrace((current) => next.traces.find((trace) => trace.run_id === current?.run_id) ?? next.traces[0] ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được dữ liệu giám sát.");
    }
  }, [days]);

  useEffect(() => { void load(); }, [load]);

  const modules = useMemo(() => [...new Set(data?.logs.map((log) => log.module) ?? [])], [data]);
  const filteredLogs = useMemo(() => (data?.logs ?? []).filter((log) => (severity === "ALL" || log.severity === severity) && (module === "ALL" || log.module === module)), [data, severity, module]);
  const maxDailyTokens = Math.max(...(data?.tokens.daily.map((day) => day.input_tokens + day.output_tokens) ?? []), 1);

  return (
    <div className="page admin-dashboard-page">
      <header className="admin-page-head">
        <div><span className="admin-eyebrow">AI & platform operations</span><h1 className="page-title">Giám sát hệ thống</h1><p className="page-sub">Độ tin cậy AI tools, token, logs, audit trace và cảnh báo cần can thiệp.</p></div>
        <div className="admin-head-actions"><select value={days} onChange={(event) => setDays(Number(event.target.value))}><option value={7}>7 ngày</option><option value={14}>14 ngày</option><option value={30}>30 ngày</option></select><button className="btn btn-outline" type="button" onClick={() => void load()}><RefreshIcon size={15} /> Làm mới</button><button className="btn btn-primary" type="button" onClick={() => setSwaggerOpen(true)}><ApiIcon size={16} /> FastAPI Console</button></div>
      </header>
      {error && <div className="alert alert-danger">{error}</div>}
      {!data ? <div className="admin-empty">Đang tải metrics…</div> : <>
        <div className="admin-metric-grid">
          <AdminMetricCard label="DAU / MAU" value={`${data.users.dau} / ${data.users.mau}`} hint="Người dùng có audit activity" icon={<UsersIcon size={20} />} />
          <AdminMetricCard label="Active sessions" value={data.users.active_sessions} hint={`${data.users.waiting_sessions} đang chờ Sale`} icon={<ActivityIcon size={20} />} tone={data.users.waiting_sessions ? "warning" : "success"} />
          <AdminMetricCard label="Tokens trong kỳ" value={number.format(data.tokens.input_tokens + data.tokens.output_tokens)} hint={`${number.format(data.tokens.input_tokens)} input · ${number.format(data.tokens.output_tokens)} output`} icon={<BotIcon size={20} />} />
          <AdminMetricCard label="Chi phí ước tính" value={data.tokens.cost_configured ? `$${data.tokens.estimated_cost_usd.toFixed(2)}` : "Chưa cấu hình"} hint={data.tokens.cost_configured ? `Dự phóng tháng $${data.tokens.projected_monthly_cost_usd.toFixed(2)}` : "Thiết lập đơn giá token trong môi trường"} icon={<ChartIcon size={20} />} />
        </div>

        <div className="admin-two-column">
          <section className="admin-panel">
            <div className="admin-panel-head"><div><h2>Tool Reliability</h2><p>Xếp hạng theo số lỗi trong pipeline trace.</p></div><ServerIcon size={20} /></div>
            {!data.tracing_enabled && <div className="admin-inline-note">Tracing đang tắt. Bật <code>TRACING_ENABLED=true</code> để thu thập metrics.</div>}
            <div className="tool-list">{data.tool_reliability.map((tool) => <article key={tool.key} className="tool-row"><div className="tool-row-title"><strong>{tool.name}</strong><span>{tool.calls} calls · {tool.errors} errors</span></div><div className="tool-progress"><i><span className={tool.success_rate != null && tool.success_rate < 90 ? "is-warning" : ""} style={{ width: `${tool.success_rate ?? 0}%` }} /></i><strong>{tool.success_rate == null ? "—" : `${tool.success_rate}%`}</strong></div><span className="tool-latency">{tool.average_latency_ms == null ? "Chưa đo latency" : `${number.format(tool.average_latency_ms)} ms avg`}</span></article>)}</div>
          </section>

          <section className="admin-panel">
            <div className="admin-panel-head"><div><h2>Token Consumption</h2><p>Input và output tokens theo ngày.</p></div><ChartIcon size={20} /></div>
            <div className="token-chart" aria-label="Biểu đồ token theo ngày">{data.tokens.daily.map((day) => { const total = day.input_tokens + day.output_tokens; return <div className="token-day" key={day.date} title={`${day.date}: ${number.format(total)} tokens`}><div className="token-stack" style={{ height: `${Math.max(total / maxDailyTokens * 100, total ? 4 : 1)}%` }}><i className="token-input" style={{ flex: day.input_tokens || 0 }} /><i className="token-output" style={{ flex: day.output_tokens || 0 }} /></div><span>{day.date.slice(5).replace("-", "/")}</span></div>; })}</div>
            <div className="chart-legend"><span><i className="legend-input" /> Input</span><span><i className="legend-output" /> Output</span></div>
          </section>
        </div>

        <div className="admin-two-column">
          <section className="admin-panel"><div className="admin-panel-head"><div><h2>Real Estate Intent Analytics</h2><p>Phân khúc ngân sách được khách nhắc đến.</p></div></div><HorizontalBars rows={data.budget_intents.map((item) => ({ label: item.label, count: item.count }))} /></section>
          <section className="admin-panel"><div className="admin-panel-head"><div><h2>Dự án được hỏi nhiều</h2><p>Dựa trên project của phiên khách trong kỳ.</p></div></div><HorizontalBars rows={data.popular_projects.map((item) => ({ label: item.project_name, count: item.count }))} /></section>
        </div>

        <section className="admin-panel fallback-panel">
          <div className="admin-panel-head"><div><h2>AI Fallback & Intervention</h2><p>Câu trả lời thấp hơn ngưỡng Verifier, cần người kiểm tra.</p></div><span className={`admin-count-badge ${data.fallback_alerts.length ? "is-danger" : ""}`}>{data.fallback_alerts.length} cảnh báo</span></div>
          {data.fallback_alerts.length === 0 ? <div className="admin-empty compact">Không có fallback cần can thiệp trong kỳ.</div> : <div className="fallback-list">{data.fallback_alerts.map((alert) => <article className={`fallback-row fallback-row--${alert.severity}`} key={alert.message_id}><AlertIcon size={18} /><div><strong>{alert.customer_question ?? `Phiên #${alert.session_id ?? "—"}`}</strong><span>{alert.failure_mode ?? "low_confidence"} · score {alert.verifier_score.toFixed(2)} · {parseServerDate(alert.created_at).toLocaleString("vi-VN")}</span></div><Link className="btn btn-sm btn-outline" to="/sales#sessions">Điều phối Sale</Link></article>)}</div>}
        </section>

        <div className="admin-two-column admin-two-column--wide-left">
          <section className="admin-panel">
            <div className="admin-panel-head"><div><h2>Audit Trace Visualizer</h2><p>Prompt → Retrieval → Tool Call → Response, không lưu nội dung prompt.</p></div><TerminalIcon size={20} /></div>
            <div className="trace-layout"><div className="trace-list">{data.traces.length === 0 ? <span className="admin-empty compact">Chưa có trace.</span> : data.traces.map((trace) => <button type="button" key={trace.run_id} className={selectedTrace?.run_id === trace.run_id ? "is-active" : ""} onClick={() => setSelectedTrace(trace)}><code>{trace.run_id}</code><span>{parseServerDate(trace.started_at).toLocaleTimeString("vi-VN")} · {Math.round(trace.duration_ms)} ms</span></button>)}</div><TraceTimeline trace={selectedTrace} /></div>
          </section>
          <section className="admin-panel"><div className="admin-panel-head"><div><h2>Most Used Modules</h2><p>Tần suất audit event theo module.</p></div></div><HorizontalBars rows={data.most_used_modules.map((item) => ({ label: item.module, count: item.calls }))} /></section>
        </div>

        <section className="admin-panel">
          <div className="admin-panel-head"><div><h2>Log Stream</h2><p>Business audit log có thể lọc theo severity và module.</p></div><div className="log-filters"><select value={severity} onChange={(event) => setSeverity(event.target.value)}><option value="ALL">Mọi severity</option><option>INFO</option><option>WARN</option><option>ERROR</option></select><select value={module} onChange={(event) => setModule(event.target.value)}><option value="ALL">Mọi module</option>{modules.map((value) => <option key={value}>{value}</option>)}</select></div></div>
          <div className="log-stream">{filteredLogs.length === 0 ? <div className="admin-empty compact">Không có log khớp bộ lọc.</div> : filteredLogs.map((log) => <div className="log-row" key={log.id}><time>{parseServerDate(log.timestamp).toLocaleString("vi-VN")}</time><span className={`log-level log-level--${log.severity.toLowerCase()}`}>{log.severity}</span><code>{log.module}</code><strong>{log.event}</strong><span>{log.username ?? "system"}</span><code>{log.request_id?.slice(0, 8) ?? "—"}</code></div>)}</div>
        </section>

        <section className="admin-panel"><div className="admin-panel-head"><div><h2>Interactive API Tester</h2><p>Gọi nhanh RAG/Chat/Lead routing bằng token Admin hiện tại.</p></div><ApiIcon size={20} /></div><ApiTester /></section>
      </>}
      <SwaggerConsoleModal open={swaggerOpen} onClose={() => setSwaggerOpen(false)} />
    </div>
  );
}
