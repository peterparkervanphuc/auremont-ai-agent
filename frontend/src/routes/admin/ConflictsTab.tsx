import { useEffect, useState } from "react";
import { api } from "../../api/client";
import { parseServerDate } from "../../utils/datetime";
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

// Flags conflicts between two documents; admin picks which one to keep.
export function ConflictsTab() {
  const [conflicts, setConflicts] = useState<ConflictFlagResponse[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .get<ConflictFlagResponse[]>("/admin/conflicts")
      .then((rows) => {
        setConflicts(rows);
        setError(null);
      })
      // An empty list and a failed load look identical on screen otherwise — the Admin
      // reads "Không có mâu thuẫn nào cần xử lý" and moves on, while flags sit unhandled.
      .catch(() => setError("Không tải được danh sách mâu thuẫn."));
  }, []);

  const resolve = async (conflictId: number, keepDocumentId: number) => {
    setError(null);
    try {
      await api.post(`/admin/conflicts/${conflictId}/resolve`, { keep_document_id: keepDocumentId });
      // Only drop the row once the server confirms, so a failed resolve leaves the flag
      // visible and actionable instead of vanishing from a list that is now wrong.
      setConflicts((prev) => prev.filter((c) => c.id !== conflictId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không xử lý được mâu thuẫn này.");
    }
  };

  return (
    <div className="page">
      <h2 className="page-title">Cảnh báo mâu thuẫn</h2>
      <p className="page-sub">Hai tài liệu có nội dung khác nhau cho cùng một dự án — chọn tài liệu cần giữ lại.</p>

      {error && <div className="alert alert-danger">{error}</div>}

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
              <div className="conflict-card-head">
                <AlertIcon size={16} />
                <span>Mâu thuẫn dữ liệu</span>
                <span className="conflict-doc-meta" style={{ marginLeft: "auto", textTransform: "none" }}>
                  {parseServerDate(c.created_at).toLocaleString("vi-VN")}
                </span>
              </div>

              <p style={{ color: "var(--text-1)", fontSize: "0.9375rem", lineHeight: 1.65 }}>
                {c.description ?? `Tài liệu #${c.document_id_a} mâu thuẫn với tài liệu #${c.document_id_b}`}
              </p>

              <div className="conflict-actions" style={{ marginTop: 16 }}>
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
