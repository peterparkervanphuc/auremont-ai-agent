import { useEffect, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useTheme } from "../context/ThemeContext";
import { useAuth } from "../hooks/useAuth";
import { fetchCategories } from "../api/projects";
import type { CategorySummary } from "../types/project";
import { UPCOMING_PHASES } from "../types/project";
import type { UserRole } from "../types";
import {
  AlertIcon,
  AuremontLogoIcon,
  ChartIcon,
  ChatIcon,
  ChevronRightIcon,
  DocumentIcon,
  HomeIcon,
  LogOutIcon,
  MenuIcon,
  MoonIcon,
  SettingsIcon,
  ShieldCheckIcon,
  SunIcon,
  XIcon,
} from "./Icons";

interface AdminNavEntry {
  to: string;
  label: string;
  icon: (p: { size?: number }) => React.ReactElement;
  roles: UserRole[];
  end?: boolean;
}

// ADMIN quản trị kho tài liệu + giám sát chất lượng AI, không có bảng hàng riêng.
const ADMIN_NAV: AdminNavEntry[] = [
  { to: "/documents", label: "Kho tài liệu", icon: DocumentIcon, roles: ["admin"] },
  { to: "/eval", label: "Chất lượng trả lời", icon: ChartIcon, roles: ["admin"] },
  { to: "/conflicts", label: "Cảnh báo mâu thuẫn", icon: AlertIcon, roles: ["admin"] },
  { to: "/settings", label: "Cài đặt chung", icon: SettingsIcon, roles: ["admin"] },
];

function typeSlug(index: number) {
  return `type-${index}`;
}

export function TopNavbar() {
  const { theme, toggleTheme } = useTheme();
  const { role, username, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [categories, setCategories] = useState<CategorySummary[]>([]);
  const [openDropdown, setOpenDropdown] = useState<string | null>(null);

  // Trang chủ Sale có ảnh hero — menu nổi trong suốt lên trên thay vì tách rời.
  const isOverlay = role === "sale" && location.pathname === "/home";

  // Dropdown hiện qua hover (mouse enter/leave), không phải :hover CSS thuần —
  // vì con trỏ chuột vẫn nằm nguyên vị trí sau khi bấm điều hướng (SPA không
  // load lại trang), :hover CSS sẽ giữ dropdown mở đè lên nội dung trang mới.
  // Reset theo route để đóng hẳn dropdown mỗi khi chuyển trang.
  useEffect(() => {
    setOpenDropdown(null);
  }, [location.pathname]);

  useEffect(() => {
    if (role !== "sale") return;
    fetchCategories()
      .then(setCategories)
      .catch(() => setCategories([]));
  }, [role]);

  const handleLogout = () => {
    logout();
    setMobileOpen(false);
    navigate("/login", { replace: true });
  };

  return (
    <header className={`topnav ${isOverlay ? "topnav--overlay" : ""}`}>
      <NavLink to="/home" className="topnav-brand" onClick={() => setMobileOpen(false)}>
        <AuremontLogoIcon size={28} />
        <span>Auremont</span>
      </NavLink>

      <nav className="topnav-links">
        <NavLink to="/home" end className={({ isActive }) => `topnav-link ${isActive ? "topnav-link--active" : ""}`}>
          <HomeIcon size={16} />
          Trang chủ
        </NavLink>

        {role === "sale" && (
          <>
            {categories.map((c) => (
              <div
                key={c.slug}
                className="topnav-item"
                onMouseEnter={() => setOpenDropdown(c.slug)}
                onMouseLeave={() => setOpenDropdown(null)}
              >
                <NavLink
                  to={`/inventory/${c.slug}`}
                  onClick={(e) => {
                    setOpenDropdown(null);
                    e.currentTarget.blur();
                  }}
                  className={({ isActive }) => `topnav-link ${isActive ? "topnav-link--active" : ""}`}
                >
                  {c.name}
                  {c.typeNames.length > 0 && <ChevronRightIcon size={12} className="topnav-caret" />}
                </NavLink>
                {c.typeNames.length > 0 && (
                  <div className={`topnav-dropdown ${openDropdown === c.slug ? "topnav-dropdown--open" : ""}`}>
                    {c.typeNames.map((t, i) => (
                      <NavLink
                        key={t}
                        to={`/inventory/${c.slug}#${typeSlug(i)}`}
                        onClick={(e) => {
                          setOpenDropdown(null);
                          e.currentTarget.blur();
                        }}
                        className="topnav-dropdown-item"
                      >
                        {t}
                      </NavLink>
                    ))}
                  </div>
                )}
              </div>
            ))}

            {UPCOMING_PHASES.map((p) => (
              <span key={p.slug} className="topnav-link topnav-link--disabled" title="Đang cập nhật dữ liệu">
                {p.name}
              </span>
            ))}

            <NavLink to="/chat" className={({ isActive }) => `topnav-link ${isActive ? "topnav-link--active" : ""}`}>
              <ChatIcon size={16} />
              Chat
            </NavLink>
          </>
        )}

        {role === "admin" &&
          ADMIN_NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) => `topnav-link ${isActive ? "topnav-link--active" : ""}`}
            >
              <item.icon size={16} />
              {item.label}
            </NavLink>
          ))}
      </nav>

      <div className="topnav-right">
        <button
          className="topnav-util"
          type="button"
          onClick={toggleTheme}
          title={theme === "dark" ? "Chuyển sang giao diện sáng" : "Chuyển sang giao diện tối"}
        >
          {theme === "dark" ? <SunIcon size={15} /> : <MoonIcon size={15} />}
        </button>
        <div className="topnav-user">
          <div className="topnav-avatar" title={username ?? ""}>
            {username ? username.charAt(0).toUpperCase() : role === "admin" ? <ShieldCheckIcon size={14} /> : <ChatIcon size={14} />}
          </div>
          <div className="topnav-user-info">
            <span className="topnav-user-name">{username ?? "—"}</span>
            <span className="topnav-user-role">{role === "admin" ? "Admin" : "Sale"}</span>
          </div>
          <button className="topnav-logout" type="button" onClick={handleLogout} title="Đăng xuất">
            <LogOutIcon size={14} />
          </button>
        </div>

        <button
          className="topnav-mobile-toggle"
          type="button"
          onClick={() => setMobileOpen((v) => !v)}
          aria-label={mobileOpen ? "Đóng menu" : "Mở menu"}
        >
          {mobileOpen ? <XIcon size={20} /> : <MenuIcon size={20} />}
        </button>
      </div>

      {mobileOpen && (
        <div className="topnav-mobile-menu">
          <NavLink
            to="/home"
            end
            onClick={() => setMobileOpen(false)}
            className={({ isActive }) => `topnav-link ${isActive ? "topnav-link--active" : ""}`}
          >
            <HomeIcon size={16} />
            Trang chủ
          </NavLink>

          {role === "sale" && (
            <>
              {categories.map((c) => (
                <div key={c.slug} className="topnav-mobile-group">
                  <NavLink
                    to={`/inventory/${c.slug}`}
                    onClick={() => setMobileOpen(false)}
                    className={({ isActive }) => `topnav-link ${isActive ? "topnav-link--active" : ""}`}
                  >
                    {c.name}
                  </NavLink>
                  {c.typeNames.map((t, i) => (
                    <NavLink
                      key={t}
                      to={`/inventory/${c.slug}#${typeSlug(i)}`}
                      onClick={() => setMobileOpen(false)}
                      className={({ isActive }) =>
                        `topnav-link topnav-mobile-sublink ${isActive ? "topnav-link--active" : ""}`
                      }
                    >
                      {t}
                    </NavLink>
                  ))}
                </div>
              ))}
              {UPCOMING_PHASES.map((p) => (
                <span key={p.slug} className="topnav-link topnav-link--disabled">
                  {p.name} · sắp có
                </span>
              ))}
              <NavLink
                to="/chat"
                onClick={() => setMobileOpen(false)}
                className={({ isActive }) => `topnav-link ${isActive ? "topnav-link--active" : ""}`}
              >
                <ChatIcon size={16} />
                Chat
              </NavLink>
            </>
          )}

          {role === "admin" &&
            ADMIN_NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={() => setMobileOpen(false)}
                className={({ isActive }) => `topnav-link ${isActive ? "topnav-link--active" : ""}`}
              >
                <item.icon size={16} />
                {item.label}
              </NavLink>
            ))}

          <div className="topnav-mobile-sep" />
          <button className="topnav-link" type="button" onClick={toggleTheme}>
            {theme === "dark" ? <SunIcon size={16} /> : <MoonIcon size={16} />}
            {theme === "dark" ? "Giao diện sáng" : "Giao diện tối"}
          </button>
          <button className="topnav-link" type="button" onClick={handleLogout}>
            <LogOutIcon size={16} />
            Đăng xuất
          </button>
        </div>
      )}
    </header>
  );
}
