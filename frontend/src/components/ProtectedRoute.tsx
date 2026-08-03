import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import type { UserRole } from "../types";

interface ProtectedRouteProps {
  /** Bỏ trống = chỉ cần đăng nhập, không giới hạn role. */
  allowedRole?: UserRole;
  children: ReactNode;
}

export function ProtectedRoute({ allowedRole, children }: ProtectedRouteProps) {
  const { isAuthenticated, role } = useAuth();

  if (!isAuthenticated) return <Navigate to="/login" replace />;
  // Role không đủ quyền: đưa về trang chủ thay vì đá ra màn hình đăng nhập.
  if (allowedRole && role !== allowedRole) return <Navigate to="/home" replace />;

  return <>{children}</>;
}
