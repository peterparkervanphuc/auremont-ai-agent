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

// ADMIN manages the document store and AI quality monitoring; no separate inventory menu.
const ADMIN_NAV: AdminNavEntry[] = [
  { to: "/documents", label: "Kho tài liệu", icon: DocumentIcon, roles: ["admin"] },
  { to: "/eval", label: "Chất lượng trả lời", icon: ChartIcon, roles: ["admin"] },
  { to: "/conflicts", label: "Cảnh báo mâu thuẫn", icon: AlertIcon, roles: ["admin"] },
  { to: "/settings", label: "Cài đặt chung", icon: SettingsIcon, roles: ["admin"] },
];

// Ocean Park 1 is the only mega-project with real data so far — its product types
// (apartments/villas/shophouses) become the top-level menu, and each dropdown lists
// the actual sub-zones matching the reference site's menu (no longer grouped by
// Studio/1BR/2BR like before).
const OCEAN_PARK_1 = CATALOG[0];
const OTHER_OCEAN_PARKS = CATALOG.slice(1);

// These groups (apartments AND villas) already have their own section within the
// /inventory/<category-slug> page (see CategoryDetailPage) — clicking scrolls to
// that section (anchor id matches the slug) instead of opening a separate
// /inventory/group/* page.
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

// Maps each group slug to its parent category — since ANCHOR_GROUP_SLUGS is shared
// across both apartments and villas, we need this to build the correct
// /inventory/<slug> href.
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

// The Senique Hanoi has no real "sub-project" split in the catalog (it's one
// combined project, not separated into S1/S2 in the DB like Metropolitan) — but
// the UI still needs a 2-item flyout matching the reference design, pointing to
// two manually placed anchor ids in CategoryDetailPage (#the-senique-1, #the-senique-2).
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

  // On the home page and pages with a hero banner (category/project detail), the
  // menu floats transparently over the image instead of sitting as a solid bar.
  // Excludes /inventory/group/* specifically, since that page has no banner and a
  // transparent menu there would sit on a plain background and become unreadable.
  const isOverlay =
    role === "sale" &&
    (location.pathname === "/home" ||
      (location.pathname.startsWith("/inventory/") && !location.pathname.startsWith("/inventory/group/")));

  // Dropdown visibility is driven by mouse enter/leave state, not plain CSS :hover —
  // because the cursor stays in the same position after a navigation click (SPA
  // routing doesn't reload the page), so :hover would keep the dropdown open on top
  // of the new page's content. Reset on route change to force it closed.
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
                {/* Each product type now has its own URL (/inventory/chung-cu, /inventory/biet-thu...)
                    so isActive resolves correctly, instead of all three highlighting at once as before. */}
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
                        // Manually built flyout (not derived from g.projects, since these
                        // aren't real sub-projects in the DB — just scroll anchors on the same page).
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
                        // Group with multiple sub-projects AND its own in-page section (e.g. "The
                        // Metropolitan" -> Zurich/Beverly/London/Paris) — same hover flyout as
                        // before, but each sub-project scrolls to its section instead of opening
                        // a separate page.
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
                        // Already has its own in-page section — scroll to it instead of navigating away.
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
                        // Group with multiple sub-projects but NO in-page section yet -> opens a
                        // second-level flyout on hover, matching the reference site's menu; clicking
                        // the group name itself still goes to the group listing page.
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
