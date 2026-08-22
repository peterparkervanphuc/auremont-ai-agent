import { useState } from "react";
import type { PropertyListing } from "../types";
import { ChevronLeftIcon, ChevronRightIcon, HomeIcon } from "../components/Icons";

interface Props {
  listings: PropertyListing[];
}

// One recommended unit at a time, with paging arrows between cards — the numeric details
// (loại căn/diện tích/giá) used to be bullet lines inside the answer's own text; they now
// live here instead, so the chat bubble stays a short 1-2 sentence recommendation and the
// actual figures get a card of their own. `image_url` is resolved server-side (see
// agent_pipeline._resolve_listing_images) from the project's own gallery — never a photo
// of the specific unit, since no such photo exists in the catalogue — so a null falls back
// to a plain icon tile instead of a broken image.
export function PropertyListingCarousel({ listings }: Props) {
  const [index, setIndex] = useState(0);
  const [broken, setBroken] = useState<Set<number>>(new Set());

  if (listings.length === 0) return null;

  const current = listings[index];
  const hasImage = Boolean(current.image_url) && !broken.has(index);
  const canGoBack = index > 0;
  const canGoForward = index < listings.length - 1;

  return (
    <div className="listing-carousel">
      <div className="listing-card">
        {hasImage ? (
          <img
            className="listing-card-image"
            src={current.image_url ?? undefined}
            alt={current.project_name}
            loading="lazy"
            onError={() => setBroken((prev) => new Set(prev).add(index))}
          />
        ) : (
          <div className="listing-card-image listing-card-image--placeholder">
            <HomeIcon size={36} />
          </div>
        )}

        <div className="listing-card-body">
          <p className="listing-card-title">{current.project_name}</p>
          <p className="listing-card-meta">
            {current.unit_type} · {current.area_range}
          </p>
          <p className="listing-card-price">{current.price_range}</p>
        </div>

        {listings.length > 1 && (
          <div className="listing-carousel-nav">
            <button
              type="button"
              className="listing-carousel-arrow"
              disabled={!canGoBack}
              onClick={() => setIndex((i) => i - 1)}
              aria-label="Căn trước"
            >
              <ChevronLeftIcon size={16} />
            </button>
            <div className="listing-carousel-dots">
              {listings.map((listing, i) => (
                <span
                  key={`${listing.project_name}-${listing.unit_type}-${i}`}
                  className={`listing-carousel-dot ${i === index ? "listing-carousel-dot--active" : ""}`}
                />
              ))}
            </div>
            <button
              type="button"
              className="listing-carousel-arrow"
              disabled={!canGoForward}
              onClick={() => setIndex((i) => i + 1)}
              aria-label="Căn tiếp theo"
            >
              <ChevronRightIcon size={16} />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
