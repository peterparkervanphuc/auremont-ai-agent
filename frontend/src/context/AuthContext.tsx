import { useCallback, useMemo, useState, type ReactNode } from "react";
import { AuthContext } from "./auth-context";
import { api } from "../api/client";
import type { UserRole } from "../types";

function read(key: string): string | null {
  return localStorage.getItem(key);
}

/**
 * Auth dùng chung cho toàn app — sidebar và các trang cùng đọc 1 nguồn state,
 * nên khi đăng xuất mọi nơi cập nhật đồng thời.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState(() => ({
    isAuthenticated: Boolean(read("access_token")),
    role: read("role") as UserRole | null,
    username: read("username"),
  }));

  const login = useCallback(
    (accessToken: string, refreshToken: string, role: UserRole, username: string) => {
      localStorage.setItem("access_token", accessToken);
      localStorage.setItem("refresh_token", refreshToken);
      localStorage.setItem("role", role);
      localStorage.setItem("username", username);
      setState({ isAuthenticated: true, role, username });
    },
    [],
  );

  const logout = useCallback(() => {
    // Báo server để ghi vết, nhưng không chờ: JWT stateless nên xoá token phía
    // client mới là thứ thực sự kết thúc phiên. Lỗi mạng không được chặn logout.
    api.post("/auth/logout").catch(() => {});
    ["access_token", "refresh_token", "role", "username"].forEach((k) => localStorage.removeItem(k));
    setState({ isAuthenticated: false, role: null, username: null });
  }, []);

  const value = useMemo(() => ({ ...state, login, logout }), [state, login, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
