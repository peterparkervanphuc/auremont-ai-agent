import { useCallback, useState } from "react";
import type { UserRole } from "../types";

interface AuthState {
  isAuthenticated: boolean;
  role: UserRole | null;
}

function readStoredRole(): UserRole | null {
  return (localStorage.getItem("role") as UserRole | null) ?? null;
}

// TODO: replace with a real auth context (e.g. React Context + refresh-token flow) once
// POST /auth/login is wired up in the UI. This is a minimal localStorage-backed placeholder.
export function useAuth() {
  const [state, setState] = useState<AuthState>({
    isAuthenticated: Boolean(localStorage.getItem("access_token")),
    role: readStoredRole(),
  });

  const login = useCallback((accessToken: string, refreshToken: string, role: UserRole) => {
    localStorage.setItem("access_token", accessToken);
    localStorage.setItem("refresh_token", refreshToken);
    localStorage.setItem("role", role);
    setState({ isAuthenticated: true, role });
  }, []);

  const logout = useCallback(() => {
    localStorage.removeItem("access_token");
    localStorage.removeItem("refresh_token");
    localStorage.removeItem("role");
    setState({ isAuthenticated: false, role: null });
  }, []);

  return { ...state, login, logout };
}
