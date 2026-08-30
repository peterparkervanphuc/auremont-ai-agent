import { ArrowRightIcon, CheckCircleIcon } from "./Icons";

// Định giá theo seat (số Sale dùng AI), như phần lớn CRM B2B (Getfly, Zoho, HubSpot) —
// dễ hiểu và dễ so sánh hơn tính theo tổng số cuộc hội thoại, vốn không phải đơn vị khách
// hàng tự ước lượng được trước khi dùng thử. Mọi gói có đầy đủ tính năng AI như nhau; gói
// chỉ khác số seat tối thiểu, hạn mức hội thoại và mức hỗ trợ — giá trị cốt lõi khách trả
// tiền là chất lượng AI tư vấn, không phải tính năng quản trị bị khoá ở gói thấp.
const PRICING_PLANS = [
  {
    name: "Starter",
    price: "390.000",
    unit: "seat / tháng",
    seatsNote: "Tối thiểu 1 seat",
    conversationsPerSeat: "150",
    support: "Hỗ trợ qua email, phản hồi trong 24h",
    featured: false,
  },
  {
    name: "Growth",
    price: "550.000",
    unit: "seat / tháng",
    seatsNote: "Tối thiểu 3 seat",
    conversationsPerSeat: "400",
    support: "Hỗ trợ ưu tiên trong giờ hành chính",
    featured: true,
  },
  {
    name: "Enterprise",
    price: "420.000",
    unit: "seat / tháng",
    seatsNote: "Từ 20 seat trở lên",
    conversationsPerSeat: "Không giới hạn cứng",
    support: "SLA riêng, hỗ trợ kỹ thuật 24/7",
    featured: false,
  },
] as const;

const CTA_LABEL = "Đăng ký";

const SHARED_FEATURES = [
  "AI tư vấn khách hàng 24/7",
  "Phân loại lead COLD / WARM / HOT",
  "Sales tiếp quản và theo dõi hội thoại",
  "Phân quyền theo team / dự án",
  "Dashboard, báo cáo hiệu suất đầy đủ",
  "Tích hợp CRM / Zalo OA",
] as const;

const OVERAGE_NOTE = "Vượt hạn mức: tính phụ phí theo cuộc, không tạm ngưng AI giữa tháng.";

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
            Trả theo số Sale đang dùng
          </h2>
          <p className="business-pricing-subtitle">
            Mọi gói đều có toàn bộ tính năng AI. Không tính theo tổng hội thoại toàn công ty —
            chi phí tăng đúng theo quy mô đội ngũ thực tế, chỉ khác nhau về hạn mức và mức hỗ trợ.
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
              <div className="business-pricing-price" aria-label={`${plan.price} đồng mỗi seat mỗi tháng`}>
                <strong>{plan.price}</strong>
                <small>đ</small>
              </div>
              <p className="business-pricing-unit">{plan.unit}</p>
              <p className="business-pricing-seats-note">{plan.seatsNote}</p>

              <p className="business-pricing-quota">
                <strong>{plan.conversationsPerSeat}</strong> cuộc tư vấn AI / seat / tháng
              </p>
              <p className="business-pricing-quota-note">Hạn mức gộp chung cho cả team, không chia cứng theo người</p>

              <div className="business-pricing-included">
                <CheckCircleIcon size={19} />
                <span>Đầy đủ mọi tính năng</span>
              </div>
              <p className="business-pricing-support-note">{plan.support}</p>

              <a
                href={buildContactHref(plan.name)}
                className={`btn business-pricing-cta ${plan.featured ? "btn-primary" : "btn-outline"}`}
                aria-label={`${CTA_LABEL} gói ${plan.name}`}
              >
                {CTA_LABEL}
                <ArrowRightIcon size={16} />
              </a>
            </article>
          ))}
        </div>

        <div className="business-pricing-benefits" aria-label="Quyền lợi chung của mọi gói">
          {SHARED_FEATURES.map((feature) => (
            <div key={feature} className="business-pricing-benefit">
              <CheckCircleIcon size={18} />
              <span>{feature}</span>
            </div>
          ))}
        </div>

        <p className="business-pricing-footnote">
          {OVERAGE_NOTE} Hạn mức được làm mới mỗi tháng. Có thể nâng/hạ số seat bất cứ lúc nào.
        </p>
      </div>
    </section>
  );
}
