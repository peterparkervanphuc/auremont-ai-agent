import { useCallback, useEffect, useState } from "react";
import { api } from "../../api/client";
import type {
  DocumentCategory,
  DocumentClassificationUpdate,
  DocumentResponse,
  LegalStatus,
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

function payloadFrom(document: DocumentResponse): DocumentClassificationUpdate {
  return {
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
  const [selected, setSelected] = useState<DocumentResponse | null>(null);
  const [draft, setDraft] = useState<DocumentClassificationUpdate | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const list = await api.get<DocumentResponse[]>("/documents/pending-review");
      setDocuments(list);
      setSelected((current) => list.find((item) => item.id === current?.id) ?? null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được danh sách chờ duyệt.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const select = (document: DocumentResponse) => {
    setSelected(document);
    setDraft(payloadFrom(document));
    setError(null);
  };

  const update = <K extends keyof DocumentClassificationUpdate>(key: K, value: DocumentClassificationUpdate[K]) => {
    setDraft((current) => current ? { ...current, [key]: value } : current);
  };

  const approve = async () => {
    if (!selected || !draft) return;
    setSaving(true);
    setError(null);
    try {
      await api.patch<DocumentResponse>(`/documents/${selected.id}/classification`, draft);
      setDocuments((current) => current.filter((item) => item.id !== selected.id));
      setSelected(null);
      setDraft(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thể duyệt tài liệu.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="page">
      <h2 className="page-title">Chờ duyệt tài liệu</h2>
      <p className="page-sub">Kiểm tra đề xuất phân loại trước khi tài liệu được AI dùng để trả lời.</p>

      {error && <div className="alert alert-danger" style={{ marginTop: 16 }}>{error}</div>}

      {loading ? (
        <div className="empty-state"><LoaderIcon size={24} className="icon-spin" /><p>Đang tải tài liệu…</p></div>
      ) : documents.length === 0 ? (
        <div className="empty-state"><div className="empty-state-icon"><InboxIcon size={26} /></div><p>Không có tài liệu nào chờ duyệt.</p></div>
      ) : (
        <div className="review-layout">
          <div className="data-list review-list">
            {documents.map((document) => (
              <button className={`review-item ${selected?.id === document.id ? "review-item--active" : ""}`} type="button" key={document.id} onClick={() => select(document)}>
                <span className="data-row-title">{document.title}</span>
                <span className="data-row-meta">{CATEGORIES.find(([key]) => key === document.category)?.[1] ?? "Khác"} · {document.classification_confidence ? `${Math.round(document.classification_confidence * 100)}%` : "Chưa rõ"}</span>
              </button>
            ))}
          </div>

          {selected && draft && (
            <section className="review-form">
              <h3 className="section-title">{selected.title}</h3>
              {selected.classification_reason && <p className="review-reason">Đề xuất hệ thống: {selected.classification_reason}</p>}
              <p className="review-reason">
                Loại tài liệu và phạm vi conflict được khóa ở bước duyệt. Nếu các trường này sai,
                hãy giữ tài liệu trong quarantine và chạy quy trình re-index/rescan thay vì chỉ đổi metadata.
              </p>
              <div className="review-grid">
                <label>Loại tài liệu<select value={draft.category} disabled>{CATEGORIES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
                <label>Phân loại phụ<input value={draft.subcategory ?? ""} onChange={(event) => update("subcategory", event.target.value || null)} /></label>
                <label>Phân khu<input value={asText(draft.subdivision_names)} readOnly /></label>
                <label>Tòa / block<input value={asText(draft.building_codes)} readOnly /></label>
                <label>Loại căn<input value={asText(draft.unit_types)} readOnly /></label>
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
              <button className="btn btn-primary" type="button" onClick={() => void approve()} disabled={saving}>{saving ? <LoaderIcon size={16} className="icon-spin" /> : <CheckIcon size={16} />} {draft.category === "legal_document" && ["expired", "repealed", "replaced"].includes(draft.legal_status) ? "Duyệt và giữ ngoài RAG" : "Duyệt và cho phép AI sử dụng"}</button>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
