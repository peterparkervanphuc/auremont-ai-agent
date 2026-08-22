import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import type { PropertyListing } from "../types";
import { ChevronLeftIcon, ChevronRightIcon, HomeIcon } from "../components/Icons";
import { ZONES } from "./sale/inventory/registry";
import { markCameFromChat } from "../components/BackToChatButton";

interface Props {
  listings: PropertyListing[];
}

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

// The catalogue Project table and the sale inventory registry (registry.tsx) were built
// independently and disagree on prefixes for the same real project: the DB's villa ids
// are bare ("hai-au") while the registry's are "tieu-khu-hai-au"; the DB's shophouse ids
// are "shop-thuong-mai-sh09" while the registry's are the shorter "shop-sh09". Every
// apartment zone happens to agree exactly, which is why this went unnoticed until a
// villa card first got tested. Stripping the known prefixes before comparing unifies
// both naming schemes instead of special-casing three zones by hand.
function coreSlug(value: string): string {
  return value.replace(/^(tieu-khu-|shop-thuong-mai-|shop-)/, "");
}

// `project_id` (resolved server-side, see agent_pipeline._resolve_listing_images) is a
// catalogue Project row's id. Two different shapes of project exist in the registry:
// a whole zone (id matches a ZoneMeta's own `slug`, e.g. "the-sapphire") or one tower
// inside a multi-tower zone (id matches one of that zone's `subAnchors[].anchorId`, e.g.
// "the-zurich" inside the "the-metropolitan" zone — Zurich has no page of its own). Both
// must resolve to a working link, or a listing for any multi-tower zone's individual
// towers (Zurich, Beverly, London, Paris, Zenpark, Pavilion, Senique's blocks...) is
// silently left unclickable.
function resolveZoneLink(projectId: string, projectName: string): string | null {
  const projectCore = coreSlug(projectId);

  const topLevel = ZONES.find((z) => coreSlug(z.slug) === projectCore);
  if (topLevel) {
    // A whole-zone id can still point at one specific sub-tower's section when the
    // listing names one (e.g. project_id "the-sapphire" but project_name "The Sapphire
    // 2") — see the "the-sapphire" zone's own subAnchors in registry.tsx.
    const nameCore = coreSlug(slugify(projectName));
    const nameAnchor = topLevel.subAnchors?.find((a) => coreSlug(a.anchorId) === nameCore);
    return `/inventory/${topLevel.categorySlug}/${topLevel.slug}${nameAnchor ? `#${nameAnchor.anchorId}` : ""}`;
  }

  for (const zone of ZONES) {
    const anchor = zone.subAnchors?.find((a) => coreSlug(a.anchorId) === projectCore);
    if (anchor) {
      return `/inventory/${zone.categorySlug}/${zone.slug}#${anchor.anchorId}`;
    }
  }

  return null;
}

// The card sits inside a narrow chat bubble, not a full page — a thumbnail row long
// enough to need its own horizontal scrollbar there was stretching the whole message
// wider than the chat column instead of scrolling in place. Showing the row one page of
// this many thumbnails at a time (not how many the backend resolves — select_listing_images
// intentionally has no cap, accuracy matters more there) keeps the row's width bounded and
// predictable. The rest are not just theoretically reachable in the fullscreen viewer —
// the "+N" badge on the last visible thumbnail IS the "next page" control, sliding the
// window forward in place rather than just zooming that one photo.
const _VISIBLE_THUMB_COUNT = 6;

// One recommended unit at a time, with paging arrows between cards — the numeric details
// (loại căn/diện tích/giá) used to be bullet lines inside the answer's own text; they now
// live here instead, so the chat bubble stays a short 1-2 sentence recommendation and the
// actual figures get a card of their own. `image_urls`/`amenities` are resolved
// server-side (see agent_pipeline._resolve_listing_images/select_listing_images): a floor
// plan when the catalogue tags one for this unit type, the subdivision's own overview
// shots otherwise — never a photo of the specific unit, since no such photo exists in the
// catalogue.
//
// Gallery layout follows the reference listing sites the user pointed at: one large hero
// photo on top, a strip of small thumbnails below it — tapping a thumbnail swaps which
// photo is the hero, in place, no overlay. Tapping the hero itself opens a fullscreen
// viewer with its own prev/next arrows, a counter and the same thumbnail strip at the
// bottom, so a photo can be viewed genuinely large rather than cropped into a tile. The
// text side links out to the subdivision's own catalogue page (`project_id` is resolved
// the same way as the photos) when one could be resolved, opening in a new tab so the
// chat itself is never navigated away from.
export function PropertyListingCarousel({ listings }: Props) {
  const [index, setIndex] = useState(0);
  const [activeImage, setActiveImage] = useState(0);
  const [thumbPage, setThumbPage] = useState(0);
  const [zoomOpen, setZoomOpen] = useState(false);
  const [brokenUrls, setBrokenUrls] = useState<Set<string>>(new Set());

  // Switching which recommended unit is shown must not carry over the previous unit's
  // "which photo is big" state onto a gallery it doesn't belong to.
  useEffect(() => {
    setActiveImage(0);
    setThumbPage(0);
    setZoomOpen(false);
  }, [index]);

  useEffect(() => {
    if (!zoomOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setZoomOpen(false);
      if (e.key === "ArrowLeft") setActiveImage((i) => Math.max(0, i - 1));
      if (e.key === "ArrowRight") setActiveImage((i) => i + 1);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [zoomOpen]);

  if (listings.length === 0) return null;

  const current = listings[index];
  const images = current.image_urls.filter((url) => !brokenUrls.has(url));
  const heroIndex = Math.min(activeImage, Math.max(images.length - 1, 0));
  const canGoBack = index > 0;
  const canGoForward = index < listings.length - 1;
  const canZoomPrev = heroIndex > 0;
  const canZoomNext = heroIndex < images.length - 1;
  const projectHref = current.project_id ? resolveZoneLink(current.project_id, current.project_name) : null;

  // The thumbnail row shows one "page" of _VISIBLE_THUMB_COUNT photos at a time — the "+N"
  // badge on the last one is itself the "next page" control (tapping it slides the window
  // forward instead of zooming that one photo), and a small back arrow appears once paged
  // forward at least once. Clamped defensively in case `images` shrank (a thumbnail's URL
  // broke) since thumbPage was last set.
  const totalThumbPages = Math.max(1, Math.ceil(images.length / _VISIBLE_THUMB_COUNT));
  const clampedThumbPage = Math.min(thumbPage, totalThumbPages - 1);
  const thumbPageStart = clampedThumbPage * _VISIBLE_THUMB_COUNT;
  const visibleThumbs = images.slice(thumbPageStart, thumbPageStart + _VISIBLE_THUMB_COUNT);
  const hiddenThumbCount = images.length - (thumbPageStart + visibleThumbs.length);

  const markBroken = (url: string) => setBrokenUrls((prev) => new Set(prev).add(url));

  const bodyContent = (
    <>
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
    </>
  );

  return (
    <div className="listing-carousel">
      <div className="listing-card">
        {images.length > 0 ? (
          <>
            <button
              type="button"
              className="listing-card-hero-btn"
              onClick={() => setZoomOpen(true)}
              title={`Phóng to ảnh ${current.project_name}`}
            >
              <img
                className="listing-card-hero-image"
                src={images[heroIndex]}
                alt={`${current.project_name} ${heroIndex + 1}`}
                onError={() => markBroken(images[heroIndex])}
              />
            </button>
            {images.length > 1 && (
              <div className="listing-card-thumbs">
                {clampedThumbPage > 0 && (
                  <button
                    type="button"
                    className="listing-card-thumb-page-btn"
                    onClick={() => setThumbPage((p) => p - 1)}
                    aria-label="Ảnh trước đó"
                  >
                    <ChevronLeftIcon size={14} />
                  </button>
                )}
                {visibleThumbs.map((url, i) => {
                  const globalIndex = thumbPageStart + i;
                  const isLastVisible = i === visibleThumbs.length - 1;
                  const showMoreBadge = isLastVisible && hiddenThumbCount > 0;
                  return (
                    <button
                      key={url}
                      type="button"
                      className={`listing-card-thumb-btn ${globalIndex === heroIndex ? "listing-card-thumb-btn--active" : ""}`}
                      onClick={() => (showMoreBadge ? setThumbPage((p) => p + 1) : setActiveImage(globalIndex))}
                      title={
                        showMoreBadge
                          ? `Xem thêm ${hiddenThumbCount} ảnh ${current.project_name}`
                          : `Ảnh ${globalIndex + 1} ${current.project_name}`
                      }
                    >
                      <img
                        className="listing-card-thumb-image"
                        src={url}
                        alt={`${current.project_name} ${globalIndex + 1}`}
                        loading="lazy"
                        onError={() => markBroken(url)}
                      />
                      {showMoreBadge && <span className="listing-card-thumb-more">+{hiddenThumbCount}</span>}
                    </button>
                  );
                })}
              </div>
            )}
          </>
        ) : (
          <div className="listing-card-hero-image listing-card-hero-image--placeholder">
            <HomeIcon size={36} />
          </div>
        )}

        {projectHref ? (
          <a
            className="listing-card-body listing-card-body--link"
            href={projectHref}
            target="_blank"
            rel="noopener noreferrer"
            title={`Xem ${current.project_name} trên trang phân khu`}
            onClick={markCameFromChat}
          >
            {bodyContent}
          </a>
        ) : (
          <div className="listing-card-body">{bodyContent}</div>
        )}

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

      {/* Portalled to <body>, same reasoning as AnswerImageStrip.tsx: `.chat-message` keeps
          a transform from its entry animation, which would otherwise clip a `position:
          fixed` lightbox to the message bubble instead of the viewport. Unlike that
          simpler single-image lightbox, this one carries its own prev/next + counter +
          thumbnail strip, since a listing has several photos worth browsing in place. */}
      {zoomOpen &&
        images.length > 0 &&
        createPortal(
          <div className="image-lightbox" onClick={() => setZoomOpen(false)} role="presentation">
            <div className="property-lightbox" onClick={(e) => e.stopPropagation()}>
              <div className="property-lightbox-main">
                <button
                  type="button"
                  className="property-lightbox-arrow property-lightbox-arrow--left"
                  disabled={!canZoomPrev}
                  onClick={() => setActiveImage((i) => i - 1)}
                  aria-label="Ảnh trước"
                >
                  <ChevronLeftIcon size={20} />
                </button>
                <img src={images[heroIndex]} alt={`${current.project_name} ${heroIndex + 1}`} />
                <button
                  type="button"
                  className="property-lightbox-arrow property-lightbox-arrow--right"
                  disabled={!canZoomNext}
                  onClick={() => setActiveImage((i) => i + 1)}
                  aria-label="Ảnh tiếp theo"
                >
                  <ChevronRightIcon size={20} />
                </button>
                {images.length > 1 && (
                  <span className="property-lightbox-counter">
                    {heroIndex + 1} / {images.length}
                  </span>
                )}
              </div>

              {images.length > 1 && (
                <div className="property-lightbox-thumbs">
                  {images.map((url, i) => (
                    <button
                      key={url}
                      type="button"
                      className={`property-lightbox-thumb ${i === heroIndex ? "property-lightbox-thumb--active" : ""}`}
                      onClick={() => setActiveImage(i)}
                      title={`Ảnh ${i + 1} ${current.project_name}`}
                    >
                      <img src={url} alt={`${current.project_name} ${i + 1}`} loading="lazy" />
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}
