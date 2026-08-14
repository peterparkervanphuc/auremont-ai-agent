import { NavLink, useNavigate } from "react-router-dom";
import { useTheme } from "../context/ThemeContext";
import { useAuth } from "../hooks/useAuth";
import type { UserRole } from "../types";
import {
  AlertIcon,
  ApiIcon,
  AuremontLogoIcon,
  ChartIcon,
  ChatIcon,
  ChevronLeftIcon,
  ClipboardListIcon,
  DocumentIcon,
  GlobeIcon,
  HomeIcon,
  LogOutIcon,
  MenuIcon,
  MoonIcon,
  SettingsIcon,
  ScaleIcon,
  SunIcon,
  XIcon,
} from "./Icons";

interface Props {
  collapsed: boolean;
  onToggleCollapse: () => void;
  mobileOpen: boolean;
  onMobileClose: () => void;
  onMobileOpen: () => void;
}

interface NavEntry {
  to: string;
  label: string;
  icon: (p: { size?: number }) => React.ReactElement;
  roles: UserRole[];
  end?: boolean;
}

// Sidebar theo đúng 2 luồng trong CLAUDE.md: SALE dùng Chat, ADMIN quản trị kho + giám sát.
const NAV: NavEntry[] = [
  { to: "/home", label: "Trang chủ", icon: HomeIcon, roles: ["sale", "admin"], end: true },
  { to: "/chat", label: "Chat", icon: ChatIcon, roles: ["sale", "admin"] },
  { to: "/documents", label: "Kho tài liệu", icon: DocumentIcon, roles: ["admin"] },
  { to: "/document-review", label: "Chờ duyệt tài liệu", icon: ClipboardListIcon, roles: ["admin"] },
  { to: "/document-relations", label: "Quan hệ tài liệu", icon: ScaleIcon, roles: ["admin"] },
  { to: "/eval", label: "Đánh giá AI", icon: ChartIcon, roles: ["admin"] },
  { to: "/conflicts", label: "Cảnh báo mâu thuẫn", icon: AlertIcon, roles: ["admin"] },
  { to: "/api-test", label: "Kiểm tra API", icon: ApiIcon, roles: ["admin"] },
  { to: "/settings", label: "Cài đặt chung", icon: SettingsIcon, roles: ["admin"] },
];

function initials(name: string) {
  return name.slice(0, 2).toUpperCase();
}

export function AppSidebar({ collapsed, onToggleCollapse, mobileOpen, onMobileClose, onMobileOpen }: Props) {
  const { theme, toggleTheme } = useTheme();
  const { role, username, logout } = useAuth();
  const navigate = useNavigate();

  const items = NAV.filter((n) => (role ? n.roles.includes(role) : false));

  const handleLogout = () => {
    logout();
    onMobileClose();
    navigate("/login", { replace: true });
  };

  function NavLinks({ labels }: { labels: boolean }) {
    return (
      <nav className="sb-nav">
        {items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            onClick={onMobileClose}
            title={!labels ? item.label : undefined}
            className={({ isActive }) => `sb-link ${isActive ? "sb-link--active" : ""}`}
          >
            {({ isActive }) => (
              <>
                <span className="sb-link-icon">
                  <item.icon size={18} />
                </span>
                {labels && <span className="sb-link-text">{item.label}</span>}
                {isActive && labels && <span className="sb-link-dot" />}
              </>
            )}
          </NavLink>
        ))}
      </nav>
    );
  }

  function BottomUtils({ labels }: { labels: boolean }) {
    return (
      <>
        <div className="sb-utils">
          <button className="sb-util" type="button" title="Ngôn ngữ: Tiếng Việt">
            <GlobeIcon size={16} />
            {labels && <span>VI</span>}
          </button>
          <button
            className="sb-util"
            type="button"
            onClick={toggleTheme}
            title={theme === "dark" ? "Chuyển sang giao diện sáng" : "Chuyển sang giao diện tối"}
          >
            {theme === "dark" ? <SunIcon size={16} /> : <MoonIcon size={16} />}
            {labels && <span>{theme === "dark" ? "Light" : "Dark"}</span>}
          </button>
        </div>

        <div className="sb-footer">
          <div className="sb-sep" />
          <div className={`sb-user ${!labels ? "sb-user--icon" : ""}`}>
            <div className="sb-avatar" title={username ?? ""}>
              {initials(username ?? "SM")}
            </div>
            {labels && (
              <div className="sb-user-info">
                <span className="sb-user-name">{username ?? "—"}</span>
                <span className="sb-user-role">{role === "admin" ? "Admin" : "Sale"}</span>
              </div>
            )}
            <button className="sb-logout" type="button" onClick={handleLogout} title="Đăng xuất">
              <LogOutIcon size={15} />
            </button>
          </div>
        </div>
      </>
    );
  }

  const brand = (
    <>
      <AuremontLogoIcon size={28} />
      <span className="sb-brand-text">
        Sales<span className="sb-brand-accent">Mate</span>
      </span>
    </>
  );

  return (
    <>
      {/* ── Topbar mobile ── */}
      <header className="sb-topbar">
        <button className="sb-hamburger" onClick={onMobileOpen} aria-label="Mở menu" type="button">
          <MenuIcon size={20} />
        </button>
        <div className="sb-brand">{brand}</div>
      </header>

      {/* ── Sidebar desktop ── */}
      <aside className={`app-sidebar ${collapsed ? "app-sidebar--sm" : ""}`}>
        {collapsed ? (
          <div className="sb-head sb-head--collapsed">
            <button className="sb-toggle" onClick={onToggleCollapse} title="Mở rộng sidebar" type="button">
              <ChevronLeftIcon size={15} className="sb-toggle--flipped" />
            </button>
          </div>
        ) : (
          <div className="sb-head">
            <div className="sb-brand">{brand}</div>
            <button className="sb-toggle" onClick={onToggleCollapse} title="Thu gọn sidebar" type="button">
              <ChevronLeftIcon size={14} />
            </button>
          </div>
        )}

        <NavLinks labels={!collapsed} />
        <div className="sb-grow" />
        <BottomUtils labels={!collapsed} />
      </aside>

      {/* ── Overlay + drawer mobile ── */}
      {mobileOpen && <div className="sb-overlay" onClick={onMobileClose} />}

      <aside className={`app-sidebar app-sidebar--drawer ${mobileOpen ? "app-sidebar--open" : ""}`}>
        <div className="sb-head sb-head--mobile">
          <div className="sb-brand">{brand}</div>
          <button className="sb-hamburger" onClick={onMobileClose} aria-label="Đóng menu" type="button">
            <XIcon size={20} />
          </button>
        </div>
        <NavLinks labels />
        <div className="sb-grow" />
        <BottomUtils labels />
      </aside>
    </>
  );
}
