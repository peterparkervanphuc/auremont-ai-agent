import { Link } from "react-router-dom";
import type { CatalogGroup } from "../types/catalog";
import type { ProjectListItem } from "../api/projects";
import { BuildingHomeIcon } from "./Icons";

interface Props {
  group: CatalogGroup;
  projectsById: Map<string, ProjectListItem>;
}

export function GroupCard({ group, projectsById }: Props) {
  const withData = group.projects
    .map((p) => (p.projectId ? projectsById.get(p.projectId) : undefined))
    .filter((p): p is ProjectListItem => !!p);

  const hasData = withData.length > 0;
  const cover = withData.find((p) => p.coverImage)?.coverImage;

  const media = cover
    ? { backgroundImage: `url(${cover})`, backgroundSize: "cover", backgroundPosition: "center" }
    : { background: "linear-gradient(135deg, #0050ef, #0a2e7a)" };

  const priceLine = withData
    .map((p) => p.priceFrom)
    .filter((p): p is string => !!p)
    .sort()[0];

  // Nhom chi co DUY NHAT 1 du an that (vd "Lumiere Orient Pearl" chi co The Palma) -> bo qua
  // trang nhom trung gian, vao thang trang du an luon — dong bo voi cach TopNavbar da lam,
  // tranh nguoi dung phai bam 2 lan de xem 1 thu duy nhat.
  const singleProject = group.projects.length === 1 ? group.projects[0] : null;
  const linkTo = singleProject?.projectId ? `/inventory/project/${singleProject.projectId}` : `/inventory/group/${group.slug}`;

  return (
    <Link to={linkTo} className={`project-card ${!hasData ? "project-card--disabled" : ""}`}>
      <div className="project-card-media" style={media}>
        {!cover && <BuildingHomeIcon size={30} className="project-card-media-icon" />}
      </div>
      <div className="project-card-body">
        <div className="project-card-meta">
          <span className="project-card-type">
            {hasData ? `${withData.length}/${group.projects.length} dự án có dữ liệu` : "Chưa có dữ liệu"}
          </span>
        </div>
        <h3 className="project-card-title">{group.name}</h3>
        <p className="project-card-desc">
          {group.projects.length > 1 ? group.projects.map((p) => p.name).join(" · ") : "Xem chi tiết"}
        </p>
        {priceLine && (
          <div className="project-card-footer">
            <div>
              <span className="project-card-price-label">Giá từ</span>
              <strong className="project-card-price">{priceLine}</strong>
            </div>
          </div>
        )}
      </div>
    </Link>
  );
}
