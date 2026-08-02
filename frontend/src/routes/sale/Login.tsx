import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../api/client";
import { useAuth } from "../../hooks/useAuth";
import type { UserRole } from "../../types";

interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

function decodeRoleFromToken(accessToken: string): UserRole {
  // backend/core/security.py create_access_token embeds {"role":...} in the JWT payload.
  const payload = JSON.parse(atob(accessToken.split(".")[1])) as { role: UserRole };
  return payload.role;
}

const STATS = [
  { value: "4", label: "Tầng dữ liệu", icon: "database" },
  { value: "2.5F", label: "Model Gemini", icon: "sparkle" },
  { value: "REST", label: "Chuẩn API", icon: "layers" },
  { value: "HITL", label: "Chặn cam kết", icon: "shield" },
] as const;

const FEATURES = [
  {
    title: "Tìm kiếm Vector Ngữ nghĩa",
    body: "Tìm kiếm vector bằng Qdrant với embedding của Gemini. Truy xuất đúng đoạn bảng giá, chính sách, tiện ích liên quan nhất trong toàn bộ kho tài liệu dự án.",
    icon: "search",
  },
  {
    title: "Tra cứu Tồn kho Real-time",
    body: "Agent gọi API tồn kho nội bộ của công ty để lấy tình trạng căn theo thời gian thực, thay vì trả lời dựa trên dữ liệu cũ đã lưu.",
    icon: "layers",
  },
  {
    title: "Tổng hợp Câu trả lời AI",
    body: "Gemini 2.5 Flash nhận ngữ cảnh từ tài liệu đã ingest, tổng hợp câu trả lời kèm trích dẫn nguồn tới đúng tài liệu gốc.",
    icon: "sparkle",
  },
  {
    title: "Verifier Agent & HITL",
    body: "Agent độc lập chấm điểm Faithfulness/Relevancy. Câu trả lời liên quan giá và cam kết bắt buộc Sale xác nhận trước khi gửi khách.",
    icon: "shield",
  },
] as const;

type IconName =
  | "database"
  | "sparkle"
  | "layers"
  | "shield"
  | "search"
  | "login"
  | "home"
  | "eye"
  | "eyeOff"
  | "loader";

function Icon({ name }: { name: IconName }) {
  const p = {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    style: { width: "100%", height: "100%" },
  };
  switch (name) {
    case "database":
      return (
        <svg {...p}>
          <ellipse cx="12" cy="5" rx="9" ry="3" />
          <path d="M3 5v14c0 1.7 4 3 9 3s9-1.3 9-3V5" />
          <path d="M3 12c0 1.7 4 3 9 3s9-1.3 9-3" />
        </svg>
      );
    case "sparkle":
      return (
        <svg {...p}>
          <path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9z" />
          <path d="M18 15l.9 2.1L21 18l-2.1.9L18 21l-.9-2.1L15 18l2.1-.9z" />
        </svg>
      );
    case "layers":
      return (
        <svg {...p}>
          <polygon points="12 2 22 8.5 12 15 2 8.5 12 2" />
          <polyline points="2 15.5 12 22 22 15.5" />
        </svg>
      );
    case "shield":
      return (
        <svg {...p}>
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
          <polyline points="9 12 11 14 15 10" />
        </svg>
      );
    case "search":
      return (
        <svg {...p}>
          <circle cx="11" cy="11" r="7" />
          <line x1="21" y1="21" x2="16.7" y2="16.7" />
        </svg>
      );
    case "login":
      return (
        <svg {...p}>
          <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4" />
          <polyline points="10 17 15 12 10 7" />
          <line x1="15" y1="12" x2="3" y2="12" />
        </svg>
      );
    case "home":
      return (
        <svg {...p}>
          <path d="M3 10.5 12 3l9 7.5" />
          <path d="M5 9.5V20h14V9.5" />
        </svg>
      );
    case "eye":
      return (
        <svg {...p}>
          <path d="M1.5 12S5 5.5 12 5.5 22.5 12 22.5 12 19 18.5 12 18.5 1.5 12 1.5 12z" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      );
    case "eyeOff":
      return (
        <svg {...p}>
          <path d="M9.9 5.7A9.9 9.9 0 0 1 12 5.5c7 0 10.5 6.5 10.5 6.5a17 17 0 0 1-3.4 4.2M6.2 6.9A16.7 16.7 0 0 0 1.5 12S5 18.5 12 18.5c1.9 0 3.5-.5 4.9-1.2" />
          <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" />
          <line x1="2" y1="2" x2="22" y2="22" />
        </svg>
      );
    case "loader":
      return (
        <svg {...p}>
          <path d="M12 3v3.5" />
          <path d="M12 17.5V21" opacity="0.35" />
          <path d="M5.6 5.6l2.5 2.5" opacity="0.6" />
          <path d="M15.9 15.9l2.5 2.5" opacity="0.25" />
          <path d="M3 12h3.5" opacity="0.8" />
          <path d="M17.5 12H21" opacity="0.3" />
          <path d="M5.6 18.4l2.5-2.5" opacity="0.45" />
          <path d="M15.9 8.1l2.5-2.5" opacity="0.2" />
        </svg>
      );
  }
}

// màn hình ĐĂNG NHẬP nội bộ chung, sau xác thực routing theo role (SALE / ADMIN).
export function Login() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const canSubmit = Boolean(username.trim() && password) && !loading;

  // POST /auth/login dùng OAuth2PasswordRequestForm nên phải gửi form-urlencoded, không phải JSON.
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    setError(null);
    setLoading(true);
    try {
      const body = new URLSearchParams({ username: username.trim(), password });
      const result = await api.postUrlEncoded<TokenResponse>("/auth/login", body);
      const role = decodeRoleFromToken(result.access_token);
      login(result.access_token, result.refresh_token, role);
      navigate(role === "admin" ? "/admin" : "/sale");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Đăng nhập thất bại");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={S.page}>
      {/* Orb trang trí — blur mềm, trôi chậm phía sau nội dung. */}
      <div style={S.orbLayer} aria-hidden>
        <div className="login-orb" style={S.orbA} />
        <div className="login-orb" style={{...S.orbB, animationDelay: "-8s" }} />
      </div>

      <aside className="login-sidebar" style={S.sidebar}>
        <div style={S.brand}>
          <div style={S.brandMark}>SM</div>
          <span style={S.brandName}>
            Sales<span style={{ color: "var(--accent)" }}>Mate</span>
          </span>
        </div>

        <nav style={S.sideNav}>
          <div className="login-side-item" style={{...S.sideItem,...S.sideItemActive }}>
            <span style={S.sideIcon}>
              <Icon name="home" />
            </span>
            Trang chủ
            <span style={S.sideDot} />
          </div>
        </nav>

        <button type="button" className="login-submit" style={S.sideLoginBtn} onClick={() => setShowForm(true)}>
          <span style={S.sideIcon}>
            <Icon name="login" />
          </span>
          Đăng nhập
        </button>
      </aside>

      <main style={S.main}>
        <div style={S.hero}>
          <span className="login-rise" style={{...S.pill, animationDelay: "0.02s" }}>
            <span style={S.pillDot} />
            RAG Multi-Agent · Bất động sản
          </span>

          <h1 className="login-rise" style={{...S.h1, animationDelay: "0.08s" }}>
            Trợ lý Tư vấn
            <br />
            <span style={S.h1Accent}>cho Đội Sale</span>
          </h1>

          <p className="login-rise" style={{...S.lead, animationDelay: "0.14s" }}>
            SalesMate kết hợp tìm kiếm vector ngữ nghĩa, tra cứu tồn kho real-time và Gemini AI để cung cấp câu trả lời
            chính xác, luôn có trích dẫn từ kho tài liệu dự án bất động sản.
          </p>

          {!showForm ? (
            <button
              type="button"
              className="login-rise login-lift login-cta"
              style={{...S.ctaCard, animationDelay: "0.2s" }}
              onClick={() => setShowForm(true)}
            >
              <span style={S.ctaIcon}>
                <Icon name="login" />
              </span>
              <span style={S.ctaText}>
                <span style={S.ctaTitle}>Đăng nhập để bắt đầu</span>
                <span style={S.ctaSub}>Truy cập nền tảng SalesMate đầy đủ</span>
              </span>
              <span className="login-cta-arrow" style={S.ctaArrow}>
                →
              </span>
            </button>
          ) : (
            <form onSubmit={handleSubmit} className="login-rise" style={S.form} noValidate>
              <div style={S.formHead}>
                <h2 style={S.formTitle}>Đăng nhập</h2>
                <p style={S.formSub}>Dùng tài khoản nội bộ Sale hoặc Admin</p>
              </div>

              <label style={S.label} htmlFor="username">
                Tên đăng nhập
                <input
                  id="username"
                  className="login-field"
                  style={S.input}
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="admin"
                  autoComplete="username"
                  autoFocus
                  disabled={loading}
                />
              </label>

              <label style={S.label} htmlFor="password">
                Mật khẩu
                <span style={S.pwdWrap}>
                  <input
                    id="password"
                    className="login-field"
                    style={{...S.input, paddingRight: 42 }}
                    type={showPwd ? "text" : "password"}
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    autoComplete="current-password"
                    disabled={loading}
                  />
                  <button
                    type="button"
                    className="login-eye"
                    style={S.eyeBtn}
                    onClick={() => setShowPwd((v) => !v)}
                    tabIndex={-1}
                    aria-label={showPwd ? "Ẩn mật khẩu" : "Hiện mật khẩu"}
                  >
                    <span style={{ width: 16, height: 16, display: "inline-flex" }}>
                      <Icon name={showPwd ? "eyeOff" : "eye"} />
                    </span>
                  </button>
                </span>
              </label>

              {error && <p style={S.error}>{error}</p>}

              <button
                type="submit"
                className="login-submit"
                style={{...S.submit,...(canSubmit ? null : S.submitDisabled) }}
                disabled={!canSubmit}
              >
                {loading ? (
                  <>
                    <span className="login-spin" style={S.btnIcon}>
                      <Icon name="loader" />
                    </span>
                    Đang đăng nhập...
                  </>
                ) : (
                  <>
                    Đăng nhập
                    <span style={S.btnIcon}>
                      <Icon name="login" />
                    </span>
                  </>
                )}
              </button>

              <p style={S.hint}>Hệ thống tự chuyển tới màn hình phù hợp theo vai trò tài khoản.</p>
            </form>
          )}

          <div className="login-stat-row login-rise" style={{...S.statRow, animationDelay: "0.26s" }}>
            {STATS.map((s) => (
              <div key={s.label} className="login-lift" style={S.statCard}>
                <span style={S.statIcon}>
                  <Icon name={s.icon} />
                </span>
                <span style={S.statValue}>{s.value}</span>
                <span style={S.statLabel}>{s.label}</span>
              </div>
            ))}
          </div>
        </div>

        <section className="login-rise" style={{...S.panel, animationDelay: "0.32s" }}>
          <span style={S.kicker}>Cách hoạt động</span>
          <h2 style={S.h2}>Bốn tầng xử lý thông minh</h2>
          <p style={S.panelLead}>
            SalesMate vượt xa tìm kiếm từ khóa — hệ thống hiểu ngữ cảnh tài liệu, đối chiếu tồn kho thực tế và tự kiểm
            chứng câu trả lời trước khi đưa tới Sale.
          </p>

          <div className="login-feature-grid" style={S.featureGrid}>
            {FEATURES.map((f) => (
              <article key={f.title} className="login-lift" style={S.featureCard}>
                <span style={S.featureIcon}>
                  <Icon name={f.icon} />
                </span>
                <h3 style={S.featureTitle}>{f.title}</h3>
                <p style={S.featureBody}>{f.body}</p>
              </article>
            ))}
          </div>
        </section>
      </main>
    </div>
  );
}

const S: Record<string, React.CSSProperties> = {
  page: { display: "flex", minHeight: "100svh", background: "var(--bg)", position: "relative", overflow: "hidden" },

  orbLayer: { position: "fixed", inset: 0, pointerEvents: "none", zIndex: 0 },
  orbA: {
    position: "absolute",
    top: -140,
    right: -110,
    width: 460,
    height: 460,
    borderRadius: "50%",
    background: "rgba(37, 99, 235, 0.14)",
    filter: "blur(90px)",
  },
  orbB: {
    position: "absolute",
    bottom: -160,
    left: 140,
    width: 440,
    height: 440,
    borderRadius: "50%",
    background: "rgba(59, 130, 246, 0.12)",
    filter: "blur(90px)",
  },

  sidebar: {
    position: "relative",
    zIndex: 1,
    width: 260,
    flexShrink: 0,
    background: "rgba(247, 249, 252, 0.82)",
    backdropFilter: "blur(10px)",
    borderRight: "1px solid var(--border)",
    display: "flex",
    flexDirection: "column",
    padding: "22px 14px",
  },
  brand: { display: "flex", alignItems: "center", gap: 10, padding: "0 8px", marginBottom: 26 },
  brandMark: {
    width: 32,
    height: 32,
    borderRadius: 9,
    background: "var(--accent)",
    color: "#fff",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontWeight: 700,
    fontSize: 13,
    letterSpacing: 0.3,
    boxShadow: "0 4px 10px rgba(37, 99, 235, 0.3)",
  },
  brandName: { fontWeight: 600, fontSize: 19, color: "var(--text-h)", letterSpacing: -0.2 },
  sideNav: { display: "flex", flexDirection: "column", gap: 2, flex: 1 },
  sideItem: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "10px 12px",
    borderRadius: 8,
    fontSize: 14,
    color: "var(--text)",
    cursor: "pointer",
  },
  sideItemActive: { background: "var(--accent-bg)", color: "var(--accent)", fontWeight: 600 },
  sideIcon: { width: 18, height: 18, flexShrink: 0, display: "inline-flex" },
  sideDot: { marginLeft: "auto", width: 6, height: 6, borderRadius: "50%", background: "var(--accent)" },
  sideLoginBtn: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "11px 14px",
    borderRadius: 10,
    border: "none",
    background: "var(--accent)",
    color: "#fff",
    fontSize: 14,
    fontWeight: 600,
    boxShadow: "0 4px 12px rgba(37, 99, 235, 0.25)",
  },

  main: { position: "relative", zIndex: 1, flex: 1, minWidth: 0, overflow: "auto", padding: "56px 32px 72px" },
  hero: { maxWidth: 880, margin: "0 auto", textAlign: "center" },
  pill: {
    display: "inline-flex",
    alignItems: "center",
    gap: 8,
    padding: "7px 16px",
    borderRadius: 999,
    background: "var(--accent-bg)",
    border: "1px solid var(--accent-border)",
    color: "var(--accent)",
    fontSize: 13,
    fontWeight: 600,
  },
  pillDot: { width: 7, height: 7, borderRadius: "50%", background: "var(--accent)" },
  h1: { fontSize: 58, lineHeight: 1.1, letterSpacing: -1.8, fontWeight: 700, margin: "26px 0 0", color: "var(--text-h)" },
  h1Accent: { color: "var(--accent)" },
  lead: { maxWidth: 660, margin: "22px auto 0", fontSize: 16, lineHeight: 1.7, color: "var(--text)" },

  ctaCard: {
    display: "inline-flex",
    alignItems: "center",
    gap: 16,
    margin: "34px auto 0",
    padding: "18px 24px",
    borderRadius: 14,
    border: "1px solid var(--border)",
    background: "rgba(255, 255, 255, 0.9)",
    backdropFilter: "blur(10px)",
    boxShadow: "var(--shadow)",
    textAlign: "left",
  },
  ctaIcon: {
    width: 40,
    height: 40,
    padding: 10,
    borderRadius: 10,
    background: "var(--accent-bg)",
    color: "var(--accent)",
    flexShrink: 0,
  },
  ctaText: { display: "flex", flexDirection: "column", gap: 3 },
  ctaTitle: { fontSize: 16, fontWeight: 600, color: "var(--text-h)" },
  ctaSub: { fontSize: 13.5, color: "var(--text-muted)" },
  ctaArrow: {
    marginLeft: 22,
    fontSize: 20,
    color: "var(--accent)",
    transition: "transform 0.22s cubic-bezier(0.22, 1, 0.36, 1)",
    display: "inline-block",
  },

  form: {
    maxWidth: 410,
    margin: "34px auto 0",
    padding: "34px 32px",
    borderRadius: 14,
    border: "1px solid var(--border)",
    background: "rgba(255, 255, 255, 0.92)",
    backdropFilter: "blur(12px)",
    boxShadow: "0 4px 6px rgba(15, 23, 42, 0.05), 0 12px 28px rgba(15, 23, 42, 0.08)",
    display: "flex",
    flexDirection: "column",
    gap: 18,
    textAlign: "left",
  },
  formHead: { display: "flex", flexDirection: "column", gap: 5 },
  formTitle: { fontSize: 27, fontWeight: 700, letterSpacing: -0.5, color: "var(--text-h)", margin: 0 },
  formSub: { fontSize: 13.5, color: "var(--text-muted)" },
  label: { display: "flex", flexDirection: "column", gap: 7, fontSize: 13.5, fontWeight: 500, color: "var(--text-h)" },
  input: {
    width: "100%",
    padding: "11px 13px",
    fontSize: 14,
    borderRadius: 7,
    border: "1px solid var(--border)",
    background: "var(--bg)",
    color: "var(--text-h)",
    outline: "none",
    boxSizing: "border-box",
  },
  pwdWrap: { position: "relative", display: "flex", alignItems: "center" },
  eyeBtn: {
    position: "absolute",
    right: 12,
    background: "none",
    border: "none",
    padding: 4,
    color: "var(--text-muted)",
    display: "flex",
    alignItems: "center",
  },
  error: {
    padding: "10px 12px",
    borderRadius: 6,
    background: "var(--danger-bg)",
    borderLeft: "3px solid var(--danger)",
    color: "var(--danger)",
    fontSize: 13.5,
  },
  submit: {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 8,
    padding: "12px 16px",
    borderRadius: 7,
    border: "none",
    background: "var(--accent)",
    color: "#fff",
    fontSize: 14.5,
    fontWeight: 600,
  },
  submitDisabled: { opacity: 0.5, cursor: "not-allowed" },
  btnIcon: { width: 15, height: 15, display: "inline-flex", flexShrink: 0 },
  hint: { fontSize: 12.5, color: "var(--text-muted)", textAlign: "center", lineHeight: 1.5 },

  statRow: { display: "grid", gridTemplateColumns: "repeat(4, minmax(0, 1fr))", gap: 14, margin: "44px auto 0" },
  statCard: {
    display: "flex",
    alignItems: "center",
    gap: 11,
    padding: "16px 18px",
    borderRadius: 12,
    border: "1px solid var(--border)",
    background: "rgba(255, 255, 255, 0.88)",
    backdropFilter: "blur(8px)",
    boxShadow: "var(--shadow)",
  },
  statIcon: {
    width: 34,
    height: 34,
    padding: 8,
    borderRadius: 9,
    background: "var(--accent-bg)",
    color: "var(--accent)",
    flexShrink: 0,
  },
  statValue: { fontSize: 17, fontWeight: 700, color: "var(--text-h)" },
  statLabel: { fontSize: 13, color: "var(--text-muted)", textAlign: "left", lineHeight: 1.35 },

  panel: {
    maxWidth: 1080,
    margin: "56px auto 0",
    padding: "38px 34px 34px",
    borderRadius: 18,
    border: "1px solid var(--border)",
    background: "rgba(248, 250, 252, 0.75)",
    backdropFilter: "blur(8px)",
  },
  kicker: { fontSize: 12.5, fontWeight: 700, letterSpacing: 1.1, textTransform: "uppercase", color: "var(--accent)" },
  h2: { fontSize: 34, fontWeight: 700, letterSpacing: -0.9, margin: "12px 0 0", color: "var(--text-h)" },
  panelLead: { maxWidth: 640, margin: "14px 0 0", fontSize: 15.5, lineHeight: 1.7, color: "var(--text)" },
  featureGrid: { display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: 16, marginTop: 30 },
  featureCard: { padding: 22, borderRadius: 13, border: "1px solid var(--border)", background: "var(--bg)" },
  featureIcon: {
    display: "inline-flex",
    width: 38,
    height: 38,
    padding: 9,
    borderRadius: 10,
    background: "var(--accent-bg)",
    color: "var(--accent)",
    marginBottom: 14,
  },
  featureTitle: { fontSize: 16.5, fontWeight: 600, color: "var(--text-h)", margin: 0, letterSpacing: -0.2 },
  featureBody: { marginTop: 9, fontSize: 14.2, lineHeight: 1.65, color: "var(--text)" },
};
