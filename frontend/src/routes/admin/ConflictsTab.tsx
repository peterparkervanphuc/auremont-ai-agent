import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { AlertIcon, CheckIcon } from "../../components/Icons";

interface ConflictFlagResponse {
  id: number;
  document_id_a: number;
  document_id_b: number;
  description: string | null;
  status: "open" | "resolved";
  created_at: string;
  resolved_at: string | null;
}

// flag mâu thuẫn giữa 2 tài liệu, xoá cũ / ưu tiên mới.
export function ConflictsTab() {
  const [conflicts, setConflicts] = useState<ConflictFlagResponse[]>([]);

  useEffect(() => {
    api.get<ConflictFlagResponse[]>("/admin/conflicts").then(setConflicts).catch(() => setConflicts([]));
  }, []);

  const resolve = async (conflictId: number, keepDocumentId: number) => {
    await api.post(`/admin/conflicts/${conflictId}/resolve`, { keep_document_id: keepDocumentId });
    setConflicts((prev) => prev.filter((c) => c.id !== conflictId));
  };

  return (
    <div className="page">
      <h2 className="page-title">Cảnh báo mâu thuẫn</h2>
      <p className="page-sub">Hai tài liệu có nội dung khác nhau cho cùng một dự án — chọn tài liệu cần giữ lại.</p>

      {conflicts.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">
            <CheckIcon size={26} />
          </div>
          <p>Không có mâu thuẫn nào cần xử lý.</p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
          {conflicts.map((c) => (
            <div key={c.id} className="conflict-card">
              <div className="hitl-head">
                <AlertIcon size={16} />
                <span className="hitl-title">Mâu thuẫn dữ liệu</span>
                <span className="data-row-meta" style={{ marginLeft: "auto" }}>
                  {new Date(c.created_at).toLocaleString("vi-VN")}
                </span>
              </div>

              <p style={{ color: "var(--text-h)", fontSize: 14.5, lineHeight: 1.6 }}>
                {c.description ?? `Tài liệu #${c.document_id_a} mâu thuẫn với tài liệu #${c.document_id_b}`}
              </p>

              <div className="hitl-actions">
                <button onClick={() => resolve(c.id, c.document_id_a)} className="btn btn-sm btn-outline">
                  Giữ tài liệu #{c.document_id_a}
                </button>
                <button onClick={() => resolve(c.id, c.document_id_b)} className="btn btn-sm btn-outline">
                  Giữ tài liệu #{c.document_id_b}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
