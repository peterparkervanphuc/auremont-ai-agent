import { Link } from "react-router-dom";
import type { CategorySummary } from "../types/project";
import { BuildingHomeIcon } from "./Icons";

export function CategoryCard({ category }: { category: CategorySummary }) {
  const media = category.coverImage
    ? { backgroundImage: `url(${category.coverImage})`, backgroundSize: "cover", backgroundPosition: "center" }
    : { background: "linear-gradient(135deg, #0050ef, #0a2e7a)" };

  const sizeLabel =
    category.sizeFrom != null && category.sizeTo != null ? `${category.sizeFrom} - ${category.sizeTo} m²` : null;

  const typesPreview = category.typeNames.slice(0, 3).join(" · ");

  return (
    <Link to={`/inventory/${category.slug}`} className="project-card">
      <div className="project-card-media" style={media}>
        {!category.coverImage && <BuildingHomeIcon size={30} className="project-card-media-icon" />}
      </div>
      <div className="project-card-body">
        <div className="project-card-meta">
          <span className="project-card-type">{category.typesCount} loại hình</span>
          {sizeLabel && <span className="project-card-location">{sizeLabel}</span>}
        </div>
        <h3 className="project-card-title">{category.name}</h3>
        <p className="project-card-desc">{typesPreview || `${category.typesCount} loại hình`}</p>
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
