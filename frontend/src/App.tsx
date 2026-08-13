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
import { ZoneDetailPage } from "./routes/sale/ZoneDetailPage";
import { CatalogGroupPage } from "./routes/sale/CatalogGroupPage";
import { ProjectOverviewPage } from "./routes/sale/ProjectOverviewPage";
import { AdminHome } from "./routes/admin/AdminHome";
import { DocumentsTab } from "./routes/admin/DocumentsTab";
import { EvalTab } from "./routes/admin/EvalTab";
import { ConflictsTab } from "./routes/admin/ConflictsTab";
import { SettingsTab } from "./routes/admin/SettingsTab";
import { NotFound } from "./routes/NotFound";

/** Admin gets its own dashboard; Sale sees the chat-oriented home page. */
function HomeRoute() {
  const { role } = useAuth();
  return role === "admin" ? <AdminHome /> : <Home />;
}

/** Shared shell: top nav bar plus content area, used by both SALE and ADMIN. */
function AppShell() {
  const { role } = useAuth();
  const location = useLocation();
  const showChatWidget = role === "sale" && !location.pathname.startsWith("/chat");
  // Chat is a full-height, app-style UI (ChatGPT-style, no page scroll) — adding the
  // Footer there would push the height past 100vh and break the chat's fixed layout.
  const showFooter = !location.pathname.startsWith("/chat");

  return (
    <div className="app-shell">
      <TopNavbar />
      <div className="app-content">
        <Routes>
          <Route path="/home" element={<HomeRoute />} />

          {/* Customer consultation chat — SALE only; ADMIN doesn't consult customers directly. */}
          <Route
            path="/chat/*"
            element={
              <ProtectedRoute allowedRole="sale">
                <SalePage />
              </ProtectedRoute>
            }
          />

          {/* Project lookup by product type — reached directly via the TopNavbar dropdown;
              there is no separate /inventory index page anymore (it duplicated the menu). */}
          <Route
            path="/inventory/:categorySlug"
            element={
              <ProtectedRoute allowedRole="sale">
                <CategoryDetailPage />
              </ProtectedRoute>
            }
          />
          {/* One zone (phân khu) per page. Static segments above/below ("group", "project")
              are more specific, so React Router still matches those first. */}
          <Route
            path="/inventory/:categorySlug/:zoneSlug"
            element={
              <ProtectedRoute allowedRole="sale">
                <ZoneDetailPage />
              </ProtectedRoute>
            }
          />
          {/* Group/sub-zone within the multi-project catalog (e.g. "The Metropolitan" = Beverly/London/Paris/Zurich). */}
          <Route
            path="/inventory/group/:groupSlug"
            element={
              <ProtectedRoute allowedRole="sale">
                <CatalogGroupPage />
              </ProtectedRoute>
            }
          />
          {/* Detail page for one real sub-project (The Beverly, The Sapphire...), distinct from
              CategoryDetailPage above, which only shows Vinhomes Ocean Park's overview by product type. */}
          <Route
            path="/inventory/project/:projectId"
            element={
              <ProtectedRoute allowedRole="sale">
                <ProjectOverviewPage />
              </ProtectedRoute>
            }
          />

          {/* ADMIN-only area */}
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

// Single entry point; routing after login branches by role (SALE / ADMIN).
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
