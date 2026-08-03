import { Link } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import {
  ArrowRightIcon,
  ChatIcon,
  DatabaseIcon,
  DocumentIcon,
  LayersIcon,
  SearchIcon,
  ShieldCheckIcon,
  SparklesIcon,
} from "../components/Icons";

const STATS = [
  { value: "4", label: "Tầng dữ liệu", icon: <DatabaseIcon size={18} /> },
  { value: "2.5F", label: "Model Gemini", icon: <SparklesIcon size={18} /> },
  { value: "REST", label: "Chuẩn API", icon: <LayersIcon size={18} /> },
  { value: "HITL", label: "Chặn cam kết sai", icon: <ShieldCheckIcon size={18} /> },
];

const FEATURES = [
  {
    title: "Tìm kiếm Vector Ngữ nghĩa",
    desc: "Qdrant lưu vector embedding của bảng giá, mặt bằng, chính sách bán hàng. Truy xuất đúng đoạn tài liệu liên quan nhất trong toàn bộ kho dự án.",
    iconClass: "fi-emerald",
    icon: <SearchIcon size={22} />,
  },
  {
    title: "Tra cứu Tồn kho Real-time",
    desc: "Agent gọi API tồn kho nội bộ qua Function Calling để lấy tình trạng căn theo thời gian thực, thay vì trả lời bằng dữ liệu cũ đã lưu.",
    iconClass: "fi-accent-2",
    icon: <LayersIcon size={22} />,
  },
  {
    title: "Tổng hợp Câu trả lời AI",
    desc: "Gemini 2.5 Flash nhận ngữ cảnh từ tài liệu đã ingest và tổng hợp câu trả lời kèm trích dẫn nguồn tới đúng tài liệu gốc.",
    iconClass: "fi-accent",
    icon: <SparklesIcon size={22} />,
  },
  {
    title: "Verifier Agent & HITL",
    desc: "Agent độc lập chấm điểm Faithfulness/Relevancy. Câu trả lời liên quan giá hoặc cam kết bắt buộc Sale xác nhận trước khi gửi khách.",
    iconClass: "fi-cyan",
    icon: <ShieldCheckIcon size={22} />,
  },
];

export function Home() {
  const { role, username } = useAuth();

  const actions =
    role === "admin"
      ? [
          {
            to: "/chat",
            icon: <ChatIcon size={22} />,
            title: "Chat với SalesMate AI",
            desc: "Hỏi về bảng giá, mặt bằng và tồn kho",
          },
          {
            to: "/documents",
            icon: <DocumentIcon size={22} />,
            title: "Kho tài liệu",
            desc: "Tải lên và quản lý tài liệu dự án",
          },
        ]
      : [
          {
            to: "/chat",
            icon: <ChatIcon size={22} />,
            title: "Chat với SalesMate AI",
            desc: "Hỏi về bảng giá, mặt bằng và tồn kho",
          },
        ];

  return (
    <div className="home home-compact">
      <section className="hero home-hero">
        <div className="hero-orbs">
          <div className="hero-orb hero-orb-1" />
          <div className="hero-orb hero-orb-2" />
        </div>
        <div className="hero-grid" />

        <div className="container hero-inner">
          <div className="hero-badge">
            <span className="hero-badge-dot" />
            RAG Multi-Agent · Bất động sản
          </div>

          <h1 className="hero-title">
            Trợ lý Tư vấn
            <br />
            <span className="gradient-text">cho Đội Sale</span>
          </h1>

          <p className="hero-subtitle">
            Chào {username ?? "bạn"}, SalesMate kết hợp tìm kiếm vector ngữ nghĩa, tra cứu tồn kho real-time và Gemini AI
            để đưa ra câu trả lời chính xác, luôn kèm trích dẫn từ kho tài liệu dự án.
          </p>

          <div className="hero-nav-cards home-action-grid">
            {actions.map((a) => (
              <Link key={a.to} to={a.to} className="hero-nav-card">
                <div className="hero-nav-card-icon">{a.icon}</div>
                <div>
                  <p className="hero-nav-card-title">{a.title}</p>
                  <p className="hero-nav-card-desc">{a.desc}</p>
                </div>
                <ArrowRightIcon size={16} className="hero-nav-card-arrow" />
              </Link>
            ))}
          </div>
        </div>
      </section>

      <section className="home-summary">
        <div className="container home-summary-inner">
          <div className="home-stats-row">
            {STATS.map((s) => (
              <div key={s.label} className="home-stat-pill">
                <span className="home-stat-icon">{s.icon}</span>
                <strong>{s.value}</strong>
                <span>{s.label}</span>
              </div>
            ))}
          </div>

          <div className="home-feature-panel">
            <div className="home-feature-head">
              <p className="section-eyebrow">Cách hoạt động</p>
              <h2 className="section-title">Bốn tầng xử lý thông minh</h2>
              <p className="section-subtitle">
                SalesMate vượt xa tìm kiếm từ khóa — hệ thống hiểu ngữ cảnh tài liệu, đối chiếu tồn kho thực tế và tự
                kiểm chứng câu trả lời trước khi đưa tới Sale.
              </p>
            </div>

            <div className="home-feature-grid">
              {FEATURES.map((f) => (
                <article key={f.title} className="home-feature-item">
                  <div className={`feature-icon-wrap ${f.iconClass}`}>{f.icon}</div>
                  <div>
                    <h3 className="feature-title">{f.title}</h3>
                    <p className="feature-desc">{f.desc}</p>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
