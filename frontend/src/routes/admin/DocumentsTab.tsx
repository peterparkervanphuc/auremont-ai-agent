import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "../../api/client";
import type {
  DocumentResponse,
  DocumentVisibility,
  ProjectResponse,
} from "../../types";
import { parseServerDate } from "../../utils/datetime";
import {
  AlertIcon,
  CheckIcon,
  InboxIcon,
  LoaderIcon,
  TrashIcon,
  UploadIcon,
  XIcon,
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

interface UploadQueueItem {
  id: string;
  file: File;
  status: "pending" | "uploading" | "done" | "error";
  message?: string;
}

export function DocumentsTab() {
  const [documents, setDocuments] = useState<DocumentResponse[]>([]);
  const [queue, setQueue] = useState<UploadQueueItem[]>([]);
  const [dragActive, setDragActive] = useState(false);
  const [projects, setProjects] = useState<ProjectResponse[]>([]);
  // Which project the uploaded document belongs to. Retrieval filters on this, and
  // conflict detection only compares documents within the same project.
  const [projectId, setProjectId] = useState<string>("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const uploading = queue.some((item) => item.status === "pending" || item.status === "uploading");

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

  // Uploaded one at a time, in order — the backend does synchronous work per file (parse,
  // prompt-injection scan, classify, embed), so firing them all in parallel would pile
  // several of those onto the server/LLM API at once for no real benefit; sequential keeps
  // each file's progress legible in the queue below and is no slower in practice for the
  // handful of files an Admin drags in at once.
  const processQueue = useCallback(
    async (items: UploadQueueItem[]) => {
      for (const item of items) {
        if (!isSupportedFile(item.file)) {
          setQueue((prev) =>
            prev.map((q) =>
              q.id === item.id
                ? { ...q, status: "error", message: `Không hỗ trợ "${item.file.name}". Chỉ nhận PDF hoặc DOCX.` }
                : q,
            ),
          );
          continue;
        }

        setQueue((prev) => prev.map((q) => (q.id === item.id ? { ...q, status: "uploading" } : q)));

        try {
          const formData = new FormData();
          formData.append("file", item.file);
          formData.append("visibility", "internal");
          // Without a project the document cannot be filtered per project at retrieval
          // time, and conflict detection has nothing to compare it against.
          if (projectId) formData.append("project_id", projectId);

          const result = await api.postForm<UploadResponse>("/documents/upload", formData);

          setQueue((prev) =>
            prev.map((q) =>
              q.id === item.id
                ? result.status === "completed"
                  ? { ...q, status: "done" }
                  : { ...q, status: "error", message: result.message }
                : q,
            ),
          );
        } catch (err) {
          setQueue((prev) =>
            prev.map((q) =>
              q.id === item.id
                ? { ...q, status: "error", message: err instanceof Error ? err.message : "Upload tài liệu thất bại." }
                : q,
            ),
          );
        }

        loadDocuments();
      }
    },
    [projectId, loadDocuments],
  );

  const handleFiles = (files: FileList | null) => {
    if (!files || files.length === 0) {
      return;
    }

    const items: UploadQueueItem[] = Array.from(files).map((file, index) => ({
      id: `${Date.now()}-${index}-${file.name}`,
      file,
      status: "pending",
    }));
    setQueue((prev) => [...prev, ...items]);
    void processQueue(items);
  };

  const clearFinishedQueue = () => {
    setQueue((prev) => prev.filter((item) => item.status === "pending" || item.status === "uploading"));
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

  const viewDocument = async (documentId: number) => {
    const { url } = await api.get<{ url: string }>(`/documents/${documentId}/view-url`);
    window.open(url, "_blank", "noopener,noreferrer");
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
        Tải PDF/DOCX để hệ thống đọc hiểu và đưa vào kho tri thức, giúp AI trả lời khách chính xác hơn.
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
          multiple
          accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document"
          onChange={(event) => {
            handleFiles(event.target.files);
            // Without this, picking the same file(s) again right after (e.g. to retry
            // one that failed) fires no "change" event — the browser dedupes an
            // unchanged file list against its own last value.
            event.target.value = "";
          }}
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
            ? "Đang xử lý và đưa vào kho tri thức..."
            : "Kéo thả tài liệu vào đây"}
        </p>

        <p className="upload-zone-hint">
          hoặc bấm để chọn từ máy tính · hỗ trợ PDF và DOCX · chọn/thả được nhiều file cùng lúc
        </p>
      </div>

      {queue.length > 0 && (
        <div className="upload-queue">
          {queue.map((item) => (
            <div key={item.id} className={`upload-queue-item upload-queue-item--${item.status}`}>
              <span className="upload-queue-item-icon">
                {item.status === "pending" || item.status === "uploading" ? (
                  <LoaderIcon size={14} className="icon-spin" />
                ) : item.status === "done" ? (
                  <CheckIcon size={14} />
                ) : (
                  <AlertIcon size={14} />
                )}
              </span>
              <span className="upload-queue-item-name">{item.file.name}</span>
              {item.message && <span className="upload-queue-item-msg">{item.message}</span>}
            </div>
          ))}
          {!uploading && (
            <button type="button" className="btn btn-sm btn-ghost upload-queue-clear" onClick={clearFinishedQueue}>
              <XIcon size={13} />
              Xóa danh sách
            </button>
          )}
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
                    {document.file_path ? (
                      <button
                        type="button"
                        className="data-row-title data-row-title--link"
                        onClick={() => void viewDocument(document.id)}
                      >
                        {document.title}
                      </button>
                    ) : (
                      <div className="data-row-title">{document.title}</div>
                    )}
                    <div className="data-row-meta">
                      {parseServerDate(document.created_at).toLocaleString("vi-VN")}
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