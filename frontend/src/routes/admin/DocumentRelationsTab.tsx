import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../../api/client";
import type { DocumentRelationResponse, DocumentRelationType, DocumentResponse } from "../../types";
import { CheckIcon, LoaderIcon, XIcon } from "../../components/Icons";

const RELATIONS: Array<[DocumentRelationType, string]> = [
  ["replaces", "Thay thế hoàn toàn"],
  ["supersedes", "Thay phiên bản cũ"],
  ["updates", "Cập nhật"],
  ["amends", "Sửa đổi / bổ sung"],
  ["repeals", "Bãi bỏ"],
  ["guides", "Hướng dẫn thi hành"],
  ["related_to", "Liên quan"],
];

export function DocumentRelationsTab() {
  const [documents, setDocuments] = useState<DocumentResponse[]>([]);
  const [relations, setRelations] = useState<DocumentRelationResponse[]>([]);
  const [sourceId, setSourceId] = useState("");
  const [targetId, setTargetId] = useState("");
  const [relationType, setRelationType] = useState<DocumentRelationType>("replaces");
  const [scopeNote, setScopeNote] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const names = useMemo(() => new Map(documents.map((item) => [item.id, item.title])), [documents]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [documentList, relationList] = await Promise.all([
        api.get<DocumentResponse[]>("/documents"),
        api.get<DocumentRelationResponse[]>("/document-relations?pending_only=true"),
      ]);
      setDocuments(documentList);
      setRelations(relationList);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tải được quan hệ tài liệu.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const create = async () => {
    if (!sourceId || !targetId) {
      setError("Hãy chọn cả tài liệu mới và tài liệu cũ.");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const relation = await api.post<DocumentRelationResponse>("/document-relations", {
        source_document_id: Number(sourceId),
        target_document_id: Number(targetId),
        relation_type: relationType,
        scope_note: scopeNote || null,
      });
      setRelations((current) => [relation, ...current]);
      setTargetId("");
      setScopeNote("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không tạo được quan hệ.");
    } finally {
      setSaving(false);
    }
  };

  const review = async (relationId: number, approve: boolean) => {
    setSaving(true);
    setError(null);
    try {
      await api.post<DocumentRelationResponse>(`/document-relations/${relationId}/review`, { approve });
      setRelations((current) => current.filter((item) => item.id !== relationId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không thể xử lý quan hệ này.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="page">
      <h2 className="page-title">Quan hệ tài liệu</h2>
      <p className="page-sub">Xác nhận bản mới cập nhật, thay thế hoặc bãi bỏ bản cũ. Bản cũ sẽ tự bị loại khỏi RAG khi quan hệ được duyệt.</p>
      {error && <div className="alert alert-danger" style={{ marginTop: 16 }}>{error}</div>}

      <section className="review-form" style={{ marginTop: 24 }}>
        <h3 className="section-title">Tạo quan hệ mới</h3>
        <div className="review-grid">
          <label>Tài liệu mới<select value={sourceId} onChange={(event) => setSourceId(event.target.value)}><option value="">— Chọn tài liệu —</option>{documents.map((doc) => <option key={doc.id} value={doc.id}>{doc.title}</option>)}</select></label>
          <label>Tài liệu cũ<select value={targetId} onChange={(event) => setTargetId(event.target.value)}><option value="">— Chọn tài liệu —</option>{documents.filter((doc) => String(doc.id) !== sourceId).map((doc) => <option key={doc.id} value={doc.id}>{doc.title}</option>)}</select></label>
          <label>Loại quan hệ<select value={relationType} onChange={(event) => setRelationType(event.target.value as DocumentRelationType)}>{RELATIONS.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
          <label>Phạm vi / ghi chú<input value={scopeNote} onChange={(event) => setScopeNote(event.target.value)} placeholder="Ví dụ: chỉ áp dụng phân khu The Beverly" /></label>
        </div>
        <button className="btn btn-primary" type="button" onClick={() => void create()} disabled={saving}>{saving && <LoaderIcon size={16} className="icon-spin" />} Tạo quan hệ chờ duyệt</button>
      </section>

      <div style={{ marginTop: 28 }}>
        <h3 className="section-title">Quan hệ chờ duyệt</h3>
        {loading ? <div className="empty-state"><LoaderIcon size={24} className="icon-spin" /></div> : relations.length === 0 ? <div className="empty-state"><p>Không có quan hệ nào chờ duyệt.</p></div> : <div className="data-list">
          {relations.map((relation) => <div className="conflict-card" key={relation.id}>
            <div className="conflict-card-head">{RELATIONS.find(([value]) => value === relation.relation_type)?.[1] ?? relation.relation_type}</div>
            <div className="conflict-pair"><div className="conflict-doc"><div className="conflict-doc-meta">Tài liệu mới</div><div className="conflict-doc-name">{names.get(relation.source_document_id) ?? `#${relation.source_document_id}`}</div></div><div className="conflict-doc"><div className="conflict-doc-meta">Tài liệu cũ</div><div className="conflict-doc-name">{names.get(relation.target_document_id) ?? `#${relation.target_document_id}`}</div></div></div>
            {relation.scope_note && <p className="review-reason">{relation.scope_note}</p>}
            <div className="conflict-actions"><button className="btn btn-primary" type="button" disabled={saving} onClick={() => void review(relation.id, true)}><CheckIcon size={16} /> Duyệt</button><button className="btn btn-danger" type="button" disabled={saving} onClick={() => void review(relation.id, false)}><XIcon size={16} /> Bác bỏ</button></div>
          </div>)}
        </div>}
      </div>
    </div>
  );
}
