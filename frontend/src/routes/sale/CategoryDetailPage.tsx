import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../../api/client";
import { fetchCategoryDetail } from "../../api/projects";
import type { CategoryDetail } from "../../types/project";
import type { ChatSessionResponse } from "../../types";
import {
  ArrowLeftIcon,
  BuildingHomeIcon,
  CheckIcon,
  ChatIcon,
  LoaderIcon,
  SearchIcon,
  SparkleIcon,
} from "../../components/Icons";

function CategoryBanner({ category }: { category: CategoryDetail }) {
  const image = category.coverImage ?? category.gallery[0] ?? null;

  return (
    <div className="detail-banner">
      {image ? <div className="detail-banner-slide detail-banner-slide--active" style={{ backgroundImage: `url(${image})` }} /> : null}
      <div className="detail-banner-scrim" />

      <BuildingHomeIcon size={40} className="detail-banner-icon" />
      <div className="detail-banner-meta">
        <span className="project-card-type">Vinhomes Ocean Park</span>
      </div>
      <h1 className="detail-banner-title">{category.name}</h1>
    </div>
  );
}

export function CategoryDetailPage() {
  const { categorySlug } = useParams();
  const navigate = useNavigate();
  const [category, setCategory] = useState<CategoryDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [booking, setBooking] = useState(false);

  const bookViewing = async () => {
    if (!category || booking) return;
    setBooking(true);
    try {
      const session = await api.post<ChatSessionResponse>("/sale/sessions", {});
      navigate(`/chat/sessions/${session.id}`, {
        state: { prefill: `Tôi muốn đặt lịch xem nhà cho ${category.name.toLowerCase()}.` },
      });
    } finally {
      setBooking(false);
    }
  };

  useEffect(() => {
    if (!categorySlug) return;
    setLoading(true);
    fetchCategoryDetail(categorySlug)
      .then(setCategory)
      .catch(() => setCategory(null))
      .finally(() => setLoading(false));
  }, [categorySlug]);

  if (loading) {
    return (
      <div className="page">
        <div className="empty-state">
          <LoaderIcon size={26} className="icon-spin" />
          <p className="empty-state-text empty-state-text--spaced">
            Đang tải bảng giá...
          </p>
        </div>
      </div>
    );
  }

  if (!category) {
    return (
      <div className="page">
        <div className="empty-state">
          <div className="empty-state-icon">
            <SearchIcon size={26} />
          </div>
          <p className="empty-state-title">Không tìm thấy loại hình này</p>
          <p className="empty-state-text">Đường dẫn có thể không đúng.</p>
          <Link to="/inventory" className="btn btn-primary" style={{ marginTop: 16 }}>
            Về Tra cứu dự án
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="page inv-page">
      <Link to="/inventory" className="detail-back">
        <ArrowLeftIcon size={15} />
        Tra cứu dự án
      </Link>

      <CategoryBanner category={category} />

      <div className="inv-layout">
        <div className="inv-main">
          <section className="section-block">
            <h3 className="section-title">Giới thiệu</h3>
            <p className="page-sub" style={{ maxWidth: "none" }}>
              {category.description}
            </p>
          </section>

          {category.gallery.length > 0 && (
            <section className="section-block">
              <h3 className="section-title">Hình ảnh thực tế ({category.gallery.length})</h3>
              <div className="detail-gallery">
                {category.gallery.map((src, i) => (
                  <a key={src} href={src} target="_blank" rel="noreferrer" className="detail-gallery-item">
                    <img src={src} alt={`${category.name} - ảnh ${i + 1}`} loading="lazy" />
                  </a>
                ))}
              </div>
            </section>
          )}

          <section className="section-block">
            <h3 className="section-title">Bảng giá theo loại hình ({category.types.length})</h3>
            <div className="data-list">
              {category.types.map((t, i) => (
                <div key={t.type} id={`type-${i}`} className="data-row data-row--anchor">
                  <div className="data-row-icon">
                    <BuildingHomeIcon size={16} />
                  </div>
                  <div className="data-row-main">
                    <div className="data-row-title">{t.type}</div>
                    <div className="data-row-meta">
                      <span>{t.sizeRange}</span>
                      <span>{t.priceRange}</span>
                      {t.storeys && <span>{t.storeys}</span>}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </section>

          {category.highlights.length > 0 && (
            <section className="section-block">
              <h3 className="section-title">Điểm nổi bật</h3>
              <p className="page-sub" style={{ maxWidth: "none", marginTop: -6, marginBottom: 14 }}>
                Những dấu ấn quy mô lớn nhất của toàn khu đô thị Vinhomes Ocean Park.
              </p>
              <div className="detail-amenities">
                {category.highlights.map((h) => (
                  <span key={h} className="detail-amenity-chip">
                    <SparkleIcon size={13} />
                    {h}
                  </span>
                ))}
              </div>
            </section>
          )}

          {category.amenities.length > 0 && (
            <section>
              <h3 className="section-title">Tiện ích</h3>
              <p className="page-sub" style={{ maxWidth: "none", marginTop: -6, marginBottom: 14 }}>
                Danh mục đầy đủ tiện ích trong khuôn viên dự án, dùng chung cho mọi loại hình.
              </p>
              <div className="detail-amenities">
                {category.amenities.map((a) => (
                  <span key={a} className="detail-amenity-chip">
                    <CheckIcon size={13} />
                    {a}
                  </span>
                ))}
              </div>
            </section>
          )}
        </div>

        <aside className="inv-assist">
          <div className="inv-assist-panel">
            <div className="detail-quickfacts">
              <div className="detail-quickfact-row">
                <span>Dự án</span>
                <strong>Vinhomes Ocean Park</strong>
              </div>
              <div className="detail-quickfact-row">
                <span>Loại hình</span>
                <strong>{category.name}</strong>
              </div>
              <div className="detail-quickfact-row">
                <span>Số nhóm giá</span>
                <strong>{category.types.length}</strong>
              </div>
            </div>

            <button
              type="button"
              className="btn btn-primary"
              style={{ width: "100%", marginTop: 16 }}
              onClick={bookViewing}
              disabled={booking}
            >
              {booking ? <LoaderIcon size={16} className="icon-spin" /> : <ChatIcon size={16} />}
              Chat với Auremont AI
            </button>
          </div>
        </aside>
      </div>
    </div>
  );
}
