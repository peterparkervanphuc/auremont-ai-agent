import { Navigate, Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "./components/ProtectedRoute";
import { AdminPage } from "./routes/admin/AdminPage";
import { Login } from "./routes/sale/Login";
import { SalePage } from "./routes/sale/SalePage";

// 1 điểm truy cập chung; màn hình ĐĂNG NHẬP nội bộ,
// sau xác thực routing tự động theo role (SALE / ADMIN).
function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/login" replace />} />
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
