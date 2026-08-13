import { Route, Routes, useLocation } from "react-router-dom";
import { TopNavbar } from "./components/TopNavbar";
import { ChatWidget } from "./components/ChatWidget";
import { Footer } from "./components/Footer";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { useAuth } from "./hooks/useAuth";
import { Landing } from "./routes/Landing";
import { Home } from "./routes/Home";
import { Login } from "./routes/sale/Login";
import { SalePage } from "./routes/sale/SalePage";
import { CategoryDetailPage } from "./routes/sale/CategoryDetailPage";
import { CatalogGroupPage } from "./routes/sale/CatalogGroupPage";
import { ProjectOverviewPage } from "./routes/sale/ProjectOverviewPage";
import { AdminHome } from "./routes/admin/AdminHome";
import { DocumentsTab } from "./routes/admin/DocumentsTab";
import { EvalTab } from "./routes/admin/EvalTab";
import { ConflictsTab } from "./routes/admin/ConflictsTab";
import { SettingsTab } from "./routes/admin/SettingsTab";
import { NotFound } from "./routes/NotFound";

/** Admin có bảng điều khiển riêng; Sale thấy trang chủ hướng chat tư vấn. */
function HomeRoute() {
  const { role } = useAuth();
  return role === "admin" ? <AdminHome /> : <Home />;
}

/** Shell chung: thanh menu ngang trên đầu + vùng nội dung, dùng cho cả SALE và ADMIN. */
function AppShell() {
  const { role } = useAuth();
  const location = useLocation();
  const showChatWidget = role === "sale" && !location.pathname.startsWith("/chat");
  // Chat là UI dạng app full-height (ChatGPT-style, không cuộn trang) — thêm Footer
  // vào đó sẽ đội chiều cao vượt 100vh và phá layout cố định của khung chat.
  const showFooter = !location.pathname.startsWith("/chat");

  return (
    <div className="app-shell">
      <TopNavbar />
      <div className="app-content">
        <Routes>
          <Route path="/home" element={<HomeRoute />} />

          {/* Chat tư vấn khách hàng — chỉ dành cho SALE, ADMIN không trực tiếp tư vấn khách. */}
          <Route
            path="/chat/*"
            element={
              <ProtectedRoute allowedRole="sale">
                <SalePage />
              </ProtectedRoute>
            }
          />

          {/* Tra cứu dự án theo loại hình — vào thẳng qua dropdown menu TopNavbar,
              không còn trang mục lục /inventory riêng (trùng lặp với menu). */}
          <Route
            path="/inventory/:categorySlug"
            element={
              <ProtectedRoute allowedRole="sale">
                <CategoryDetailPage />
              </ProtectedRoute>
            }
          />
          {/* Nhóm/phân khu trong catalog nhiều dự án (vd "The Metropolitan" gồm Beverly/London/Paris/Zurich). */}
          <Route
            path="/inventory/group/:groupSlug"
            element={
              <ProtectedRoute allowedRole="sale">
                <CatalogGroupPage />
              </ProtectedRoute>
            }
          />
          {/* Trang chi tiết 1 dự án con thật (The Beverly, The Sapphire...), khác với CategoryDetailPage
              ở trên vốn chỉ hiển thị tổng quan CỦA RIÊNG Vinhomes Ocean Park theo loại hình. */}
          <Route
            path="/inventory/project/:projectId"
            element={
              <ProtectedRoute allowedRole="sale">
                <ProjectOverviewPage />
              </ProtectedRoute>
            }
          />

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

      {showFooter && <Footer />}
      {showChatWidget && <ChatWidget />}
    </div>
  );
}

// 1 điểm truy cập chung; sau đăng nhập routing theo role (SALE / ADMIN).
function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
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
