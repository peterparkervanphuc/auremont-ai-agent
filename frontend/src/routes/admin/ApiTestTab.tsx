const API_BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000/api/v1";
const SWAGGER_URL = `${API_BASE_URL.replace(/\/api\/v1\/?$/, "")}/docs`;

// Nhúng Swagger UI có sẵn của FastAPI (/docs) để gọi thử endpoint trực tiếp.
export function ApiTestTab() {
  return (
    <div style={{ height: "100%", display: "flex", flexDirection: "column" }}>
      <div style={{ padding: "28px 32px 0" }}>
        <h2 className="page-title">Kiểm tra API</h2>
        <p className="page-sub" style={{ marginBottom: 16 }}>
          Swagger UI của backend — gọi thử trực tiếp các endpoint.{" "}
          <a href={SWAGGER_URL} target="_blank" rel="noreferrer" style={{ color: "var(--accent)", fontWeight: 500 }}>
            Mở toàn màn hình ↗
          </a>
        </p>
      </div>
      <iframe
        src={SWAGGER_URL}
        title="Swagger UI"
        style={{ flex: 1, border: "none", width: "100%" }}
      />
    </div>
  );
}
