import { useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { AppSidebar } from "./components/AppSidebar";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { Home } from "./routes/Home";
import { Login } from "./routes/sale/Login";
import { SalePage } from "./routes/sale/SalePage";
import { DocumentsTab } from "./routes/admin/DocumentsTab";
import { EvalTab } from "./routes/admin/EvalTab";
import { ConflictsTab } from "./routes/admin/ConflictsTab";
import { ApiTestTab } from "./routes/admin/ApiTestTab";
import { SettingsTab } from "./routes/admin/SettingsTab";
import { NotFound } from "./routes/NotFound";

/** Shell chung: sidebar bên trái + vùng nội dung, dùng cho cả SALE và ADMIN. */
function AppShell() {
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("sb-collapsed") === "true");
  const [mobileOpen, setMobileOpen] = useState(false);

  const toggleCollapse = () => {
    setCollapsed((v) => {
      const next = !v;
      localStorage.setItem("sb-collapsed", String(next));
      return next;
    });
  };

  return (
    <div className={`app-shell ${collapsed ? "app-shell--sm" : ""}`}>
      <AppSidebar
        collapsed={collapsed}
        onToggleCollapse={toggleCollapse}
        mobileOpen={mobileOpen}
        onMobileClose={() => setMobileOpen(false)}
        onMobileOpen={() => setMobileOpen(true)}
      />
      <div className="app-content">
        <Routes>
          <Route path="/home" element={<Home />} />
          <Route path="/chat/*" element={<SalePage />} />

          {/* Khu vực chỉ dành cho ADMIN */}
          <Route
            path="/documents"
            element={
              <ProtectedRoute allowedRole="admin">
                <DocumentsTab />
              </ProtectedRoute>
            }
          />
          <Route
            path="/eval"
            element={
              <ProtectedRoute allowedRole="admin">
                <EvalTab />
              </ProtectedRoute>
            }
          />
          <Route
            path="/conflicts"
            element={
              <ProtectedRoute allowedRole="admin">
                <ConflictsTab />
              </ProtectedRoute>
            }
          />
          <Route
            path="/api-test"
            element={
              <ProtectedRoute allowedRole="admin">
                <ApiTestTab />
              </ProtectedRoute>
            }
          />
          <Route
            path="/settings"
            element={
              <ProtectedRoute allowedRole="admin">
                <SettingsTab />
              </ProtectedRoute>
            }
          />

          <Route path="*" element={<NotFound />} />
        </Routes>
      </div>
    </div>
  );
}

// 1 điểm truy cập chung; sau đăng nhập routing theo role (SALE / ADMIN).
function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/home" replace />} />
      <Route path="/login" element={<Login />} />
      <Route
        path="*"
        element={
          <ProtectedRoute>
            <AppShell />
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}

export default App;
