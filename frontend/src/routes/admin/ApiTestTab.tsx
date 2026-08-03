import { useState } from "react";
import { api } from "../../api/client";
import {
  CheckCircleIcon,
  ExternalLinkIcon,
  InfoIcon,
  LoaderIcon,
  PlayIcon,
  RefreshIcon,
  XCircleIcon,
} from "../../components/Icons";

const API_BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";
const ROOT_URL = API_BASE_URL.replace(/\/api\/v1\/?$/, "");
const SWAGGER_URL = `${ROOT_URL}/docs`;

interface Endpoint {
  method: string;
  path: string;
  desc: string;
  /** Endpoint chỉ để mở tab mới (Swagger UI), không gọi bằng fetch. */
  external?: boolean;
}

const ENDPOINTS: Endpoint[] = [
  { method: "GET", path: "/health", desc: 'Kiểm tra liveness — trả về {"status":"ok"}' },
  { method: "GET", path: "/documents", desc: "Danh sách tài liệu đã ingest vào kho tri thức" },
  { method: "GET", path: "/sale/sessions", desc: "Danh sách phiên tư vấn của Sale đang đăng nhập" },
  { method: "GET", path: "/admin/eval/scores", desc: "Điểm DeepEval — Faithfulness & Answer Relevancy" },
  { method: "GET", path: "/admin/conflicts", desc: "Danh sách flag mâu thuẫn giữa các tài liệu" },
  { method: "GET", path: "/docs", desc: "Swagger UI — tài liệu OpenAPI tương tác", external: true },
];

type Result = { ok: boolean; status: number | string; body: string; ms: number };

export function ApiTestTab() {
  const [results, setResults] = useState<Record<string, Result>>({});
  const [running, setRunning] = useState<string | null>(null);

  const test = async (ep: Endpoint) => {
    setRunning(ep.path);
    const started = performance.now();
    try {
      // /health nằm ngoài prefix /api/v1 nên gọi thẳng root.
      const data =
        ep.path === "/health"
          ? await fetch(`${ROOT_URL}/health`).then((r) => r.json())
          : await api.get<unknown>(ep.path);
      setResults((prev) => ({
        ...prev,
        [ep.path]: {
          ok: true,
          status: 200,
          body: JSON.stringify(data, null, 2),
          ms: Math.round(performance.now() - started),
        },
      }));
    } catch (err) {
      setResults((prev) => ({
        ...prev,
        [ep.path]: {
          ok: false,
          status: err instanceof Error && "status" in err ? (err as { status: number }).status : "ERR",
          body: err instanceof Error ? err.message : "Không gọi được endpoint",
          ms: Math.round(performance.now() - started),
        },
      }));
    } finally {
      setRunning(null);
    }
  };

  const runAll = async () => {
    for (const ep of ENDPOINTS.filter((e) => !e.external)) await test(ep);
  };

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h2 className="page-title">Kiểm tra API</h2>
          <p className="page-sub">
            Ping các endpoint backend SalesMate và xem phản hồi trực tiếp. Vite dev server proxy <code>/api/*</code> tới{" "}
            <code>localhost:8000</code>.
          </p>
        </div>
        <div className="docs-header-actions">
          <button className="btn btn-outline" onClick={() => setResults({})} type="button">
            <RefreshIcon size={15} />
            Đặt lại
          </button>
          <button className="btn btn-primary" onClick={runAll} type="button">
            <PlayIcon size={15} />
            Chạy tất cả
          </button>
        </div>
      </div>

      <div className="data-list">
        {ENDPOINTS.map((ep) => {
          const res = results[ep.path];
          const busy = running === ep.path;

          return (
            <div key={ep.path} className="card" style={{ padding: 0, overflow: "hidden" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 14, padding: "18px 20px" }}>
                <span className="badge">{ep.method}</span>
                <code style={{ fontSize: "0.875rem" }}>{ep.path}</code>

                <div style={{ marginLeft: "auto" }}>
                  {ep.external ? (
                    <a className="btn btn-sm btn-outline" href={SWAGGER_URL} target="_blank" rel="noreferrer">
                      <ExternalLinkIcon size={14} />
                      Mở
                    </a>
                  ) : (
                    <button className="btn btn-sm btn-outline" onClick={() => test(ep)} disabled={busy} type="button">
                      {busy ? <LoaderIcon size={14} className="icon-spin" /> : <PlayIcon size={14} />}
                      Test
                    </button>
                  )}
                </div>
              </div>

              <p className="page-sub" style={{ margin: 0, padding: "0 20px 18px" }}>
                {ep.desc}
              </p>

              {res && (
                <div style={{ borderTop: "1px solid var(--border)", padding: "14px 20px", background: "var(--bg-glass)" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
                    <span className={`badge ${res.ok ? "badge-success" : "badge-danger"}`}>
                      {res.ok ? <CheckCircleIcon size={12} /> : <XCircleIcon size={12} />}
                      {res.status}
                    </span>
                    <span className="conflict-doc-meta">{res.ms} ms</span>
                  </div>
                  <pre
                    style={{
                      margin: 0,
                      maxHeight: 220,
                      overflow: "auto",
                      fontFamily: "var(--font-mono)",
                      fontSize: "0.8125rem",
                      lineHeight: 1.6,
                      color: res.ok ? "var(--text-2)" : "var(--rose)",
                      whiteSpace: "pre-wrap",
                      wordBreak: "break-word",
                    }}
                  >
                    {res.body}
                  </pre>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="card" style={{ marginTop: 20, display: "flex", gap: 14 }}>
        <div className="data-row-icon">
          <InfoIcon size={18} />
        </div>
        <div>
          <h3 className="upload-zone-title">Backend không phản hồi?</h3>
          <p className="page-sub" style={{ marginTop: 6 }}>
            Khởi động FastAPI server từ thư mục <code>backend/</code>:
          </p>
          <pre
            style={{
              marginTop: 10,
              padding: "12px 16px",
              borderRadius: "var(--radius-sm)",
              background: "#0a0e1a",
              color: "var(--emerald)",
              fontFamily: "var(--font-mono)",
              fontSize: "0.8125rem",
              overflowX: "auto",
            }}
          >
            $ uvicorn app.main:app --reload --port 8000
          </pre>
          <p className="page-sub" style={{ marginTop: 12 }}>
            Hoặc khởi động toàn bộ stack với Docker:
          </p>
          <pre
            style={{
              marginTop: 10,
              padding: "12px 16px",
              borderRadius: "var(--radius-sm)",
              background: "#0a0e1a",
              color: "var(--emerald)",
              fontFamily: "var(--font-mono)",
              fontSize: "0.8125rem",
              overflowX: "auto",
            }}
          >
            $ docker compose up -d --build
          </pre>
        </div>
      </div>
    </div>
  );
}
