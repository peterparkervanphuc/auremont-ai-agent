import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../api/client";
import { useAuth } from "../../hooks/useAuth";
import type { UserRole } from "../../types";

interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

function decodeRoleFromToken(accessToken: string): UserRole {
  // backend/core/security.py create_access_token embeds {"role": ...} in the JWT payload.
  const payload = JSON.parse(atob(accessToken.split(".")[1])) as { role: UserRole };
  return payload.role;
}

// CLAUDE.md §6.2 — internal login, routes to /sale/* or /admin/* by role after auth.
export function Login() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const { login } = useAuth();
  const navigate = useNavigate();

  // TODO: POST /auth/login expects OAuth2PasswordRequestForm (form-encoded), not JSON —
  // switch this fetch to `application/x-www-form-urlencoded` when wiring the real call.
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const result = await api.post<TokenResponse>("/auth/login", { username, password });
      const role = decodeRoleFromToken(result.access_token);
      login(result.access_token, result.refresh_token, role);
      navigate(role === "admin" ? "/admin" : "/sale");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Đăng nhập thất bại");
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <h2>Đăng nhập</h2>
      {error && <p>{error}</p>}
      <input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Username" />
      <input
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
        placeholder="Password"
      />
      <button type="submit">Đăng nhập</button>
    </form>
  );
}
