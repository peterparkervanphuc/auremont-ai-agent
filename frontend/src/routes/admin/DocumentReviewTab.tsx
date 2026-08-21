import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import type {
  DocumentCategory,
  DocumentClassificationUpdate,
  DocumentReclassificationUpdate,
  DocumentResponse,
  LegalStatus,
  ProjectResponse,
} from "../../types";
import { CheckIcon, InboxIcon, LoaderIcon } from "../../components/Icons";

const CATEGORIES: Array<[DocumentCategory, string]> = [
  ["sales_policy", "Chính sách bán hàng"],
  ["price_list", "Bảng giá"],
  ["inventory_snapshot", "Giỏ hàng / tồn kho"],
  ["subdivision_info", "Thông tin phân khu"],
  ["building_info", "Thông tin tòa"],
  ["floor_plan", "Mặt bằng"],
  ["payment_schedule", "Tiến độ thanh toán"],
  ["promotion", "Ưu đãi / khuyến mại"],
  ["legal_document", "Tài liệu pháp lý"],
  ["contract_template", "Hợp đồng / biểu mẫu"],
  ["internal_guide", "Tài liệu nội bộ"],
  ["other", "Khác"],
];

function asText(values: string[] | null): string {
  return values?.join(", ") ?? "";
}

type ScopeField = "subdivision_names" | "building_codes" | "unit_types";

type ScopeText = Record<ScopeField, string>;
type ProjectCatalogItem = Pick<ProjectResponse, "id" | "name" | "location">;

function scopeTextFrom(document: DocumentResponse): ScopeText {
  return {
    subdivision_names: asText(document.subdivision_names),
    building_codes: asText(document.building_codes),
    unit_types: asText(document.unit_types),
  };
}

function asList(value: string): string[] | null {
  const values = [...new Set(value.split(",").map((item) => item.trim()).filter(Boolean))];
  return values.length > 0 ? values : null;
}

function sameList(left: string[] | null, right: string[] | null): boolean {
  return (left ?? []).join("\u0000") === (right ?? []).join("\u0000");
}

function hasStructuralChanges(
  document: DocumentResponse,
  draft: DocumentReclassificationUpdate,
): boolean {
  return document.category !== draft.category
    || document.project_id !== draft.project_id
    || !sameList(document.subdivision_names, draft.subdivision_names)
    || !sameList(document.building_codes, draft.building_codes)
    || !sameList(document.unit_types, draft.unit_types);
}

function withoutProjectId({
  project_id: _projectId,
  ...payload
}: DocumentReclassificationUpdate): DocumentClassificationUpdate {
  return payload;
}

function payloadFrom(document: DocumentResponse): DocumentReclassificationUpdate {
  return {
    project_id: document.project_id,
    category: document.category,
    subcategory: document.subcategory,
    subdivision_names: document.subdivision_names,
    building_codes: document.building_codes,
    unit_types: document.unit_types,
    applicable_area: document.applicable_area,
    document_summary: document.document_summary,
    version_label: document.version_label,
    issued_date: document.issued_date,
    effective_date: document.effective_date,
    expiry_date: document.expiry_date,
    applicable_period: document.applicable_period,
    legal_document_type: document.legal_document_type,
    legal_document_number: document.legal_document_number,
    legal_issuer: document.legal_issuer,
    legal_domain: document.legal_domain,
    legal_status: document.legal_status,
  };
}

export function DocumentReviewTab() {
  const [documents, setDocuments] = useState<DocumentResponse[]>([]);
  const [projects, setProjects] = useState<ProjectCatalogItem[]>([]);
  const [selected, setSelected] = useState<DocumentResponse | null>(null);
  const [draft, setDraft] = useState<DocumentReclassificationUpdate | null>(null);
  const [scopeText, setScopeText] = useState<ScopeText>({
    subdivision_names: "",
    building_codes: "",
    unit_types: "",
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [list, projectList] = await Promise.all([
        api.get<DocumentResponse[]>("/documents/metadata-editable"),
        api.get<ProjectCatalogItem[]>("/documents/project-catalog"),
      ]);
      setDocuments(list);
      setProjects(projectList);
      setSelected((current) => list.find((item) => item.id === current?.id) ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được danh sách tài liệu.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const select = (document: DocumentResponse) => {
    setSelected(document);
    setDraft(payloadFrom(document));
    setScopeText(scopeTextFrom(document));
    setError(null);
  };

  const update = <K extends keyof DocumentReclassificationUpdate>(key: K, value: DocumentReclassificationUpdate[K]) => {
    setDraft((current) => current ? { ...current, [key]: value } : current);
  };

  const updateScope = (key: ScopeField, value: string) => {
    setScopeText((current) => ({ ...current, [key]: value }));
    update(key, asList(value));
  };

  const save = async () => {
    if (!selected || !draft) return;
    setSaving(true);
    setError(null);
    try {
      if (hasStructuralChanges(selected, draft)) {
        await api.post<DocumentResponse>(`/documents/${selected.id}/reclassify`, draft);
      } else {
        await api.patch<DocumentResponse>(
          `/documents/${selected.id}/classification`,
          withoutProjectId(draft),
        );
      }
      setDocuments((current) => current.filter((item) => item.id !== selected.id));
      setSelected(null);
      setDraft(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không lưu được thay đổi.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="page">
      <h2 className="page-title">Metadata tài liệu</h2>
      <p className="page-sub">Kết quả LLM đủ tin cậy được duyệt tự động. Tài liệu có bằng chứng mơ hồ hoặc điểm tin cậy thấp sẽ được cách ly tại đây và chỉ được AI sử dụng sau khi Admin xác nhận. Riêng <strong>Trạng thái pháp lý</strong> hết hiệu lực / bị bãi bỏ / bị thay thế luôn đưa tài liệu ra khỏi phạm vi trả lời.</p>

      {error && <div className="alert alert-danger" style={{ marginTop: 16 }}>{error}</div>}

      {loading ? (
        <div className="empty-state"><LoaderIcon size={24} className="icon-spin" /><p>Đang tải tài liệu…</p></div>
      ) : documents.length === 0 ? (
        <div className="empty-state"><div className="empty-state-icon"><InboxIcon size={26} /></div><p>Chưa có tài liệu nào đã ingest xong.</p></div>
      ) : (
        <div className="review-layout">
          <div className="data-list review-list">
            {documents.map((document) => (
              <button className={`review-item ${selected?.id === document.id ? "review-item--active" : ""}`} type="button" key={document.id} onClick={() => select(document)}>
                <span className="data-row-title">{document.title}</span>
                <span className="data-row-meta">
                  {CATEGORIES.find(([key]) => key === document.category)?.[1] ?? "Khác"} · {document.classification_confidence !== null ? `${Math.round(document.classification_confidence * 100)}%` : "Chưa rõ"} · {document.review_status === "pending" ? "Cần duyệt" : "Đã duyệt"}
                </span>
              </button>
            ))}
          </div>

          {selected && draft && (
            <section className="review-form">
              <h3 className="section-title">{selected.title}</h3>
              <p className="review-reason">
                Project: <strong>{selected.project_id ?? "Chưa xác định"}</strong> · Bộ phân loại: <strong>{selected.classification_version ?? "Legacy"}</strong>
                {selected.classification_requires_admin_review ? " · LLM yêu cầu Admin kiểm tra" : ""}
              </p>
              {selected.classification_reason && <p className="review-reason">Đề xuất hệ thống: {selected.classification_reason}</p>}
              <p className="review-reason">
                Thay đổi dự án, loại tài liệu hoặc phạm vi conflict sẽ chạy lại luồng xử lý an toàn:
                cách ly tài liệu, lập chỉ mục lại khi cần và quét mâu thuẫn trước khi cho AI sử dụng.
              </p>
              <div className="review-grid">
                <label>Dự án<select value={draft.project_id ?? ""} onChange={(event) => update("project_id", event.target.value || null)}>
                  <option value="">Không gắn dự án</option>
                  {draft.project_id && !projects.some((project) => project.id === draft.project_id) && (
                    <option value={draft.project_id}>{draft.project_id}</option>
                  )}
                  {projects.map((project) => <option key={project.id} value={project.id}>{project.name}</option>)}
                </select></label>
                <label>Loại tài liệu<select value={draft.category} onChange={(event) => update("category", event.target.value as DocumentCategory)}>{CATEGORIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
                <label>Phân loại phụ<input value={draft.subcategory ?? ""} onChange={(event) => update("subcategory", event.target.value || null)} /></label>
                <label>Phân khu<input value={scopeText.subdivision_names} placeholder="Phân cách bằng dấu phẩy" onChange={(event) => updateScope("subdivision_names", event.target.value)} /></label>
                <label>Tòa / block<input value={scopeText.building_codes} placeholder="Phân cách bằng dấu phẩy" onChange={(event) => updateScope("building_codes", event.target.value)} /></label>
                <label>Loại căn<input value={scopeText.unit_types} placeholder="Phân cách bằng dấu phẩy" onChange={(event) => updateScope("unit_types", event.target.value)} /></label>
                <label>Phạm vi áp dụng<input value={draft.applicable_area ?? ""} onChange={(event) => update("applicable_area", event.target.value || null)} /></label>
                <label>Hiệu lực từ<input type="date" value={draft.effective_date ?? ""} onChange={(event) => update("effective_date", event.target.value || null)} /></label>
                <label>Hết hiệu lực<input type="date" value={draft.expiry_date ?? ""} onChange={(event) => update("expiry_date", event.target.value || null)} /></label>
                <label>Phiên bản<input value={draft.version_label ?? ""} onChange={(event) => update("version_label", event.target.value || null)} /></label>
                <label>Kỳ áp dụng<input value={draft.applicable_period ?? ""} onChange={(event) => update("applicable_period", event.target.value || null)} /></label>
              </div>

              {draft.category === "legal_document" && <div className="review-grid review-grid--legal">
                <label>Loại văn bản<input value={draft.legal_document_type ?? ""} onChange={(event) => update("legal_document_type", event.target.value || null)} /></label>
                <label>Số hiệu<input value={draft.legal_document_number ?? ""} onChange={(event) => update("legal_document_number", event.target.value || null)} /></label>
                <label>Cơ quan ban hành<input value={draft.legal_issuer ?? ""} onChange={(event) => update("legal_issuer", event.target.value || null)} /></label>
                <label>Lĩnh vực<input value={draft.legal_domain ?? ""} onChange={(event) => update("legal_domain", event.target.value || null)} /></label>
                <label>Trạng thái pháp lý<select value={draft.legal_status} onChange={(event) => update("legal_status", event.target.value as LegalStatus)}><option value="unknown">Chưa xác định</option><option value="not_yet_effective">Chưa hiệu lực</option><option value="effective">Đang hiệu lực</option><option value="expired">Hết hiệu lực</option><option value="repealed">Bị bãi bỏ</option><option value="replaced">Bị thay thế</option></select></label>
              </div>}

              <label className="review-summary">Tóm tắt<textarea value={draft.document_summary ?? ""} onChange={(event) => update("document_summary", event.target.value || null)} rows={4} /></label>
              <button className="btn btn-primary" type="button" onClick={() => void save()} disabled={saving}>{saving ? <LoaderIcon size={16} className="icon-spin" /> : <CheckIcon size={16} />} {["expired", "repealed", "replaced"].includes(draft.legal_status) ? "Lưu và đưa ra khỏi phạm vi AI" : selected.review_status === "pending" ? "Xác nhận và cho phép AI sử dụng" : "Lưu thay đổi"}</button>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
