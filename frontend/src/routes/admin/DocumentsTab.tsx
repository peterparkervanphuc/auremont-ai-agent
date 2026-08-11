import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import type {
  DocumentResponse,
  DocumentVisibility,
  ProjectResponse,
} from "../../types";
import {
  InboxIcon,
  LoaderIcon,
  TrashIcon,
  UploadIcon,
} from "../../components/Icons";

const STATUS_LABEL: Record<
  string,
  { text: string; badge: string }
> = {
  pending: { text: "Đang chờ", badge: "badge-warning" },
  processing: {
    text: "Đang xử lý & quét mã độc",
    badge: "badge-info",
  },
  completed: {
    text: "Upload & Vector hóa thành công",
    badge: "badge-success",
  },
  failed: { text: "Thất bại", badge: "badge-danger" },
  blocked: {
    text: "Đã chặn — nội dung bất thường",
    badge: "badge-danger",
  },
};

const ALLOWED_EXTENSIONS = [".pdf", ".docx"];

interface UploadResponse {
  document_id: number;
  status: string;
  message: string;
}

function isSupportedFile(file: File): boolean {
  const filename = file.name.toLowerCase();
  return ALLOWED_EXTENSIONS.some((extension) =>
    filename.endsWith(extension),
  );
}

export function DocumentsTab() {
  const [documents, setDocuments] = useState<DocumentResponse[]>([]);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  // Which project the uploaded document belongs to. Retrieval filters on this, and
  // conflict detection only compares documents within the same project.
  const [projectId, setProjectId] = useState<string>("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadDocuments = useCallback(() => {
    api
      .get<DocumentResponse[]>("/documents")
      .then(setDocuments)
      .catch(() => setDocuments([]));
  }, []);

  useEffect(() => {
    loadDocuments();
  }, [loadDocuments]);

  useEffect(() => {
    api
      .get<ProjectResponse[]>("/projects")
      .then((list) => {
        setProjects(list);
        // Preselect when there is only one project, so the common case needs no clicks.
        if (list.length === 1) setProjectId(list[0].id);
      })
      .catch(() => setProjects([]));
  }, []);

  const uploadFile = async (file: File) => {
    if (!isSupportedFile(file)) {
      setError(
        `Không hỗ trợ "${file.name}". Chỉ nhận file PDF hoặc DOCX.`,
      );
      return;
    }

    setUploading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("visibility", "internal");
      // Without a project the document cannot be filtered per project at retrieval
      // time, and conflict detection has nothing to compare it against.
      if (projectId) formData.append("project_id", projectId);

      const result = await api.postForm<UploadResponse>(
        "/documents/upload",
        formData,
      );

      loadDocuments();

      if (result.status !== "completed") {
        setError(result.message);
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Upload tài liệu thất bại.",
      );
    } finally {
      setUploading(false);
    }
  };

  const handleFiles = (files: FileList | null) => {
    if (!files || files.length === 0) {
      return;
    }

    void uploadFile(files[0]);
  };

  const setVisibility = async (
    documentId: number,
    visibility: DocumentVisibility,
  ) => {
    const updated = await api.patch<DocumentResponse>(
      `/documents/${documentId}/visibility`,
      { visibility },
    );

    setDocuments((previous) =>
      previous.map((document) =>
        document.id === documentId ? updated : document,
      ),
    );
  };

  const removeDocument = async (documentId: number) => {
    await api.delete(`/documents/${documentId}`);

    setDocuments((previous) =>
      previous.filter((document) => document.id !== documentId),
    );
  };

  return (
    <div className="page">
      <h2 className="page-title">Kho Tài liệu</h2>
      <p className="page-sub">
        Tải PDF/DOCX để parse, vector hóa và đưa vào kho tri thức RAG.
      </p>

      <div className="upload-project-row">
        <label htmlFor="upload-project" className="upload-project-label">
          Dự án
        </label>
        <select
          id="upload-project"
          className="upload-project-select"
          value={projectId}
          onChange={(event) => setProjectId(event.target.value)}
        >
          <option value="">— Không gắn dự án —</option>
          {projects.map((project) => (
            <option key={project.id} value={project.id}>
              {project.name}
            </option>
          ))}
        </select>
        {!projectId && (
          <span className="upload-project-hint">
            Nên chọn dự án để lọc tài liệu khi tư vấn và phát hiện mâu thuẫn.
          </span>
        )}
      </div>

      <div
        className={`upload-zone ${
          dragActive ? "upload-zone--active" : ""
        }`}
        onDragOver={(event) => {
          event.preventDefault();
          setDragActive(true);
        }}
        onDragLeave={() => setDragActive(false)}
        onDrop={(event) => {
          event.preventDefault();
          setDragActive(false);
          handleFiles(event.dataTransfer.files);
        }}
        onClick={() => fileInputRef.current?.click()}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          onChange={(event) => handleFiles(event.target.files)}
          style={{ display: "none" }}
        />

        <div className="upload-zone-icon">
          {uploading ? (
            <LoaderIcon size={24} className="icon-spin" />
          ) : (
            <UploadIcon size={24} />
          )}
        </div>

        <p className="upload-zone-title">
          {uploading
            ? "Đang parse, quét nội dung và vector hóa..."
            : "Kéo thả tài liệu vào đây"}
        </p>

        <p className="upload-zone-hint">
          hoặc bấm để chọn từ máy tính · hỗ trợ PDF và DOCX
        </p>
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
            {documents.map((document) => {
              const displayStatus =
                STATUS_LABEL[document.status] ?? {
                  text: document.status,
                  badge: "badge-muted",
                };

              return (
                <div key={document.id} className="data-row">
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="data-row-title">
                      {document.title}
                    </div>
                    <div className="data-row-meta">
                      {new Date(
                        document.created_at,
                      ).toLocaleString("vi-VN")}
                    </div>
                  </div>

                  <span className={`badge ${displayStatus.badge}`}>
                    {displayStatus.text}
                  </span>

                  <select
                    className="doc-visibility-select"
                    value={document.visibility}
                    aria-label="Phân quyền tài liệu"
                    onChange={(event) =>
                      void setVisibility(
                        document.id,
                        event.target.value as DocumentVisibility,
                      )
                    }
                  >
                    <option value="internal">Nội bộ</option>
                    <option value="public">Public</option>
                  </select>

                  <button
                    className="btn btn-sm btn-danger"
                    type="button"
                    aria-label="Xóa"
                    onClick={() => void removeDocument(document.id)}
                  >
                    <TrashIcon size={14} />
                    Xóa
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