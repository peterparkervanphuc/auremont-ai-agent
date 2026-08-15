import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import type { UserRole } from "../types";

interface ProtectedRouteProps {
  /** Omit to require only authentication, with no role restriction. */
  allowedRole?: UserRole;
  children: ReactNode;
}

export function ProtectedRoute({ allowedRole, children }: ProtectedRouteProps) {
  const { isAuthenticated, role } = useAuth();

  if (!isAuthenticated) return <Navigate to="/login" replace />;
  // Wrong role: redirect to home instead of bouncing back to the login screen.
  if (allowedRole && role !== allowedRole) return <Navigate to="/home" replace />;

  return <>{children}</>;
}
