import { useEffect, useState } from "react";
import { api } from "../../api/client";
import type { DocumentResponse, DocumentVisibility } from "../../types";

// CLAUDE.md §6.5 Tab 1 — upload, quét, gán nhãn RBAC bắt buộc, danh sách, xoá.
export function DocumentsTab() {
  const [documents, setDocuments] = useState<DocumentResponse[]>([]);

  useEffect(() => {
    api.get<DocumentResponse[]>("/documents").then(setDocuments);
  }, []);

  // TODO: drag-and-drop upload -> POST /documents/ingest (multipart, once ingestion_service reads files).

  const setVisibility = async (documentId: number, visibility: DocumentVisibility) => {
    const updated = await api.patch<DocumentResponse>(`/documents/${documentId}/visibility`, { visibility });
    setDocuments((prev) => prev.map((d) => (d.id === documentId ? updated : d)));
  };

  const removeDocument = async (documentId: number) => {
    await api.delete(`/documents/${documentId}`);
    setDocuments((prev) => prev.filter((d) => d.id !== documentId));
  };

  return (
    <div>
      <h3>Quản lý Tài liệu</h3>
      <table>
        <thead>
          <tr>
            <th>Tên file</th>
            <th>Trạng thái</th>
            <th>Phân quyền</th>
            <th>Xoá</th>
          </tr>
        </thead>
        <tbody>
          {documents.map((doc) => (
            <tr key={doc.id}>
              <td>{doc.title}</td>
              <td>{doc.status}</td>
              <td>
                <select value={doc.visibility} onChange={(e) => setVisibility(doc.id, e.target.value as DocumentVisibility)}>
                  <option value="internal">Nội bộ</option>
                  <option value="public">Public</option>
                </select>
              </td>
              <td>
                <button onClick={() => removeDocument(doc.id)}>Xoá</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
