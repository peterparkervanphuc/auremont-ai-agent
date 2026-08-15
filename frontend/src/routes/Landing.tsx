import { Link, Navigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { AuremontLogoIcon, LogInIcon } from "../components/Icons";

const HERO_IMAGE_URL =
  "https://pub-2b6dd93e8e8948099737838a9bf56770.r2.dev/vinhomes-ocean-park/masteri-grand-coast-bg-homepage.jpg";

// First public screen before login — branding and an entry button only,
// so internal lookup/chat content is never exposed to unauthenticated visitors.
export function Landing() {
  const { isAuthenticated } = useAuth();
  if (isAuthenticated) return <Navigate to="/home" replace />;

  return (
    <div className="landing-page" style={{ "--hero-image-url": `url(${HERO_IMAGE_URL})` } as React.CSSProperties}>
      <div className="landing-scrim" />
      <div className="landing-content">
        <div className="landing-logo">
          <AuremontLogoIcon size={40} />
          <span className="logo-text">Auremont</span>
        </div>
        <h1 className="landing-title">Trợ lý AI nội bộ cho đội ngũ Sale Vinhomes Ocean Park</h1>
        <p className="landing-subtitle">
          Tra cứu bảng giá, tồn kho và tư vấn khách hàng nhanh hơn với AI có trích dẫn nguồn tài liệu.
        </p>
        <Link to="/login" className="btn btn-primary landing-cta">
          Đăng nhập
          <LogInIcon size={16} />
        </Link>
      </div>
    </div>
  );
}
