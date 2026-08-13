import { Link } from "react-router-dom";
import type { CategorySummary } from "../types/project";
import { BuildingHomeIcon } from "./Icons";

// Anh rieng cho the "Chung cu" theo yeu cau — khong lay tu API nhu cac the khac.
const CHUNG_CU_IMAGE = "/masteri-grand-coast-bg-homepage.jpg";

export function CategoryCard({ category }: { category: CategorySummary }) {
  const coverImage = category.slug === "chung-cu" ? CHUNG_CU_IMAGE : category.coverImage;

  const media = coverImage ? undefined : { background: "linear-gradient(135deg, #0050ef, #0a2e7a)" };

  const sizeLabel =
    category.sizeFrom != null && category.sizeTo != null ? `${category.sizeFrom} - ${category.sizeTo} m²` : null;

  return (
    <Link to={`/inventory/${category.slug}`} className="project-card">
      <div className="project-card-media" style={media}>
        {coverImage ? (
          <img src={coverImage} className="project-card-image" alt={category.name} />
        ) : (
          <BuildingHomeIcon size={30} className="project-card-media-icon" />
        )}
      </div>
      <div className="project-card-body">
        <div className="project-card-meta">
          {sizeLabel && <span className="project-card-location">{sizeLabel}</span>}
        </div>
        <h3 className="project-card-title">{category.name}</h3>
        <div className="project-card-footer">
          <div>
            <span className="project-card-price-label">Khoảng giá</span>
            <strong className="project-card-price">
              {category.priceFrom} - {category.priceTo}
            </strong>
          </div>
        </div>
      </div>
    </Link>
  );
}
