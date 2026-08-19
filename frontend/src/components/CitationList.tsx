import { useState } from "react";
import type { Citation } from "../types";
import { DocumentIcon } from "./Icons";
import { fetchDocumentViewUrl } from "../api/projects";

interface Props {
  citations: Citation[];
  /** Wrapper class — the chat bubble and the HITL card lay this row out differently. */
  className: string;
  label: string;
}

// Source chips under an answer: one per file.
//
// The de-duplication is repeated here even though the backend already collapses
// citations per file, because messages stored before that change still hold one entry
// per chunk — five rows of the same PDF name — and reopening an old conversation
// renders whatever was saved. Doing it at render time fixes the history too.
export function CitationList({ citations, className, label }: Props) {
  const [loadingId, setLoadingId] = useState<number | null>(null);

  const seen = new Set<string>();
  const unique = citations.filter((c) => {
    const key = c.title.trim().toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  if (unique.length === 0) return null;

  const openDocument = async (documentId: number) => {
    if (loadingId !== null) return;
    setLoadingId(documentId);
    try {
      const url = await fetchDocumentViewUrl(documentId);
      window.open(url, "_blank", "noopener,noreferrer");
    } catch {
      // The signed link can fail to generate (file moved, storage hiccup) — worth a
      // console trace for support, not worth a chat bubble interrupting the answer.
      console.error("Không mở được tài liệu.");
    } finally {
      setLoadingId(null);
    }
  };

  return (
    <div className={className}>
      <span className="chat-citations-label">{label}</span>
      {unique.map((c) => (
        <button
          key={c.title}
          type="button"
          className="chat-citation"
          onClick={() => openDocument(c.document_id)}
          disabled={loadingId === c.document_id}
        >
          <DocumentIcon size={12} />
          {c.title}
        </button>
      ))}
    </div>
  );
}
