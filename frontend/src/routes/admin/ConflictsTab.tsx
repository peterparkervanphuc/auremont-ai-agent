import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../../api/client";
import { AlertIcon, CheckIcon, ExternalLinkIcon, ScaleIcon } from "../../components/Icons";
import type { ConflictDetail, ConflictDocumentSummary } from "../../types/admin";
import { parseServerDate } from "../../utils/datetime";

function DocumentPane({ label, document, conflict, onOpen }: { label: string; document: ConflictDocumentSummary; conflict: string | null; onOpen: () => void }) {
  return <article className="conflict-document-pane">
    <header><span>{label}</span><button type="button" className="admin-icon-button" onClick={onOpen} aria-label={`Mở ${document.title}`}><ExternalLinkIcon size={16} /></button></header>
    <div className="conflict-document-body">
      <div className="conflict-document-title"><small>Tài liệu #{document.id}</small><h3>{document.title}</h3></div>
      <dl className="conflict-document-meta"><div><dt>Phiên bản</dt><dd>{document.version_label ?? "Không ghi nhận"}</dd></div><div><dt>Hiệu lực</dt><dd>{document.effective_date ?? document.issued_date ?? "Không ghi nhận"}</dd></div><div><dt>Phân loại</dt><dd>{document.category}</dd></div><div><dt>Quyền xem</dt><dd>{document.visibility}</dd></div></dl>
      <div className="conflict-copy"><span>Tóm tắt nguồn</span><p>{document.summary ?? document.classification_reason ?? "Tài liệu chưa có bản tóm tắt để hiển thị."}</p></div>
      <div className="conflict-highlight"><span>Nội dung được đánh dấu mâu thuẫn</span><mark>{conflict ?? "Hệ thống ghi nhận hai tài liệu có thông tin không nhất quán."}</mark></div>
    </div>
  </article>;
}

export function ConflictsTab() {
  const [conflicts, setConflicts] = useState<ConflictDetail[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resolving, setResolving] = useState<number | null>(null);
  const [manualId, setManualId] = useState<number | null>(null);

  useEffect(() => {
    api.get<ConflictDetail[]>("/admin/conflicts").then((rows) => { setConflicts(rows); setError(null); }).catch(() => { setError("Không tải được danh sách mâu thuẫn."); setConflicts([]); });
  }, []);

  const resolve = async (conflictId: number, keepDocumentId: number) => {
    setError(null);
    setResolving(conflictId);
    try {
      await api.post(`/admin/conflicts/${conflictId}/resolve`, { keep_document_id: keepDocumentId });
      setConflicts((previous) => previous?.filter((conflict) => conflict.id !== conflictId) ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không xử lý được mâu thuẫn này.");
    } finally {
      setResolving(null);
    }
  };

  const openDocument = async (documentId: number) => {
    try {
      const { url } = await api.get<{ url: string }>(`/documents/${documentId}/view-url`);
      window.open(url, "_blank", "noopener,noreferrer");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Không mở được tài liệu.");
    }
  };

  return <div className="page admin-dashboard-page">
    <header className="admin-page-head"><div><span className="admin-eyebrow">Knowledge governance</span><h1 className="page-title">Cảnh báo mâu thuẫn tài liệu</h1><p className="page-sub">So sánh hai nguồn độc lập trước khi quyết định phiên bản được phép tham gia RAG.</p></div></header>
    {error && <div className="alert alert-danger">{error}</div>}
    {conflicts === null ? <div className="admin-empty">Đang tải cảnh báo…</div> : conflicts.length === 0 ? <div className="empty-state"><div className="empty-state-icon"><CheckIcon size={26} /></div><p>Không có mâu thuẫn nào cần xử lý.</p></div> : <div className="conflict-list">{conflicts.map((conflict) => <section className="conflict-compare" key={conflict.id}>
      <header className="conflict-compare-head"><div><span className="conflict-alert-title"><AlertIcon size={17} /> Conflict #{conflict.id}</span><h2>{conflict.project_name ?? conflict.project_id ?? "Tài liệu áp dụng chung"}</h2></div><div className="conflict-badges"><span>Similarity: {conflict.similarity_score == null ? "Chưa đo" : `${Math.round(conflict.similarity_score * 100)}%`}</span><span>Phát hiện {parseServerDate(conflict.created_at).toLocaleDateString("vi-VN")}</span><span>{conflict.project_name ?? "Toàn hệ thống"}</span></div></header>
      <div className="conflict-split"><DocumentPane label="Tài liệu A · nguồn cũ" document={conflict.document_a} conflict={conflict.description} onOpen={() => void openDocument(conflict.document_a.id)} /><DocumentPane label="Tài liệu B · nguồn mới" document={conflict.document_b} conflict={conflict.description} onOpen={() => void openDocument(conflict.document_b.id)} /></div>
      {manualId === conflict.id && <div className="manual-merge-note"><ScaleIcon size={19} /><div><strong>Quy trình gộp/chỉnh sửa thủ công</strong><p>Mở hai bản nguồn, tạo hoặc tải bản đã chỉnh sửa vào Kho tài liệu, rồi quay lại chọn tài liệu thắng. Cảnh báo vẫn mở để không vô tình đưa hai nguồn mâu thuẫn vào retrieval.</p></div><div><button className="btn btn-sm btn-outline" onClick={() => void openDocument(conflict.document_a.id)}>Mở A</button><button className="btn btn-sm btn-outline" onClick={() => void openDocument(conflict.document_b.id)}>Mở B</button><Link className="btn btn-sm btn-primary" to="/documents">Đến Kho tài liệu</Link></div></div>}
      <footer className="conflict-compare-actions"><span>Chọn một nguồn sẽ chặn nguồn còn lại khỏi RAG.</span><div><button className="btn btn-outline" type="button" disabled={resolving === conflict.id} onClick={() => void resolve(conflict.id, conflict.document_a.id)}>Chấp nhận Bản A</button><button className="btn btn-primary" type="button" disabled={resolving === conflict.id} onClick={() => void resolve(conflict.id, conflict.document_b.id)}>Chấp nhận Bản B</button><button className="btn btn-outline" type="button" onClick={() => setManualId((value) => value === conflict.id ? null : conflict.id)}><ScaleIcon size={15} /> Gộp/Chỉnh sửa thủ công</button></div></footer>
    </section>)}</div>}
  </div>;
}
