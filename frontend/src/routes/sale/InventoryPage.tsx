import { useEffect, useState } from "react";
import { fetchCategories } from "../../api/projects";
import { CategoryCard } from "../../components/CategoryCard";
import type { CategorySummary } from "../../types/project";
import { UPCOMING_PHASES } from "../../types/project";
import { ArrowRightIcon, LoaderIcon, SendIcon, SparkleIcon } from "../../components/Icons";
import { Link } from "react-router-dom";

export function InventoryPage() {
  const [categories, setCategories] = useState<CategorySummary[] | null>(null);
  const [activeSlug, setActiveSlug] = useState<string | null>(null);

  useEffect(() => {
    fetchCategories()
      .then(setCategories)
      .catch(() => setCategories([]));
  }, []);

  const visibleCategories = (categories ?? []).filter(
    (c) => !activeSlug || c.slug === activeSlug
  );

  const activeCategory = (categories ?? []).find((c) => c.slug === activeSlug) ?? null;

  const suggestions = activeCategory
    ? [
        `${activeCategory.typeNames[0] ?? activeCategory.name} giá bao nhiêu?`,
        `So sánh giá các loại ${activeCategory.name.toLowerCase()}`,
      ]
    : ["Còn căn 2PN dưới 3 tỷ không?", "Biệt thự song lập giá bao nhiêu?"];

  return (
    <div className="page inv-page">
      <div className="page-head">
        <div>
          <h2 className="page-title">Tra cứu dự án</h2>
          <p className="page-sub">
            Bảng hàng Vinhomes Ocean Park theo loại hình — dùng trợ lý AI bên cạnh khi cần hỏi nhanh.
          </p>
        </div>
      </div>

      <div className="inv-layout">
        <div className="inv-main">
          <div className="inv-toolbar">
            <div className="inv-filters">
              {categories && categories.length > 0 && (
                <button
                  type="button"
                  className={`inv-filter-chip ${activeSlug === null ? "inv-filter-chip--active" : ""}`}
                  onClick={() => setActiveSlug(null)}
                >
                  Tất cả
                </button>
              )}
              {(categories ?? []).map((c) => (
                <button
                  key={c.slug}
                  type="button"
                  className={`inv-filter-chip ${activeSlug === c.slug ? "inv-filter-chip--active" : ""}`}
                  onClick={() => setActiveSlug(c.slug)}
                >
                  {c.name}
                </button>
              ))}
              {UPCOMING_PHASES.map((p) => (
                <span key={p.slug} className="inv-filter-chip inv-filter-chip--disabled" title="Đang cập nhật dữ liệu">
                  {p.name} · sắp có
                </span>
              ))}
            </div>
          </div>

          {categories === null ? (
            <div className="empty-state">
              <LoaderIcon size={26} className="icon-spin" />
              <p className="empty-state-text empty-state-text--spaced">
                Đang tải bảng hàng...
              </p>
            </div>
          ) : categories.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon">
                <SparkleIcon size={26} />
              </div>
              <p className="empty-state-title">Chưa có dữ liệu bảng hàng</p>
              <p className="empty-state-text">Liên hệ Admin để nạp dữ liệu dự án.</p>
            </div>
          ) : (
            <div className="inv-grid">
              {visibleCategories.map((c) => (
                <CategoryCard key={c.slug} category={c} />
              ))}
            </div>
          )}
        </div>

        <aside className="inv-assist">
          <div className="inv-assist-panel">
            <div className="inv-assist-head">
              <div className="inv-assist-icon">
                <SparkleIcon size={18} />
              </div>
              <div>
                <p className="inv-assist-title">Trợ lý AI</p>
                <p className="inv-assist-sub">Hỏi nhanh về giá, pháp lý hoặc tồn kho</p>
              </div>
            </div>

            <div className="inv-assist-suggestions">
              {suggestions.map((s) => (
                <span key={s}>&ldquo;{s}&rdquo;</span>
              ))}
            </div>

            <Link to="/chat" className="inv-assist-input">
              <span>Đặt câu hỏi cho Auremont AI...</span>
              <SendIcon size={15} />
            </Link>

            <Link to="/chat" className="inv-assist-fulllink">
              Mở trợ lý đầy đủ
              <ArrowRightIcon size={14} />
            </Link>
          </div>
        </aside>
      </div>
    </div>
  );
}
