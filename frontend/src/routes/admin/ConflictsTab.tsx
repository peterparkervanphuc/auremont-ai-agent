import { useEffect, useState } from "react";
import { api } from "../../api/client";

interface ConflictFlagResponse {
  id: number;
  document_id_a: number;
  document_id_b: number;
  description: string | null;
  status: "open" | "resolved";
  created_at: string;
  resolved_at: string | null;
}

// CLAUDE.md §6.5 Tab 3 — flag mâu thuẫn giữa 2 tài liệu, xoá cũ / ưu tiên mới.
export function ConflictsTab() {
  const [conflicts, setConflicts] = useState<ConflictFlagResponse[]>([]);

  useEffect(() => {
    api.get<ConflictFlagResponse[]>("/admin/conflicts").then(setConflicts);
  }, []);

  const resolve = async (conflictId: number, keepDocumentId: number) => {
    await api.post(`/admin/conflicts/${conflictId}/resolve`, { keep_document_id: keepDocumentId });
    setConflicts((prev) => prev.filter((c) => c.id !== conflictId));
  };

  return (
    <div>
      <h3>Cảnh báo mâu thuẫn</h3>
      <ul>
        {conflicts.map((c) => (
          <li key={c.id}>
            {c.description ?? `Tài liệu #${c.document_id_a} vs #${c.document_id_b}`}
            <button onClick={() => resolve(c.id, c.document_id_a)}>Giữ tài liệu A</button>
            <button onClick={() => resolve(c.id, c.document_id_b)}>Giữ tài liệu B</button>
          </li>
        ))}
      </ul>
    </div>
  );
}
