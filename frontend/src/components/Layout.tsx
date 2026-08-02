import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { LogoutIcon } from "./Icons";

export interface NavItem {
  id: string;
  label: string;
  icon: ReactNode;
}

interface LayoutProps {
  title: string;
  navItems: NavItem[];
  activeTab: string;
  onTabChange: (id: string) => void;
  children: ReactNode;
}

/** Sidebar shell dùng chung cho Admin — trắng/xanh dương, minimal. */
export function Layout({ title, navItems, activeTab, onTabChange, children }: LayoutProps) {
  const { logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="app-shell">
      <aside className="app-sidebar">
        <div className="app-brand">
          <div className="app-brand-mark">S</div>
          <span className="app-brand-name">{title}</span>
        </div>

        <nav className="app-nav">
          {navItems.map((item) => (
            <button
              key={item.id}
              onClick={() => onTabChange(item.id)}
              className={`app-nav-item ${item.id === activeTab ? "app-nav-item--active" : ""}`}
            >
              <span className="app-nav-icon">{item.icon}</span>
              <span>{item.label}</span>
            </button>
          ))}
        </nav>

        <button onClick={handleLogout} className="app-logout">
          <span className="app-nav-icon">
            <LogoutIcon size={18} />
          </span>
          <span>Đăng xuất</span>
        </button>
      </aside>

      <main className="app-main">{children}</main>
    </div>
  );
}
