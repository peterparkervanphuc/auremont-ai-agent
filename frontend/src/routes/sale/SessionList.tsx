import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import type { ChatSessionResponse } from "../../types";

// CLAUDE.md §5.2.b — sidebar: nút "+" tạo Session mới, danh sách "Session: Khách...".
export function SessionList() {
  const [sessions, setSessions] = useState<ChatSessionResponse[]>([]);

  useEffect(() => {
    api.get<ChatSessionResponse[]>("/sale/sessions").then(setSessions);
  }, []);

  const createSession = async () => {
    const session = await api.post<ChatSessionResponse>("/sale/sessions", {});
    setSessions((prev) => [session, ...prev]);
  };

  return (
    <aside>
      <button onClick={createSession}>+ Phiên khách hàng mới</button>
      <ul>
        {sessions.map((s) => (
          <li key={s.id}>
            <Link to={`/sale/sessions/${s.id}`}>{s.title ?? `Session #${s.id}`}</Link>
          </li>
        ))}
      </ul>
    </aside>
  );
}
