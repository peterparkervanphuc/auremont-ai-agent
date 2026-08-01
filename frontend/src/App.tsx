import { Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { AdminPage } from "./routes/admin/AdminPage";
import { CustomerPortal } from "./routes/customer/CustomerPortal";
import { Login } from "./routes/sale/Login";
import { SalePage } from "./routes/sale/SalePage";

// CLAUDE.md §3/§6.2 — 1 điểm truy cập chung; "/" là Customer Portal công khai,
// "/login" là đăng nhập nội bộ, sau đó routing tự động theo role (SALE / ADMIN).
function App() {
  return (
    <Routes>
      <Route path="/*" element={<CustomerPortal />} />
      <Route path="/login" element={<Login />} />
      <Route
        path="/sale/*"
        element={
          <ProtectedRoute allowedRole="sale">
            <SalePage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin/*"
        element={
          <ProtectedRoute allowedRole="admin">
            <AdminPage />
          </ProtectedRoute>
        }
      />
    </Routes>
  );
}

export default App;
