import type { Citation } from "../types";
import { DocumentIcon } from "./Icons";

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
  const seen = new Set<string>();
  const unique = citations.filter((c) => {
    const key = c.title.trim().toLowerCase();
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  if (unique.length === 0) return null;

  return (
    <div className={className}>
      <span className="chat-citations-label">{label}</span>
      {unique.map((c) => (
        <span key={c.title} className="chat-citation">
          <DocumentIcon size={12} />
          {c.title}
        </span>
      ))}
    </div>
  );
}
