import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import type { DocumentResponse, DocumentVisibility } from "../../types";
import { InboxIcon, LoaderIcon, TrashIcon, UploadIcon } from "../../components/Icons";

const STATUS_LABEL: Record<string, { text: string; badge: string }> = {
  pending: { text: "Đang chờ", badge: "badge-warning" },
  processing: { text: "Đang xử lý & quét mã độc", badge: "badge-info" },
  completed: { text: "Upload & Vector hóa thành công", badge: "badge-success" },
  failed: { text: "Thất bại", badge: "badge-danger" },
  blocked: { text: "Đã chặn — nội dung bất thường", badge: "badge-danger" },
};

// Backend /documents/ingest hiện nhận raw_text. Đọc PDF/Excel bằng readAsText
// chỉ ra chuỗi nhị phân vô nghĩa, nên chặn sớm và báo rõ cho Admin thay vì
// đẩy rác vào pipeline vector hoá.
const TEXT_EXTENSIONS = [".txt", ".md", ".csv"];

function isTextFile(file: File): boolean {
  const name = file.name.toLowerCase();
  return TEXT_EXTENSIONS.some((ext) => name.endsWith(ext));
}

function readFileAsText(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result ?? ""));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(file);
  });
}

// kéo-thả file, quét mã độc, gán nhãn RBAC, danh sách, xoá.
export function DocumentsTab() {
  const [documents, setDocuments] = useState<DocumentResponse[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadDocuments = useCallback(() => {
    api.get<DocumentResponse[]>("/documents").then(setDocuments).catch(() => setDocuments([]));
  }, []);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  const uploadFile = async (file: File) => {
    if (!isTextFile(file)) {
      setError(
        `Chưa hỗ trợ trích xuất nội dung từ "${file.name}". Hiện tại chỉ nhận .txt/.md/.csv — ` +
          "pipeline đọc PDF/Excel đang được hoàn thiện.",
      );
      return;
    }

    setUploading(true);
    setError(null);
    try {
      const raw_text = await readFileAsText(file);
      await api.post("/documents/ingest", { title: file.name, raw_text });
      loadDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload thất bại — phát hiện nội dung bất thường, chặn file");
    } finally {
      setUploading(false);
    }
  };

  const handleFiles = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    uploadFile(files[0]);
  };

  const setVisibility = async (documentId: number, visibility: DocumentVisibility) => {
    const updated = await api.patch<DocumentResponse>(`/documents/${documentId}/visibility`, { visibility });
    setDocuments((prev) => prev.map((d) => (d.id === documentId ? updated : d)));
  };

  const removeDocument = async (documentId: number) => {
    await api.delete(`/documents/${documentId}`);
    setDocuments((prev) => prev.filter((d) => d.id !== documentId));
  };

  return (
    <div className="page">
      <h2 className="page-title">Kho Tài liệu</h2>
      <p className="page-sub">Tải lên và quản lý tài liệu dự án cho pipeline RAG.</p>

      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragActive(false);
          handleFiles(e.dataTransfer.files);
        }}
        onClick={() => fileInputRef.current?.click()}
        className={`upload-zone ${dragActive ? "upload-zone--active" : ""}`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".txt,.md,.csv"
          onChange={(e) => handleFiles(e.target.files)}
          style={{ display: "none" }}
        />
        <div className="upload-zone-icon">
          {uploading ? <LoaderIcon size={24} className="icon-spin" /> : <UploadIcon size={24} />}
        </div>
        <p className="upload-zone-title">
          {uploading ? "Đang xử lý & quét mã độc..." : "Kéo thả tài liệu vào đây"}
        </p>
        <p className="upload-zone-hint">hoặc bấm để chọn từ máy tính · hiện hỗ trợ .txt, .md, .csv</p>
      </div>

      {error && (
        <div className="alert alert-danger" style={{ marginTop: 16 }}>
          {error}
        </div>
      )}

      <div style={{ marginTop: 32 }}>
        <h3 className="section-title">Danh sách tài liệu</h3>
        {documents.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state-icon">
              <InboxIcon size={26} />
            </div>
            <p>Chưa có tài liệu nào được tải lên.</p>
          </div>
        ) : (
          <div className="data-list">
            {documents.map((doc) => {
              const status = STATUS_LABEL[doc.status] ?? { text: doc.status, badge: "badge-muted" };
              return (
                <div key={doc.id} className="data-row">
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="data-row-title">{doc.title}</div>
                    <div className="data-row-meta">{new Date(doc.created_at).toLocaleString("vi-VN")}</div>
                  </div>

                  <span className={`badge ${status.badge}`}>{status.text}</span>

                  <select
                    value={doc.visibility}
                    onChange={(e) => setVisibility(doc.id, e.target.value as DocumentVisibility)}
                    className="doc-visibility-select"
                    aria-label="Phân quyền tài liệu"
                  >
                    <option value="internal">Nội bộ</option>
                    <option value="public">Public</option>
                  </select>

                  <button onClick={() => removeDocument(doc.id)} className="btn btn-sm btn-danger" aria-label="Xoá">
                    <TrashIcon size={14} />
                    Xoá
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
