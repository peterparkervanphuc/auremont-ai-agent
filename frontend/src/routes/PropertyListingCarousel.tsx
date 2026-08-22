import { useState } from "react";
import type { PropertyListing } from "../types";
import { ChevronLeftIcon, ChevronRightIcon, HomeIcon } from "../components/Icons";

interface Props {
  listings: PropertyListing[];
}

// One recommended unit at a time, with paging arrows between cards — the numeric details
// (loại căn/diện tích/giá) used to be bullet lines inside the answer's own text; they now
// live here instead, so the chat bubble stays a short 1-2 sentence recommendation and the
// actual figures get a card of their own. `image_urls`/`amenities` are resolved
// server-side (see agent_pipeline._resolve_listing_images/select_listing_images): a floor
// plan when the catalogue tags one for this unit type, the subdivision's own overview
// shots otherwise — never a photo of the specific unit, since no such photo exists in the
// catalogue. Falls back to a plain icon tile when nothing resolved or every photo 404s.
export function PropertyListingCarousel({ listings }: Props) {
  const [index, setIndex] = useState(0);
  const [brokenUrls, setBrokenUrls] = useState<Set<string>>(new Set());

  if (listings.length === 0) return null;

  const current = listings[index];
  const images = current.image_urls.filter((url) => !brokenUrls.has(url));
  const canGoBack = index > 0;
  const canGoForward = index < listings.length - 1;

  const markBroken = (url: string) => setBrokenUrls((prev) => new Set(prev).add(url));

  return (
    <div className="listing-carousel">
      <div className="listing-card">
        {images.length > 0 ? (
          <div className="listing-card-images">
            {images.map((url, i) => (
              <img
                key={url}
                className="listing-card-image"
                src={url}
                alt={`${current.project_name} ${i + 1}`}
                loading="lazy"
                onError={() => markBroken(url)}
              />
            ))}
          </div>
        ) : (
          <div className="listing-card-images">
            <div className="listing-card-image listing-card-image--placeholder">
              <HomeIcon size={36} />
            </div>
          </div>
        )}

        <div className="listing-card-body">
          <p className="listing-card-title">{current.project_name}</p>
          <p className="listing-card-meta">
            {current.unit_type} · {current.area_range}
          </p>
          <p className="listing-card-price">{current.price_range}</p>
          {current.amenities.length > 0 && (
            <div className="listing-card-amenities">
              {current.amenities.map((amenity) => (
                <span key={amenity} className="listing-card-amenity">
                  {amenity}
                </span>
              ))}
            </div>
          )}
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
