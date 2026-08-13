import { useEffect, useState } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { useTheme } from "../context/ThemeContext";
import { useAuth } from "../hooks/useAuth";
import { CATALOG } from "../types/catalog";
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

// Ocean Park 1 la khu do thi duy nhat da co du lieu — cac loai hinh (Chung cu/Biet
// thu/Shop TMDV) cua no len thanh menu chinh, dropdown la danh sach phan khu that
// theo dung menu web mau (khong con chia theo Studio/1PN/2PN nhu truoc).
const OCEAN_PARK_1 = CATALOG[0];
const OTHER_OCEAN_PARKS = CATALOG.slice(1);

// Cac nhom (Chung cu VA Biet thu) da co san section rieng ngay trong trang
// /inventory/<category-slug> (xem CategoryDetailPage) — bam vao thi cuon toi
// thang section do (neo id trung slug) thay vi mo trang /inventory/group/* rieng.
const ANCHOR_GROUP_SLUGS = new Set([
  "lumiere-orient-pearl",
  "the-metropolitan",
  "the-ocean-view",
  "the-sapphire",
  "the-senique-hanoi",
  "tieu-khu-ngoc-trai",
  "tieu-khu-hai-au",
  "tieu-khu-sao-bien",
  "shop-sh09",
  "shop-sb11a",
  "shop-ha08",
  "shop-bh9b",
]);

// Slug nhom nay thuoc category nao — vi ANCHOR_GROUP_SLUGS dung chung cho ca
// Chung cu lan Biet thu, can biet dung /inventory/<slug-nay> de ghep href.
const ANCHOR_GROUP_CATEGORY: Record<string, string> = {
  "lumiere-orient-pearl": "chung-cu",
  "the-metropolitan": "chung-cu",
  "the-ocean-view": "chung-cu",
  "the-sapphire": "chung-cu",
  "the-senique-hanoi": "chung-cu",
  "tieu-khu-ngoc-trai": "biet-thu",
  "tieu-khu-hai-au": "biet-thu",
  "tieu-khu-sao-bien": "biet-thu",
  "shop-sh09": "shophouse",
  "shop-sb11a": "shophouse",
  "shop-ha08": "shophouse",
  "shop-bh9b": "shophouse",
};

// The Senique Hanoi khong co san "sub-project" that trong catalog (chi 1
// project gop chung, khong tach S1/S2 trong DB nhu Metropolitan) — nhung UI
// van can flyout 2 muc con nhu anh mau, tro toi 2 neo id lam thu cong trong
// CategoryDetailPage (#the-senique-1, #the-senique-2).
const ANCHOR_SUBSECTIONS: Record<string, { label: string; anchorId: string }[]> = {
  "the-senique-hanoi": [
    { label: "Tòa The Senique 1", anchorId: "the-senique-1" },
    { label: "Tòa The Senique 2", anchorId: "the-senique-2" },
  ],
};

export function TopNavbar() {
  const { theme, toggleTheme } = useTheme();
  const { role, username, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [openDropdown, setOpenDropdown] = useState<string | null>(null);

  // Trang chủ va cac trang co hero banner (chi tiet loai hinh, chi tiet du an) —
  // menu noi trong suot len tren anh thay vi tach roi. Tru rieng /inventory/group/*
  // vi trang do khong co banner, menu trong suot se de tren nen trang bi mat chu.
  const isOverlay =
    role === "sale" &&
    (location.pathname === "/home" ||
      (location.pathname.startsWith("/inventory/") && !location.pathname.startsWith("/inventory/group/")));

  // Dropdown hiện qua hover (mouse enter/leave), không phải :hover CSS thuần —
  // vì con trỏ chuột vẫn nằm nguyên vị trí sau khi bấm điều hướng (SPA không
  // load lại trang), :hover CSS sẽ giữ dropdown mở đè lên nội dung trang mới.
  // Reset theo route để đóng hẳn dropdown mỗi khi chuyển trang.
  useEffect(() => {
    setOpenDropdown(null);
  }, [location.pathname]);

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
            {OCEAN_PARK_1.categories.map((c) => (
              <div
                key={c.slug}
                className="topnav-item"
                onMouseEnter={() => setOpenDropdown(c.slug)}
                onMouseLeave={() => setOpenDropdown(null)}
              >
                {/* Moi loai hinh gio co URL rieng (/inventory/chung-cu, /inventory/biet-thu...)
                    nen isActive tinh dung, khong con bi tren xanh ca 3 cung luc nhu truoc. */}
                <NavLink
                  to={`/inventory/${c.slug}`}
                  onClick={(e) => {
                    setOpenDropdown(null);
                    e.currentTarget.blur();
                  }}
                  className={({ isActive }) => `topnav-link ${isActive ? "topnav-link--active" : ""}`}
                >
                  {c.name}
                  {c.groups.length > 0 && <ChevronRightIcon size={12} className="topnav-caret" />}
                </NavLink>
                {c.groups.length > 0 && (
                  <div className={`topnav-dropdown ${openDropdown === c.slug ? "topnav-dropdown--open" : ""}`}>
                    {c.groups.map((g) => {
                      const isAnchorGroup = ANCHOR_GROUP_SLUGS.has(g.slug);
                      const anchorCategorySlug = ANCHOR_GROUP_CATEGORY[g.slug] ?? c.slug;
                      const subsections = isAnchorGroup ? ANCHOR_SUBSECTIONS[g.slug] : undefined;

                      if (subsections) {
                        // Flyout thu cong (khong lay tu g.projects vi day khong phai
                        // sub-project that trong DB — chi la neo cuon trong cung 1 trang).
                        return (
                          <div key={g.slug} className="topnav-subitem">
                            <NavLink
                              to={`/inventory/${anchorCategorySlug}#${g.slug}`}
                              onClick={(e) => {
                                setOpenDropdown(null);
                                e.currentTarget.blur();
                              }}
                              className="topnav-dropdown-item"
                            >
                              {g.name}
                            </NavLink>
                            <div className="topnav-submenu">
                              {subsections.map((s) => (
                                <NavLink
                                  key={s.anchorId}
                                  to={`/inventory/${anchorCategorySlug}#${s.anchorId}`}
                                  onClick={(e) => {
                                    setOpenDropdown(null);
                                    e.currentTarget.blur();
                                  }}
                                  className="topnav-dropdown-item"
                                >
                                  {s.label}
                                </NavLink>
                              ))}
                            </div>
                          </div>
                        );
                      }

                      if (isAnchorGroup && g.projects.length > 1) {
                        // Nhom co nhieu du an con VA da co section rieng trong trang (vd "The
                        // Metropolitan" -> Zurich/Beverly/London/Paris) — flyout hover nhu cu,
                        // nhung tung du an con cuon toi dung section thay vi mo trang rieng.
                        return (
                          <div key={g.slug} className="topnav-subitem">
                            <NavLink
                              to={`/inventory/${anchorCategorySlug}#${g.slug}`}
                              onClick={(e) => {
                                setOpenDropdown(null);
                                e.currentTarget.blur();
                              }}
                              className="topnav-dropdown-item"
                            >
                              {g.name}
                            </NavLink>
                            <div className="topnav-submenu">
                              {g.projects.map((p) =>
                                p.projectId ? (
                                  <NavLink
                                    key={p.projectId}
                                    to={`/inventory/${anchorCategorySlug}#${p.projectId}`}
                                    onClick={(e) => {
                                      setOpenDropdown(null);
                                      e.currentTarget.blur();
                                    }}
                                    className="topnav-dropdown-item"
                                  >
                                    {p.name}
                                  </NavLink>
                                ) : (
                                  <span key={p.name} className="topnav-dropdown-item topnav-link--disabled">
                                    {p.name}
                                  </span>
                                )
                              )}
                            </div>
                          </div>
                        );
                      }

                      if (isAnchorGroup) {
                        // Da co section rieng trong trang — cuon toi thay vi mo trang khac.
                        return (
                          <NavLink
                            key={g.slug}
                            to={`/inventory/${anchorCategorySlug}#${g.slug}`}
                            onClick={(e) => {
                              setOpenDropdown(null);
                              e.currentTarget.blur();
                            }}
                            className="topnav-dropdown-item"
                          >
                            {g.name}
                          </NavLink>
                        );
                      }

                      return g.projects.length > 1 ? (
                        // Nhom co nhieu du an con nhung CHUA co section rieng trong trang -> mo
                        // flyout thu 2 khi hover, giong menu web mau; bam thang vao ten nhom van
                        // vao duoc trang liet ke ca nhom.
                        <div key={g.slug} className="topnav-subitem">
                          <NavLink
                            to={`/inventory/group/${g.slug}`}
                            onClick={(e) => {
                              setOpenDropdown(null);
                              e.currentTarget.blur();
                            }}
                            className="topnav-dropdown-item"
                          >
                            {g.name}
                          </NavLink>
                          <div className="topnav-submenu">
                            {g.projects.map((p) =>
                              p.projectId ? (
                                <NavLink
                                  key={p.projectId}
                                  to={`/inventory/project/${p.projectId}`}
                                  onClick={(e) => {
                                    setOpenDropdown(null);
                                    e.currentTarget.blur();
                                  }}
                                  className="topnav-dropdown-item"
                                >
                                  {p.name}
                                </NavLink>
                              ) : (
                                <span key={p.name} className="topnav-dropdown-item topnav-link--disabled">
                                  {p.name}
                                </span>
                              )
                            )}
                          </div>
                        </div>
                      ) : (
                        <NavLink
                          key={g.slug}
                          to={
                            g.projects[0]?.projectId
                              ? `/inventory/project/${g.projects[0].projectId}`
                              : `/inventory/group/${g.slug}`
                          }
                          onClick={(e) => {
                            setOpenDropdown(null);
                            e.currentTarget.blur();
                          }}
                          className="topnav-dropdown-item"
                        >
                          {g.name}
                        </NavLink>
                      );
                    })}
                  </div>
                )}
              </div>
            ))}

            {OTHER_OCEAN_PARKS.map((p) => (
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
              {OCEAN_PARK_1.categories.map((c) => (
                <div key={c.slug} className="topnav-mobile-group">
                  <NavLink
                    to={`/inventory/${c.slug}`}
                    onClick={() => setMobileOpen(false)}
                    className={({ isActive }) => `topnav-link ${isActive ? "topnav-link--active" : ""}`}
                  >
                    {c.name}
                  </NavLink>
                  {c.groups.map((g) => (
                    <NavLink
                      key={g.slug}
                      to={
                        ANCHOR_GROUP_SLUGS.has(g.slug)
                          ? `/inventory/${ANCHOR_GROUP_CATEGORY[g.slug] ?? c.slug}#${g.slug}`
                          : g.projects.length === 1 && g.projects[0].projectId
                            ? `/inventory/project/${g.projects[0].projectId}`
                            : `/inventory/group/${g.slug}`
                      }
                      onClick={() => setMobileOpen(false)}
                      className={({ isActive }) =>
                        `topnav-link topnav-mobile-sublink ${isActive ? "topnav-link--active" : ""}`
                      }
                    >
                      {g.name}
                    </NavLink>
                  ))}
                </div>
              ))}
              {OTHER_OCEAN_PARKS.map((p) => (
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
