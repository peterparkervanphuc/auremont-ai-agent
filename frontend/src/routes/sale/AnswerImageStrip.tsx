import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import type { AnswerImage } from "../../types";

interface Props {
  images: AnswerImage[];
}

// Photos of the project an answer is about, shown as a row of thumbnails under it.
// Capped at four by the backend, so they fit without needing arrows — the row still
// scrolls horizontally on a narrow phone, where touch handles it natively.
//
// Tapping one opens it full-size over the chat rather than in a new tab: the Sale is
// mid-conversation with a customer and must not lose the thread to a browser tab.
export function AnswerImageStrip({ images }: Props) {
  const [broken, setBroken] = useState<Set<string>>(new Set());
  const [zoomed, setZoomed] = useState<AnswerImage | null>(null);

  // Escape closes the overlay, matching what every other lightbox does. Bound only
  // while one is open so the chat keeps its own key handling the rest of the time.
  useEffect(() => {
    if (!zoomed) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setZoomed(null);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [zoomed]);

  // A gallery URL can 404 (an image removed from MinIO after the answer was stored).
  // Dropping just that thumbnail beats showing the browser's broken-image glyph to a
  // customer, and the strip disappears entirely once nothing is left to show.
  const visible = images.filter((image) => !broken.has(image.url));
  if (visible.length === 0) return null;

  return (
    <div className="answer-images">
      <span className="answer-images-label">Hình ảnh {visible[0].project_name}</span>

      <div className="answer-images-track">
        {visible.map((image) => (
          <button
            key={image.url}
            type="button"
            className="answer-image-card"
            onClick={() => setZoomed(image)}
            title={`Phóng to ảnh ${image.project_name}`}
          >
            <img
              src={image.url}
              alt={image.project_name}
              loading="lazy"
              onError={() => setBroken((prev) => new Set(prev).add(image.url))}
            />
          </button>
        ))}
      </div>

      {/* Rendered into <body>, not in place: `.chat-message` keeps a `translateX(0)` from
          its entry animation (animation-fill-mode: both), and any transform other than
          `none` makes the element a containing block for `position: fixed` descendants —
          an inline overlay would be clipped to the message bubble instead of the viewport. */}
      {zoomed &&
        createPortal(
          // The click handler sits on the backdrop and the image stops propagation, so
          // clicking outside the photo closes it while clicking the photo itself does not.
          <div className="image-lightbox" onClick={() => setZoomed(null)} role="presentation">
            <img src={zoomed.url} alt={zoomed.project_name} onClick={(e) => e.stopPropagation()} />
          </div>,
          document.body,
        )}
    </div>
  );
}
