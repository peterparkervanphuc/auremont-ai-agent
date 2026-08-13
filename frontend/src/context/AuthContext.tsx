import { useCallback, useMemo, useState, type ReactNode } from "react";
import { AuthContext } from "./auth-context";
import { api } from "../api/client";
import type { UserRole } from "../types";

function read(key: string): string | null {
  return localStorage.getItem(key);
}

function isTokenValid(token: string | null): boolean {
  if (!token) return false;
  try {
    const payload = JSON.parse(atob(token.split(".")[1])) as { exp: number };
    return payload.exp * 1000 > Date.now();
  } catch {
    return false;
  }
}

function clearStoredSession() {
  ["access_token", "refresh_token", "role", "username"].forEach((k) => localStorage.removeItem(k));
}

/**
 * Auth dùng chung cho toàn app — sidebar và các trang cùng đọc 1 nguồn state,
 * nên khi đăng xuất mọi nơi cập nhật đồng thời.
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState(() => {
    // Access token còn trong localStorage nhưng đã hết hạn (từ phiên test cũ) vẫn
    // để isAuthenticated=true nếu chỉ check sự tồn tại — trang sẽ nhảy vào /home rồi
    // bị 401 đá ngược lại /login, không bao giờ thấy Landing. Check hạn ngay từ đầu.
    if (!isTokenValid(read("access_token"))) {
      clearStoredSession();
      return { isAuthenticated: false, role: null, username: null };
    }
    return {
      isAuthenticated: true,
      role: read("role") as UserRole | null,
      username: read("username"),
    };
  });

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
    clearStoredSession();
    setState({ isAuthenticated: false, role: null, username: null });
  }, []);

  const value = useMemo(() => ({ ...state, login, logout }), [state, login, logout]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
