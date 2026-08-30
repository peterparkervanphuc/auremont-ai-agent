import { ArrowRightIcon, CheckCircleIcon } from "./Icons";

const PRICING_PLANS = [
  {
    name: "Khởi động",
    price: "10",
    conversations: "500",
    cta: "Chọn gói",
    featured: false,
  },
  {
    name: "Tăng trưởng",
    price: "20",
    conversations: "2.000",
    cta: "Bắt đầu ngay",
    featured: true,
  },
  {
    name: "Quy mô",
    price: "40",
    conversations: "6.000",
    cta: "Liên hệ tư vấn",
    featured: false,
  },
] as const;

const SHARED_BENEFITS = [
  "AI tư vấn khách hàng 24/7",
  "Phân loại lead COLD / WARM / HOT",
  "Sales tiếp quản và theo dõi hội thoại",
  "Dashboard, dữ liệu và phân quyền đầy đủ",
] as const;

function buildContactHref(planName: string) {
  const subject = encodeURIComponent(`Tư vấn gói ${planName} - Auremont AI`);
  const body = encodeURIComponent(
    `Tôi muốn được tư vấn thêm về gói ${planName} dành cho doanh nghiệp.`,
  );
  return `mailto:support@auremont.vn?subject=${subject}&body=${body}`;
}

export function PricingSection() {
  return (
    <section className="business-pricing" id="bang-gia" aria-labelledby="business-pricing-title">
      <div className="container">
        <header className="business-pricing-head">
          <p className="section-eyebrow">Bảng giá dành cho doanh nghiệp</p>
          <h2 className="business-pricing-title" id="business-pricing-title">
            Một nền tảng, đầy đủ tính năng
          </h2>
          <p className="business-pricing-subtitle">
            Mọi gói đều có toàn bộ quyền lợi, chỉ khác nhau về số cuộc tư vấn AI mỗi tháng.
          </p>
        </header>

        <div className="business-pricing-grid">
          {PRICING_PLANS.map((plan) => (
            <article
              key={plan.name}
              className={`business-pricing-plan${plan.featured ? " business-pricing-plan--featured" : ""}`}
            >
              {plan.featured && <span className="business-pricing-badge">Phổ biến nhất</span>}

              <h3 className="business-pricing-plan-name">{plan.name}</h3>
              <div className="business-pricing-price" aria-label={`${plan.price} triệu đồng mỗi tháng`}>
                <strong>{plan.price}</strong>
                <span>triệu</span>
                <small>/ tháng</small>
              </div>

              <p className="business-pricing-quota">
                <strong>{plan.conversations}</strong> cuộc tư vấn AI
              </p>
              <p className="business-pricing-quota-note">Mỗi cuộc gồm nhiều câu hỏi trong cùng một phiên</p>

              <div className="business-pricing-included">
                <CheckCircleIcon size={19} />
                <span>Đầy đủ mọi tính năng</span>
              </div>

              <a
                href={buildContactHref(plan.name)}
                className={`btn business-pricing-cta ${plan.featured ? "btn-primary" : "btn-outline"}`}
                aria-label={`${plan.cta} ${plan.name}`}
              >
                {plan.cta}
                <ArrowRightIcon size={16} />
              </a>
            </article>
          ))}
        </div>

        <div className="business-pricing-benefits" aria-label="Quyền lợi chung của mọi gói">
          {SHARED_BENEFITS.map((benefit) => (
            <div key={benefit} className="business-pricing-benefit">
              <CheckCircleIcon size={18} />
              <span>{benefit}</span>
            </div>
          ))}
        </div>

        <p className="business-pricing-footnote">
          Hạn mức được làm mới mỗi tháng. Có thể nâng gói bất cứ lúc nào khi nhu cầu tăng.
        </p>
      </div>
    </section>
  );
}
