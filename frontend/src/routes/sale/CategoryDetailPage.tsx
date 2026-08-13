import { useEffect, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import {
  fetchCategoryDetail,
  fetchAllProjects,
  fetchProjectDetail,
  type ProjectListItem,
  type ProjectFullDetail,
} from "../../api/projects";
import type { CategoryDetail } from "../../types/project";
import { CATALOG } from "../../types/catalog";
import { GroupCard } from "../../components/GroupCard";
import {
  ArrowLeftIcon,
  BuildingHomeIcon,
  CheckIcon,
  LoaderIcon,
  SearchIcon,
  SparkleIcon,
} from "../../components/Icons";

// categorySlug tren URL la slug suy ra tu field `category` trong pricing (qua
// slugify o backend, vd "Shophouse" -> "shophouse") — phai KHOP dung voi
// CatalogCategory.slug trong catalog.ts moi tim dung duoc nhom phan khu de hien thi.
const CATEGORY_SLUG_TO_CATALOG_SLUG: Record<string, string> = {
  "chung-cu": "chung-cu",
  "biet-thu": "biet-thu",
  shophouse: "shophouse",
};

// Anh rieng cho banner "Chung cu" theo yeu cau — khong lay tu API nhu cac loai hinh khac.
const CHUNG_CU_BANNER_IMAGE = "/the-paris-background.jpg";

// Anh nen tu luot cho banner dau trang "Chung cu" — 4 anh theo dung yeu cau,
// da co san tren MinIO tu cac du an the-london/the-paris/the-zurich.
const CHUNG_CU_BANNER_SLIDES = [
  "http://localhost:9000/project-images/the-london/phong-dance-phan-khu-the-london-vinhomes-ocean-park.jpg",
  "http://localhost:9000/project-images/the-london/phong-giai-tri-phan-khu-the-london-vinhomes-ocean-park.jpg",
  "http://localhost:9000/project-images/the-paris/gym-ngoai-troi-phan-khu-paris-ocean-park.jpg",
  "http://localhost:9000/project-images/the-zurich/canh-quan-the-zurich.jpg",
];

// Anh nen tu luot cho banner dau trang "Biet thu" — 3 anh theo dung yeu cau,
// da co san tren MinIO tu cac du an hai-au/ngoc-trai.
const BIET_THU_BANNER_SLIDES = [
  "http://localhost:9000/project-images/hai-au/lien-ke-vinhomes-ocean-park.jpg",
  "http://localhost:9000/project-images/ngoc-trai/vinhomes-ocean-park-shop-house.jpg",
  "http://localhost:9000/project-images/hai-au/song-lap-hai-au.jpg",
];

// 4 anh tu luot cho khoi gioi thieu rieng cua tab "Chung cu".
const CHUNG_CU_INTRO_IMAGES = [
  "/masterise-vinhomes-ocean-park-night.jpg",
  "/masteri-grand-coast-bg-homepage.jpg",
  "/saphire-vinhomes-ocean-park-night.jpg",
  "/san-choi-the-pavilion.jpg",
];

function IntroCarousel({ images }: { images: string[] }) {
  const [active, setActive] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => {
      setActive((i) => (i + 1) % images.length);
    }, 3500);
    return () => clearInterval(timer);
  }, [images.length]);

  return (
    <div className="intro-carousel">
      {images.map((src, i) => (
        <img
          key={src}
          src={src}
          alt=""
          className={`intro-carousel-slide ${i === active ? "intro-carousel-slide--active" : ""}`}
        />
      ))}
    </div>
  );
}

// Vi tri (uoc luong theo % chieu rong/cao anh) cua tung khu mau tren
// cac-phan-khu-chung-cu-vinhomes-ocean-park.jpg — anh nay von la ban KHONG co nhan,
// nen toa do la uoc luong bang mat theo dung tam khu mau trong anh, khong phai so do.
const CHUNG_CU_LOCATIONS = [
  { number: 1, name: "The Sapphire", left: "32%", top: "48%" },
  { number: 2, name: "The Ocean View", left: "41%", top: "17%" },
  { number: 3, name: "The Metropolitan", left: "22%", top: "30%" },
  { number: 4, name: "Masteri Waterfront", left: "44%", top: "43%" },
];

function LocationMap() {
  return (
    <section className="section-block">
      <h3 className="location-map-title">Vị trí các phân khu Chung cư Vinhomes Ocean Park</h3>
      <div className="location-map-wrap">
        <img
          src="/cac-phan-khu-chung-cu-vinhomes-ocean-park.jpg"
          alt="Vị trí các phân khu Chung cư Vinhomes Ocean Park"
          className="location-map-img"
        />
        {CHUNG_CU_LOCATIONS.map((loc) => (
          <div key={loc.name} className="location-pin" style={{ left: loc.left, top: loc.top }}>
            <span className="location-pin-label">{loc.name}</span>
            <span className="location-pin-dot">{loc.number}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

// Noi dung mo ta Lumiere Orient Pearl / The Palma lay tu du lieu THAT cua project
// "the-palma" (developer, overview, location_sides...) da doc truoc do — khong bia.
function LumiereOrientPearlSpotlight() {
  return (
    <section className="zone-spotlight">
      <h3 className="zone-spotlight-title">Phân khu Lumière Orient Pearl</h3>
      <p className="zone-spotlight-subtitle">Kiến trúc lấy cảm hứng từ tàu lá cọ soi bóng mặt nước</p>

      <div className="zone-spotlight-grid">
        <div className="zone-spotlight-text">
          <p className="page-sub" style={{ maxWidth: "none" }}>
            <strong className="zone-spotlight-lead">Lumière Orient Pearl</strong> là phân khu căn hộ do{" "}
            <strong>Masterise Homes</strong> phát triển tại Vinhomes Ocean Park. <strong>The Palma</strong> là dự án
            căn hộ đầu tiên ra mắt tại đây, thiết kế lấy cảm hứng từ sự riêng tư và tĩnh tại, kiến trúc gợi hình tàu
            lá cọ soi bóng trên mặt nước.
          </p>
          <p className="page-sub" style={{ maxWidth: "none" }}>
            Phân khu The Palma gồm <strong>02 tòa</strong> căn hộ (~1.140 căn), cao <strong>30 tầng</strong>, tầng
            tiện ích riêng tại tầng 1 và tầng 13, với 2 tòa:
          </p>
          <ul className="zone-spotlight-list">
            <li>
              <strong>The Palma 1:</strong> tòa tháp thứ nhất, tầng 2 – 30.
            </li>
            <li>
              <strong>The Palma 2:</strong> tòa tháp thứ hai, tầng 2 – 30.
            </li>
          </ul>
          <p className="page-sub" style={{ maxWidth: "none" }}>
            Căn hộ tại The Palma có diện tích từ khoảng <strong>28,6 – 93,9m²</strong> với đa dạng loại hình Studio,
            1PN, 1PN+, 2PN, 2PN+, 3PN, Duplex, Penthouse — giá bán từ khoảng <strong>3 tỷ đồng</strong>, dự kiến bàn
            giao Quý 3/2027.
          </p>
        </div>
        <div className="zone-spotlight-media">
          <img src="/lumiere-orient-pearl-bg-1.jpg" alt="Lumière Orient Pearl" />
        </div>
      </div>
    </section>
  );
}

// Noi dung "Phan khu The Ocean View" lay tu anh mau tham khao nguoi dung gui
// (khong bia) — day la nhom cha (The Zenpark/The Pavilion/The Bayfront), khong
// phai 1 project rieng trong DB nen KHONG the fetch API, giong cach lam voi
// MetropolitanSpotlight.
function OceanViewSpotlight() {
  return (
    <section className="zone-spotlight">
      <h3 className="zone-spotlight-title zone-spotlight-title--amber">Phân khu The Ocean View</h3>
      <p className="zone-spotlight-subtitle">Thiên đường nghỉ dưỡng sinh thái</p>

      <div className="zone-spotlight-grid">
        <div className="zone-spotlight-text">
          <p className="page-sub" style={{ maxWidth: "none" }}>
            <strong className="zone-spotlight-lead">The Ocean View</strong> Vinhomes Ocean Park là phân khu chung cư
            được mở bán tiếp theo phân khu The Sapphire. Được quy hoạch theo mô hình "Nghỉ dưỡng sinh thái đẳng cấp"
            giữa biển xanh khoáng đạt, The Ocean View là nơi mà cư dân có thể thư thái tận hưởng sự tiện nghi của
            thiên đường tiện ích, sự trong lành của "ốc đảo xanh" và sự yên tĩnh ngay tại một Đại đô thị sôi động.
          </p>
          <p className="page-sub" style={{ maxWidth: "none" }}>
            The Ocean View bao gồm <strong>3 tiểu khu</strong> với tổng số <strong>12 tòa</strong> căn hộ, đó là:
          </p>
          <ul className="zone-spotlight-list">
            <li>
              <strong>The Zenpark:</strong> 4 tòa căn hộ cao cấp phong cách Nhật Bản, đánh số từ R1.01 đến R1.05.
            </li>
            <li>
              <strong>The Pavilion:</strong> 4 tòa căn hộ phong cách Singapore, đánh số từ P1 đến P4.
            </li>
            <li>
              <strong>The Bayfront:</strong> 4 tòa căn hộ hạng sang phong cách Dubai, gồm 3 tòa BF1, BF2, BF3 và 1 tòa
              căn hộ dịch vụ Royal Sail.
            </li>
          </ul>
        </div>
        <div className="zone-spotlight-media">
          <img
            src="http://localhost:9000/project-images/the-ocean-view/the-ocean-view.jpg"
            alt="Phân khu The Ocean View"
          />
        </div>
      </div>
    </section>
  );
}

// Du 6 anh layout can ho The Zenpark theo dung danh sach duoc gui — khong co
// dien tich xac nhan rieng cho tung anh nen de trong nhan (giong cach lam voi
// ZURICH_LAYOUTS), tranh bia so.
const ZENPARK_LAYOUTS = [
  { label: "Căn Studio", src: "http://localhost:9000/project-images/the-zenpark/can-ho-studio-r1-01-vinhomes-ocean-park.jpg" },
  { label: "Căn 1 ngủ", src: "http://localhost:9000/project-images/the-zenpark/can-ho-1-ngu-r1-01-vinhomes-ocean-park.jpg" },
  { label: "Căn 1 ngủ + 1", src: "http://localhost:9000/project-images/the-zenpark/can-ho-1-ngu-1-r1-01-vinhomes-ocean-park.jpg" },
  { label: "Căn 2 ngủ", src: "http://localhost:9000/project-images/the-zenpark/can-ho-2-ngu-r1-01-vinhomes-ocean-park.jpg" },
  { label: "Căn 2 ngủ + 1", src: "http://localhost:9000/project-images/the-zenpark/can-ho-2-ngu-1-r1-01-vinhomes-ocean-park.jpg" },
  { label: "Căn 3 ngủ", src: "http://localhost:9000/project-images/the-zenpark/can-ho-3-ngu-r1-01-vinhomes-ocean-park.jpg" },
];

function ZenparkLayoutGallery() {
  return (
    <section className="section-block">
      <h3 className="pricing-card-title">Layout căn hộ The Zenpark</h3>
      <div className="layout-gallery">
        {ZENPARK_LAYOUTS.map((l, i) => (
          <div key={i} className="layout-gallery-card">
            <img src={l.src} alt={l.label} />
            <p>{l.label}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

// Du 6 anh layout can ho The Pavilion theo dung danh sach duoc gui — khong co
// dien tich xac nhan rieng cho tung anh nen de trong nhan, giong cach lam voi
// ZENPARK_LAYOUTS.
const PAVILION_LAYOUTS = [
  { label: "Căn Studio", src: "http://localhost:9000/project-images/the-pavilion/can-ho-studio-p1-vinhomes-ocean-park.jpg" },
  { label: "Căn 1 ngủ", src: "http://localhost:9000/project-images/the-pavilion/can-ho-1-ngu-p1-vinhomes-ocean-park.jpg" },
  { label: "Căn 1 ngủ + 1", src: "http://localhost:9000/project-images/the-pavilion/can-ho-1-ngu-1-p1-vinhomes-ocean-park.jpg" },
  { label: "Căn 2 ngủ (mẫu 1)", src: "http://localhost:9000/project-images/the-pavilion/can-ho-2-ngu-p1-vinhomes-ocean-park-mau-1.jpg" },
  { label: "Căn 2 ngủ (mẫu 2)", src: "http://localhost:9000/project-images/the-pavilion/can-ho-2-ngu-p1-vinhomes-ocean-park-mau-2.jpg" },
  { label: "Căn 3 ngủ", src: "http://localhost:9000/project-images/the-pavilion/can-ho-3-ngu-p1-vinhomes-ocean-park.jpg" },
];

function PavilionLayoutGallery() {
  return (
    <section className="section-block">
      <h3 className="pricing-card-title">Layout căn hộ The Pavilion</h3>
      <div className="layout-gallery">
        {PAVILION_LAYOUTS.map((l, i) => (
          <div key={i} className="layout-gallery-card">
            <img src={l.src} alt={l.label} />
            <p>{l.label}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

// Noi dung "Phan khu The Sapphire" theo dung mau thiet ke nguoi dung gui (khac
// voi "description" ngan trong the_sapphire.json) — Sapphire la 1 PHAN KHU (khong
// phai tieu khu con cua phan khu nao khac), nen dung style "zone-spotlight" tieu
// de giua trang giong OceanViewSpotlight, kem nut CTA, thay vi TowerSpotlight.
function SapphireSpotlight() {
  return (
    <section className="zone-spotlight">
      <h3 className="zone-spotlight-title">Phân khu The Sapphire</h3>
      <p className="zone-spotlight-subtitle">Tâm điểm của thành phố biển hồ</p>

      <div className="zone-spotlight-grid">
        <div className="zone-spotlight-text">
          <p className="page-sub" style={{ maxWidth: "none" }}>
            <strong className="zone-spotlight-lead">The Sapphire</strong> Vinhomes Ocean Park là phân khu căn hộ
            được mở bán đầu tiên của dự án, chính vì vậy mà hiện tại các tòa căn hộ Sapphire đã đạt tỉ lệ lấp kín
            khoảng <strong>70 – 80%</strong>. Sở hữu vị trí trung tâm của dự án, The Sapphire là tâm điểm của nhịp
            sống hiện đại năng động, là tâm điểm cảnh quan với bộ đôi Biển – Hồ và là tâm điểm vị trí — nơi cư dân có
            thể dễ dàng kết nối muôn nơi với các trục đường huyết mạch.
          </p>
          <p className="page-sub" style={{ maxWidth: "none" }}>
            Phân khu The Sapphire bao gồm <strong>27 tòa</strong> căn hộ cao từ 26 – 28 tầng với 2 tiểu khu là:
          </p>
          <ul className="zone-spotlight-list">
            <li>
              <strong>The Sapphire 1 (S1):</strong> 11 tòa căn hộ đánh số từ S1.01 đến S1.12.
            </li>
            <li>
              <strong>The Sapphire 2 (S2):</strong> 16 tòa căn hộ đánh số từ S2.01 đến S2.19.
            </li>
          </ul>
          <p className="page-sub" style={{ maxWidth: "none" }}>
            Các căn hộ tại phân khu The Sapphire là phân khúc căn hộ có giá bán thấp nhất tại dự án Vinhomes Ocean
            Park, chỉ khoảng <strong>30 – 40 triệu/m²</strong> với tiêu chuẩn bàn giao nội thất tiêu chuẩn. Căn hộ có
            diện tích từ khoảng 25 – 98,5m² với các loại hình căn hộ Studio, 1 ngủ, 1 ngủ + 1, 2 ngủ, 2 ngủ + 1 và 3
            ngủ.
          </p>
        </div>
        <div className="zone-spotlight-media">
          <img
            src="http://localhost:9000/project-images/the-sapphire/phan-khu-sapphire-vinhomes-ocean-park.jpg"
            alt="Phân khu The Sapphire"
          />
        </div>
      </div>
    </section>
  );
}

// Noi dung "Phan khu The Senique Hanoi" lay THAT tu the_senique_hanoi.json
// (developer, overview: 3 toa, 2152 can, 37 tang, ban giao Q2/2027, gia tu 68
// trieu/m2, mo hinh Compound dau tien tai Ocean Park) — khong bia, giong cach
// lam voi SapphireSpotlight vi day cung la 1 PHAN KHU doc lap (khong phai tieu
// khu con).
function SeniqueSpotlight() {
  return (
    <section className="zone-spotlight">
      <h3 className="zone-spotlight-title">Phân khu The Senique Hanoi</h3>
      <p className="zone-spotlight-subtitle">Compound khép kín đầu tiên tại Ocean Park</p>

      <div className="zone-spotlight-grid">
        <div className="zone-spotlight-text">
          <p className="page-sub" style={{ maxWidth: "none" }}>
            <strong className="zone-spotlight-lead">The Senique Hanoi</strong> là khu căn hộ cao cấp tọa lạc tại vị
            trí trung tâm Vinhomes Ocean Park, do <strong>CapitaLand Development</strong> (qua Công ty Cổ phần đầu tư
            phát triển kinh doanh Bình Minh) phát triển — dự án đầu tiên theo mô hình{" "}
            <strong>Compound (khu khép kín)</strong> tại Ocean Park.
          </p>
          <p className="page-sub" style={{ maxWidth: "none" }}>
            Dự án gồm <strong>3 tòa</strong> căn hộ cao <strong>37 tầng</strong> — <strong>The Senique 1</strong>,{" "}
            <strong>The Senique 2</strong> và <strong>The Senique Premier</strong>, tổng số khoảng{" "}
            <strong>2.152 căn</strong>.
          </p>
          <p className="page-sub" style={{ maxWidth: "none" }}>
            Căn hộ đa dạng loại hình 1PN, 2PN, 3PN, 4PN, Duplex, Penthouse, giá bán từ khoảng{" "}
            <strong>68 triệu đồng/m²</strong>, sở hữu không thời hạn, dự kiến bàn giao <strong>Quý 2/2027</strong>.
          </p>
        </div>
        <div className="zone-spotlight-media">
          <img
            src="http://localhost:9000/project-images/the-senique-hanoi/the-senique-hanoi-phoi-canh.jpg"
            alt="Phân khu The Senique Hanoi"
          />
        </div>
      </div>
    </section>
  );
}

// Du 22 anh layout can ho The Senique Hanoi — dien tich suy tu chinh ten file
// (vd "813" = 81,3m²) va doi chieu khop voi khoang dien tich that trong
// the_senique_hanoi.json (2PN 54-81m², 3PN 83-108m², 4PN 154-188m², Duplex
// 118-190m²) — khong bia so.
const SENIQUE_LAYOUTS = [
  { label: "Căn 1PN | 42m²", src: "http://localhost:9000/project-images/the-senique-hanoi/can-ho-1PN-medium-42-m2-the-senique-hanoi.jpg" },
  { label: "Căn 2PN | 53,5m²", src: "http://localhost:9000/project-images/the-senique-hanoi/can-ho-2PN-small-535-m2-the-senique-hanoi.jpg" },
  { label: "Căn 2PN | 54,4m²", src: "http://localhost:9000/project-images/the-senique-hanoi/can-ho-2PN-small-544-m2-the-senique-hanoi.jpg" },
  { label: "Căn 2PN | 64,3m²", src: "http://localhost:9000/project-images/the-senique-hanoi/can-ho-2PN-medium-643-m2-the-senique-hanoi.jpg" },
  { label: "Căn 2PN | 81,3m²", src: "http://localhost:9000/project-images/the-senique-hanoi/can-ho-2PN-large-813-m2-the-senique-hanoi.jpg" },
  { label: "Căn 3PN | 83,2m²", src: "http://localhost:9000/project-images/the-senique-hanoi/can-ho-3PN-small-832-m2-the-senique-hanoi.jpg" },
  { label: "Căn 3PN | 84,9m²", src: "http://localhost:9000/project-images/the-senique-hanoi/can-ho-3PN-small-849-m2-the-senique-hanoi.jpg" },
  { label: "Căn 3PN | 85,9m²", src: "http://localhost:9000/project-images/the-senique-hanoi/can-ho-3PN-small-859-m2-the-senique-hanoi.jpg" },
  { label: "Căn 3PN | 96,8m²", src: "http://localhost:9000/project-images/the-senique-hanoi/can-ho-3PN-medium-968-m2-the-senique-hanoi.jpg" },
  { label: "Căn 3PN | 97,3m²", src: "http://localhost:9000/project-images/the-senique-hanoi/can-ho-3PN-medium-973-m2-the-senique-hanoi.jpg" },
  { label: "Căn 3PN | 101,5m²", src: "http://localhost:9000/project-images/the-senique-hanoi/can-ho-3PN-large-1015-m2-the-senique-hanoi.jpg" },
  { label: "Căn 3PN | 107,5m²", src: "http://localhost:9000/project-images/the-senique-hanoi/can-ho-3PN-large-1075-m2-the-senique-hanoi.jpg" },
  { label: "Căn 4PN | 153,6m²", src: "http://localhost:9000/project-images/the-senique-hanoi/can-ho-4PN-large-1536-m2-the-senique-hanoi.jpg" },
  { label: "Căn 4PN | 177,5m²", src: "http://localhost:9000/project-images/the-senique-hanoi/can-ho-4PN-large-1775-m2-the-senique-hanoi.jpg" },
  { label: "Căn 4PN | 187,4m²", src: "http://localhost:9000/project-images/the-senique-hanoi/can-ho-4PN-large-1874-m2-the-senique-hanoi.jpg" },
  { label: "Duplex 117,5m² | Tầng 1", src: "http://localhost:9000/project-images/the-senique-hanoi/can-ho-duplex-small-1175-m2-tang-1-the-senique-hanoi.jpg" },
  { label: "Duplex 117,5m² | Tầng 2", src: "http://localhost:9000/project-images/the-senique-hanoi/can-ho-duplex-small-1175-m2-tang-2-the-senique-hanoi.jpg" },
  { label: "Duplex 133,7m² | Tầng 1", src: "http://localhost:9000/project-images/the-senique-hanoi/can-ho-duplex-medium-1337-m2-tang-1-the-senique-hanoi.jpg" },
  { label: "Duplex 133,7m² | Tầng 2", src: "http://localhost:9000/project-images/the-senique-hanoi/can-ho-duplex-medium-1337-m2-tang-2-the-senique-hanoi.jpg" },
  { label: "Duplex 147,4m² | Tầng 1", src: "http://localhost:9000/project-images/the-senique-hanoi/can-ho-duplex-medium-1474-m2-tang-1-the-senique-hanoi.jpg" },
  { label: "Duplex 147,4m² | Tầng 2", src: "http://localhost:9000/project-images/the-senique-hanoi/can-ho-duplex-medium-1474-m2-tang-2-the-senique-hanoi.jpg" },
  { label: "Duplex 189,5m² | Tầng 1", src: "http://localhost:9000/project-images/the-senique-hanoi/can-ho-duplex-medium-1895-m2-tang-1-the-senique-hanoi.jpg" },
];

// Anh layout can ho da co san day du bang thong tin (loai can, toa, tang, so
// can, DTSD/DTXD) + key plan ngay trong anh — chi can doi bo cuc hien thi sang
// sidebar doc (gon hon luoi 3 cot cu) chu khong can them du lieu gi.
function SidebarLayoutTabs({ title, tabs }: { title: string; tabs: { label: string; src: string }[] }) {
  const [active, setActive] = useState(0);

  return (
    <section className="section-block">
      <h3 className="pricing-card-title">{title}</h3>
      <div className="layout-sidebar">
        <div className="layout-sidebar-nav">
          {tabs.map((t, i) => (
            <button
              key={i}
              type="button"
              className={`layout-sidebar-tab ${active === i ? "layout-sidebar-tab--active" : ""}`}
              onClick={() => setActive(i)}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="layout-sidebar-body">
          <img src={tabs[active].src} alt={tabs[active].label} />
        </div>
      </div>
    </section>
  );
}

function SeniqueLayoutGallery() {
  return <SidebarLayoutTabs title="Layout căn hộ tòa The Senique Hanoi" tabs={SENIQUE_LAYOUTS} />;
}

// Anh mat bang tang thuc te The Senique Hanoi — 3 toa (Senique 1, Senique 2,
// Senique Premier), moi toa co nhieu nhom tang khac nhau (theo dung file anh
// duoc upload san tren MinIO tu truoc, khong thieu toa nao).
const SENIQUE_1_FLOOR_PLANS = [
  { label: "Tầng 2-18", src: "http://localhost:9000/project-images/the-senique-hanoi/mat-bang-tang-2-4-6-8-10-12-14-16-18-toa-the-senique-1-ocean-park-1.jpg" },
  { label: "Tầng 3-17", src: "http://localhost:9000/project-images/the-senique-hanoi/mat-bang-tang-3-5-7-9-11-13-15-17-toa-the-senique-1-ocean-park.jpg" },
  { label: "Tầng 20", src: "http://localhost:9000/project-images/the-senique-hanoi/mat-bang-tang-20-toa-the-senique-1-ocean-park.jpg" },
  { label: "Tầng 21, 23", src: "http://localhost:9000/project-images/the-senique-hanoi/mat-bang-tang-21-23-toa-the-senique-1-ocean-park.jpg" },
  { label: "Tầng 22", src: "http://localhost:9000/project-images/the-senique-hanoi/mat-bang-tang-22-toa-the-senique-1-ocean-park.jpg" },
  { label: "Tầng 24-34", src: "http://localhost:9000/project-images/the-senique-hanoi/mat-bang-tang-24-26-28-30-32-34-toa-the-senique-1-ocean-park.jpg" },
  { label: "Tầng 25-35", src: "http://localhost:9000/project-images/the-senique-hanoi/mat-bang-tang-25-27-29-31-33-35-toa-the-senique-1-ocean-park.jpg" },
  { label: "Tầng 36", src: "http://localhost:9000/project-images/the-senique-hanoi/mat-bang-tang-36-toa-the-senique-1-ocean-park.jpg" },
  { label: "Tầng 37", src: "http://localhost:9000/project-images/the-senique-hanoi/mat-bang-tang-37-toa-the-senique-1-ocean-park.jpg" },
];

const SENIQUE_2_FLOOR_PLANS = [
  { label: "Tầng 2-18", src: "http://localhost:9000/project-images/the-senique-hanoi/mat-bang-tang-2-4-6-8-10-12-14-16-18-toa-the-senique-2-ocean-park-1.jpg" },
  { label: "Tầng 3-17", src: "http://localhost:9000/project-images/the-senique-hanoi/mat-bang-tang-3-5-7-9-11-13-15-17-toa-the-senique-2-ocean-park.jpg" },
  { label: "Tầng 20", src: "http://localhost:9000/project-images/the-senique-hanoi/mat-bang-tang-20-toa-the-senique-2-ocean-park.jpg" },
  { label: "Tầng 21, 23", src: "http://localhost:9000/project-images/the-senique-hanoi/mat-bang-tang-21-23-toa-the-senique-2-ocean-park.jpg" },
  { label: "Tầng 22", src: "http://localhost:9000/project-images/the-senique-hanoi/mat-bang-tang-22-toa-the-senique-2-ocean-park.jpg" },
  { label: "Tầng 24-34", src: "http://localhost:9000/project-images/the-senique-hanoi/mat-bang-tang-24-26-28-30-32-34-toa-the-senique-2-ocean-park.jpg" },
  { label: "Tầng 25-35", src: "http://localhost:9000/project-images/the-senique-hanoi/mat-bang-tang-25-27-29-31-33-35-toa-the-senique-2-ocean-park-2048x1463.jpg" },
  { label: "Tầng 36", src: "http://localhost:9000/project-images/the-senique-hanoi/mat-bang-tang-36-toa-the-senique-2-ocean-park.jpg" },
];

const SENIQUE_PREMIER_FLOOR_PLANS = [
  { label: "Tầng 3-17", src: "http://localhost:9000/project-images/the-senique-hanoi/mat-bang-tang-3-5-7-9-11-13-15-17-toa-the-senique-premier.jpg" },
  { label: "Tầng 21", src: "http://localhost:9000/project-images/the-senique-hanoi/mat-bang-tang-21-toa-the-senique-premier.jpg" },
  { label: "Tầng 22-34", src: "http://localhost:9000/project-images/the-senique-hanoi/mat-bang-tang-22-24-26-28-30-32-34-toa-the-senique-premier-ocean-park.jpg" },
  { label: "Tầng 23-35", src: "http://localhost:9000/project-images/the-senique-hanoi/mat-bang-tang-23-25-27-29-31-33-35-toa-the-senique-premier.jpg" },
  { label: "Tầng 36", src: "http://localhost:9000/project-images/the-senique-hanoi/mat-bang-tang-36-toa-the-senique-premier.jpg" },
  { label: "Tầng 37", src: "http://localhost:9000/project-images/the-senique-hanoi/mat-bang-tang-37-toa-the-senique-premier.jpg" },
];

// Anh mat bang thuc te The Sapphire — du an chia 2 khu (Sapphire 1: 12 toa,
// Sapphire 2: 19 toa). Anh nguon chi co 9/12 toa S1 (thieu S1.01/03/04) va
// 1/19 toa S2 (S2.17) — CHI liet ke dung so toa co anh that, khong bia them
// toa chua co anh (tranh hien thi sai/gay nham lan cho sale).
const SAPPHIRE_FLOOR_PLANS = [
  { label: "Khu Sapphire 1", src: "http://localhost:9000/project-images/the-sapphire/mat-bang-khu-sapphire-1-vinhomes-ocean-park.jpg" },
  { label: "Tòa S1.02", src: "http://localhost:9000/project-images/the-sapphire/mat-bang-toa-s1-02-vinhomes-ocean-park.jpg" },
  { label: "Tòa S1.05", src: "http://localhost:9000/project-images/the-sapphire/mat-bang-toa-s1-05-vinhomes-ocean-park.jpg" },
  { label: "Tòa S1.06", src: "http://localhost:9000/project-images/the-sapphire/mat-bang-toa-s1-06-vinhomes-ocean-park.jpg" },
  { label: "Tòa S1.07", src: "http://localhost:9000/project-images/the-sapphire/mat-bang-toa-s1-07-vinhomes-ocean-park.jpg" },
  { label: "Tòa S1.08", src: "http://localhost:9000/project-images/the-sapphire/mat-bang-toa-s1-08-vinhomes-ocean-park.jpg" },
  { label: "Tòa S1.09", src: "http://localhost:9000/project-images/the-sapphire/mat-bang-toa-s1-09-sapphire-1.jpg" },
  { label: "Tòa S1.10", src: "http://localhost:9000/project-images/the-sapphire/mat-bang-toa-s1-10-vinhomes-ocean-park.jpg" },
  { label: "Tòa S1.11", src: "http://localhost:9000/project-images/the-sapphire/mat-bang-toa-s1-11-vinhomes-ocean-park.jpg" },
  { label: "Tòa S1.12", src: "http://localhost:9000/project-images/the-sapphire/mat-bang-toa-s1-12-vinhomes-ocean-park.jpg" },
  { label: "Khu Sapphire 2", src: "http://localhost:9000/project-images/the-sapphire/mat-bang-khu-sapphire-2-vinhomes-ocean-park.jpg" },
  { label: "Tòa S2.17", src: "http://localhost:9000/project-images/the-sapphire/mat-bang-toa-s2-17-vinhomes-ocean-park.jpg" },
];

// Bang gia rieng cua The Palma, doc that qua API (khong code cung so lieu) —
// dung chung logic voi trang chi tiet du an (fetchProjectDetail).
function PriceTable({ projectId }: { projectId: string }) {
  const [detail, setDetail] = useState<ProjectFullDetail | null>(null);

  useEffect(() => {
    fetchProjectDetail(projectId)
      .then(setDetail)
      .catch(() => setDetail(null));
  }, [projectId]);

  if (!detail || detail.pricing.length === 0) return null;

  return (
    <section className="price-table-brown">
      <h3 className="price-table-brown-title">Bảng giá {detail.name}</h3>
      <p className="price-table-brown-note">
        Bảng giá {detail.name} dưới đây chỉ là <strong>khoảng giá Min – Max</strong> được chủ đầu tư công bố để Quý
        khách hàng cân đối đưa ra quyết định đặt chỗ. Giá bán chi tiết từng căn hộ sẽ phụ thuộc vào vị trí tòa,
        khoảng tầng, hướng ban công, thời điểm ra hàng và sẽ chỉ được công bố tại thời điểm ra mắt chính thức dự án.
      </p>
      <div className="price-table-brown-wrap">
        <div className="price-table-brown-row price-table-brown-row--head">
          <span>Loại hình</span>
          <span>Diện tích</span>
          <span>Giá bán</span>
        </div>
        {detail.pricing.map((p, i) => (
          <div key={`${p.apartmentType}-${i}`} className="price-table-brown-row">
            <span>{p.apartmentType}</span>
            <span>{p.sizeRange}</span>
            <span>{p.priceRange}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

// Anh mat bang tang thuc te cua 2 toa The Palma — da co san tren MinIO tu luc
// upload anh du an "the-palma" (khong can copy lai vao public/).
const PALMA_FLOOR_PLANS = [
  {
    label: "Tòa PALMA 1",
    src: "http://localhost:9000/project-images/the-palma/mat-bang-tang-6-17-toa-palma-1-lumiere-orient-pearl.jpg",
  },
  {
    label: "Tòa PALMA 2",
    src: "http://localhost:9000/project-images/the-palma/mat-bang-tang-6-18-toa-palma-2-lumiere-orient-pearl.jpg",
  },
];

// Anh mat bang tang thuc te 4 toa The Beverly — da co san tren MinIO tu luc
// upload anh du an "the-beverly".
const BEVERLY_FLOOR_PLANS = [
  { label: "Tòa BE1", src: "http://localhost:9000/project-images/the-beverly/mat-bang-toa-be1-vinhomes-ocean-park-2048x1447.jpg" },
  { label: "Tòa BE2", src: "http://localhost:9000/project-images/the-beverly/mat-bang-tang-3-24-toa-be2-phan-khu-the-beverly-vinhomes-ocean-park-2048x1447.jpg" },
  { label: "Tòa BE3", src: "http://localhost:9000/project-images/the-beverly/mat-bang-tang-3-24-toa-be3-the-beverly-vinhomes-ocean-park-2048x1447.jpg" },
  { label: "Tòa BE4", src: "http://localhost:9000/project-images/the-beverly/mat-bang-toa-be4-the-beverly-vinhomes-ocean-park-2048x1447.jpg" },
];

// Anh mat bang tang thuc te 4/5 toa The Paris co san tren MinIO (khong co mat
// bang rieng cho PR6 trong danh sach anh duoc gui).
const PARIS_FLOOR_PLANS = [
  { label: "Tòa PR1", src: "http://localhost:9000/project-images/the-paris/mat-bang-toa-pr1-the-paris-vinhomes-ocean-park-2048x1170.jpg" },
  { label: "Tòa PR2", src: "http://localhost:9000/project-images/the-paris/mat-bang-toa-pr2-the-paris-vinhomes-ocean-park-2048x1449.jpg" },
  { label: "Tòa PR3", src: "http://localhost:9000/project-images/the-paris/mat-bang-toa-pr3-phan-khu-the-paris-vinhomes-ocean-park-2048x1448.jpg" },
  { label: "Tòa PR5", src: "http://localhost:9000/project-images/the-paris/mat-bang-toa-pr5-the-paris-vinhomes-ocean-park-2048x1170.jpg" },
];

// Vi tri 5 toa tren anh vi-tri-the-paris-ocean-park-2048x1170.jpg — uoc luong
// bang mat, doi chieu voi anh mau tham khao co san nhan (PR1..PR6, danh so 1-5
// theo dung thu tu nhan trong anh mau: PR6=5, PR1=1, PR5=4, PR2=2, PR3=3).
const PARIS_LOCATIONS = [
  { number: 1, name: "Tòa PR1", left: "40%", top: "46%" },
  { number: 2, name: "Tòa PR2", left: "45%", top: "53%" },
  { number: 3, name: "Tòa PR3", left: "29%", top: "62%" },
  { number: 4, name: "Tòa PR5", left: "22%", top: "55%" },
  { number: 5, name: "Tòa PR6", left: "24%", top: "44%" },
];

function ParisLocationMap() {
  return (
    <section className="section-block location-map-section--dark">
      <div className="location-map-wrap">
        <img
          src="http://localhost:9000/project-images/the-paris/vi-tri-the-paris-ocean-park-2048x1170.jpg"
          alt="Vị trí các tòa The Paris"
          className="location-map-img"
        />
        {PARIS_LOCATIONS.map((loc) => (
          <div key={loc.name} className="location-pin" style={{ left: loc.left, top: loc.top }}>
            <span className="location-pin-label">{loc.name}</span>
            <span className="location-pin-dot">{loc.number}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

// Tab mat bang tang — tai su dung cho Palma (2 toa), Beverly (4 toa) va cac
// tieu khu khac sau nay, chi can doi title + danh sach tabs.
function FloorPlanTabs({
  title,
  tabs,
  compact = false,
}: {
  title: string;
  tabs: { label: string; src: string }[];
  /** true = gioi han chieu cao anh, dung cho anh vi tri/phoi canh kho dung/doc
   * de tranh chiem qua nhieu khong gian (vd Vi tri & Phoi canh Ngoc Trai). */
  compact?: boolean;
}) {
  const [active, setActive] = useState(0);

  return (
    <section className="floor-plan-tabs">
      <h3 className="floor-plan-tabs-title">{title}</h3>
      <div className="floor-plan-tabs-nav">
        {tabs.map((t, i) => (
          <button
            key={t.label}
            type="button"
            className={`floor-plan-tab ${active === i ? "floor-plan-tab--active" : ""}`}
            onClick={() => setActive(i)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="floor-plan-tabs-body">
        <img
          src={tabs[active].src}
          alt={`Mặt bằng ${tabs[active].label}`}
          className={compact ? "floor-plan-tabs-img floor-plan-tabs-img--compact" : "floor-plan-tabs-img"}
        />
      </div>
    </section>
  );
}

// "The Metropolitan" la nhom cha (4 tieu khu Beverly/London/Paris/Zurich), khong
// phai 1 project rieng trong DB nen KHONG the fetch API — noi dung o day la viet
// tay, dua tren so lieu that da xac minh: Beverly 4 toa (BE1-BE4), London 3 toa
// (LD1-LD3), Paris 5 toa (PR1,PR2,PR3,PR5,PR6), Zurich 3 toa (ZR1-ZR3) = 15 toa,
// developer Vingroup + Mitsubishi Corporation (tu the_beverly/the_zurich...json).
function MetropolitanSpotlight() {
  return (
    <section className="zone-spotlight zone-spotlight--dark">
      <h3 className="zone-spotlight-title zone-spotlight-title--light">Phân khu The Metropolitan</h3>
      <p className="zone-spotlight-subtitle zone-spotlight-subtitle--light">Điểm đến thượng lưu quận Ocean</p>
      <div className="zone-spotlight-grid">
        <div className="zone-spotlight-text zone-spotlight-text--light">
          <p className="page-sub zone-spotlight-text--light" style={{ maxWidth: "none" }}>
            <strong>The Metropolitan</strong> là phân khu căn hộ do <strong>Vingroup</strong> và{" "}
            <strong>Mitsubishi Corporation</strong> phát triển tại Vinhomes Ocean Park, mở bán tiếp theo phân khu The
            Ocean View.
          </p>
          <p className="page-sub zone-spotlight-text--light" style={{ maxWidth: "none" }}>
            Phân khu gồm <strong>4 tiểu khu</strong> với tổng cộng <strong>15 tòa</strong> căn hộ cao cấp:
          </p>
          <ul className="zone-spotlight-list zone-spotlight-list--light">
            <li>
              <strong>The Beverly:</strong> 4 tòa (BE1 – BE4)
            </li>
            <li>
              <strong>The London:</strong> 3 tòa (LD1 – LD3)
            </li>
            <li>
              <strong>The Paris:</strong> 5 tòa (PR1, PR2, PR3, PR5, PR6)
            </li>
            <li>
              <strong>The Zurich:</strong> 3 tòa (ZR1 – ZR3)
            </li>
          </ul>
          <p className="page-sub zone-spotlight-text--light" style={{ maxWidth: "none" }}>
            Căn hộ tại The Metropolitan có giá bán từ khoảng <strong>1,3 tỷ đồng</strong>, đa dạng loại hình từ
            Studio đến nhiều phòng ngủ, tuỳ theo từng tiểu khu.
          </p>
        </div>
        <div className="zone-spotlight-media">
          <img src="/the-metropolitan-vinhomes-ocean-park.jpg" alt="The Metropolitan" />
        </div>
      </div>
    </section>
  );
}

// Vi tri 4 tieu khu tren anh vi-tri-the-metropolitan-vinhomes-ocean-park.jpg —
// CHI CHAC CHAN "The Zurich" (khop dung anh mau tham khao co ghi nhan). 3 khu con
// lai (Beverly/London/Paris) la UOC LUONG theo mo ta vi tri thuc te trong data
// (Beverly o vi tri trung tam, Paris tiep giap Zurich) — can ban xac nhan lai.
// Chi giu "The Zurich" — day la vi tri DUY NHAT khop voi anh mau tham khao (khu
// mau xanh). 3 khu con lai (Beverly/London/Paris) chua co nguon xac nhan vi tri
// nen KHONG danh dau (tranh ghi sai), se bo sung khi co du lieu chac chan hon.
const METROPOLITAN_LOCATIONS = [{ number: 1, name: "The Zurich", left: "72%", top: "34%" }];

// Vi tri "The Beverly" — khop voi khu mau VANG trong anh mau tham khao
// vi-tri-the-metropolitan-vinhomes-ocean-park.jpg (rieng biet voi khu mau xanh
// cua Zurich). Dung mau vang (#ffd400) cho dot so 2 de khop dung mau khu tren anh.
const BEVERLY_LOCATION = [{ number: 2, name: "The Beverly", left: "62%", top: "42%", color: "#ffd400" }];

function MetropolitanLocationMap({
  locations = METROPOLITAN_LOCATIONS,
}: {
  locations?: { number: number; name: string; left: string; top: string; color?: string }[];
}) {
  return (
    <section className="section-block location-map-section--dark">
      <div className="location-map-wrap">
        <img
          src="/vi-tri-the-metropolitan-vinhomes-ocean-park.jpg"
          alt="Vị trí các tiểu khu The Metropolitan"
          className="location-map-img"
        />
        {locations.map((loc) => (
          <div key={loc.name} className="location-pin" style={{ left: loc.left, top: loc.top }}>
            <span className="location-pin-label">{loc.name}</span>
            <span className="location-pin-dot" style={loc.color ? { background: loc.color } : undefined}>
              {loc.number}
            </span>
          </div>
        ))}
      </div>
    </section>
  );
}

// Banner nen dam danh dau diem bat dau 1 khu/tieu khu moi (tai su dung mau dark
// da co san o MetropolitanSpotlight) — dat o DAU moi block tieu khu/day shop de
// nguoi dung de nhan biet ranh gioi khi cuon qua khu khac, khong can doi lai
// toan bo phan noi dung ben duoi (van giu nen sang nhu cu, tranh phai re-theme
// lai FloorPlanTabs/PriceTable... cho nen toi).
function ZoneHeaderBanner({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <div className="zone-spotlight--dark zone-header-banner">
      <h3 className="zone-spotlight-title zone-spotlight-title--light">{title}</h3>
      {subtitle && <p className="zone-spotlight-subtitle zone-spotlight-subtitle--light">{subtitle}</p>}
    </div>
  );
}

// Spotlight 1 tieu khu con (khac Lumiere/Metropolitan — day la TIEU KHU, dung
// lai dung "detail.description" THAT tu API thay vi viet tay, vi mo ta trong
// data da rat day du (khop gan nguyen van nguon tham khao). Tai su dung duoc
// cho Beverly/London/Paris sau nay, chi can doi projectId + image.
function TowerSpotlight({
  projectId,
  image,
  oval = true,
  hideImage = false,
}: {
  projectId: string;
  image: string;
  /** false = anh chu nhat bo goc binh thuong, thu nho hon oval — dung khi da
   * co san 1 khoi anh vi tri/phoi canh rieng ngay ben duoi (vd Ngoc Trai), oval
   * to lai thanh thua. */
  oval?: boolean;
  /** true = an han khoi anh ben phai, chi hien text gioi thieu. */
  hideImage?: boolean;
}) {
  const [detail, setDetail] = useState<ProjectFullDetail | null>(null);

  useEffect(() => {
    fetchProjectDetail(projectId)
      .then(setDetail)
      .catch(() => setDetail(null));
  }, [projectId]);

  if (!detail) return null;

  return (
    <section className={hideImage ? "zone-spotlight-grid zone-spotlight-grid--solo section-block" : "zone-spotlight-grid section-block"}>
      <div className="intro-text">
        <h3 className="intro-title">
          <span className="intro-title-bar" />
          Tiểu khu {detail.name}
        </h3>
        <p className="page-sub" style={{ maxWidth: "none" }}>
          {detail.description}
        </p>
      </div>
      {!hideImage && (
        <div className={oval ? "zone-spotlight-media" : "zone-spotlight-media zone-spotlight-media--rect"}>
          <img src={image} alt={detail.name} />
        </div>
      )}
    </section>
  );
}

// Du 9 file anh thuc te cua The Zurich (theo dung danh sach ban gui). Size chi
// dien khi da doi chieu khop voi anh mau tham khao thuc; 2 file khong co size
// xac nhan (studio-zr2, 3-ngu-zr1) de trong theo yeu cau, khong bia so.
const ZURICH_LAYOUTS = [
  { label: "Căn Studio", size: "36m²", src: "http://localhost:9000/project-images/the-zurich/can-ho-studio-zr1-vinhomes-ocean-park.jpg" },
  { label: "Căn Studio", size: "", src: "http://localhost:9000/project-images/the-zurich/can-ho-studio-zr2-vinhomes-ocean-park.jpg" },
  { label: "Căn 1 ngủ", size: "47m²", src: "http://localhost:9000/project-images/the-zurich/can-ho-1-ngu-zr1-vinhomes-ocean-park.jpg" },
  { label: "Căn 1 ngủ", size: "47m²", src: "http://localhost:9000/project-images/the-zurich/can-ho-1-ngu-zr1-vinhomes-ocean-park-2.jpg" },
  { label: "Căn 1 ngủ", size: "47m²", src: "http://localhost:9000/project-images/the-zurich/can-ho-1-ngu-zr1-vinhomes-ocean-park-3.jpg" },
  { label: "Căn 2 ngủ", size: "54m²", src: "http://localhost:9000/project-images/the-zurich/can-ho-2-ngu-zr1-vinhomes-ocean-park.jpg" },
  { label: "Căn 2 ngủ", size: "74,3m²", src: "http://localhost:9000/project-images/the-zurich/can-ho-2-ngu-zr2-vinhomes-ocean-park.jpg" },
  { label: "Căn 3 ngủ", size: "", src: "http://localhost:9000/project-images/the-zurich/can-ho-3-ngu-zr1-vinhomes-ocean-park.jpg" },
  { label: "Căn 3 ngủ", size: "105m²", src: "http://localhost:9000/project-images/the-zurich/can-ho-3-ngu-zr2-vinhomes-ocean-park.jpg" },
];

function ZurichLayoutGallery() {
  return (
    <section className="section-block">
      <h3 className="pricing-card-title">Layout căn hộ The Zurich</h3>
      <div className="layout-gallery">
        {ZURICH_LAYOUTS.map((l, i) => (
          <div key={i} className="layout-gallery-card">
            <img src={l.src} alt={`${l.label} ${l.size}`} />
            <p>{l.size ? `${l.label} | ${l.size}` : l.label}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

// Anh mat bang tang thuc te 3 toa The London — da co san tren MinIO tu luc
// upload anh du an "the-london".
const LONDON_FLOOR_PLANS = [
  {
    label: "Tòa LD1",
    src: "http://localhost:9000/project-images/the-london/mat-bang-tang-10-29-toa-ld1-the-london-vinhomes-ocean-park-2048x1448.jpg",
  },
  {
    label: "Tòa LD2",
    src: "http://localhost:9000/project-images/the-london/mat-bang-tang-5-26-toa-ld2-the-london-vinhomes-ocean-park-2048x1448.jpg",
  },
  {
    label: "Tòa LD3",
    src: "http://localhost:9000/project-images/the-london/mat-bang-toa-ld3-vinhomes-ocean-park-2048x1439.jpg",
  },
];

// Banner vang "TONG MAT BANG CAC PHAN KHU BIET THU" dung dung anh mau tham
// khao nguoi dung gui (co san pin so tren anh mau) — toa do pin doc lai truc
// tiep tu vi tri pin trong chinh anh mau do (khong con doan qua mau khac nhu
// truoc), theo dung mapping: 1 Ngoc Trai, 2 San Ho, 3 Hai Au, 4 Sao Bien.
const VILLA_LOCATIONS = [
  { number: 1, name: "Ngọc Trai", left: "34%", top: "43%" },
  { number: 2, name: "San Hô", left: "40%", top: "20%" },
  { number: 3, name: "Hải Âu", left: "24%", top: "16%" },
  { number: 4, name: "Sao Biển", left: "14%", top: "34%" },
];

function VillaLocationMap() {
  return (
    <section className="villa-map-banner">
      <h3 className="villa-map-banner-title">Tổng mặt bằng các phân khu Biệt thự</h3>
      <div className="location-map-wrap">
        <img
          src="http://localhost:9000/project-images/ngoc-trai/tong-the-vinhomes-ocean-park.jpg"
          alt="Tổng mặt bằng các phân khu Biệt thự Vinhomes Ocean Park"
          className="location-map-img"
        />
        {VILLA_LOCATIONS.map((loc) => (
          <span key={loc.name} className="villa-map-pin" style={{ left: loc.left, top: loc.top }}>
            {loc.number}
            <span className="villa-map-pin-tooltip">{loc.name}</span>
          </span>
        ))}
      </div>
    </section>
  );
}

// 4 anh "anh-biet-thu-1..4" theo dung ten file nguoi dung yeu cau — dung lam
// gallery: anh dau tien la anh lon mac dinh, lướt/bam vao 1 trong 4 thumbnail
// se doi anh lon tuong ung (xem VillaOverviewIntro).
const VILLA_OVERVIEW_PHOTOS = [
  "http://localhost:9000/project-images/ngoc-trai/anh-biet-thu-1.jpg",
  "http://localhost:9000/project-images/ngoc-trai/anh-biet-thu-2.jpg",
  "http://localhost:9000/project-images/ngoc-trai/anh-biet-thu-3.jpg",
  "http://localhost:9000/project-images/ngoc-trai/anh-biet-thu-4.jpg",
];

// Noi dung phan text (so lieu quy mo/ban giao/phap ly) KHONG lay tu du lieu
// crawl (hai_au.json/ngoc_trai.json/sao_bien.json khong co so luong can hay
// nam khoi cong) — day la text go tay, chep dung nguyen van tu anh chup man
// hinh trang mau nguoi dung gui truoc do, vi khong co truong API nao mang so
// lieu nay ca.
function VillaOverviewIntro() {
  const [activePhoto, setActivePhoto] = useState(0);

  return (
    <section className="section-block intro-grid">
      <div className="intro-text">
        <h3 className="intro-title">
          <span className="intro-title-bar" />
          Tổng quan biệt thự Vinhomes Ocean Park
        </h3>
        <p className="page-sub" style={{ maxWidth: "none" }}>
          <strong>Quy mô số lượng:</strong> khoảng 3.500 căn.
        </p>
        <p className="page-sub" style={{ maxWidth: "none" }}>
          <strong>Các loại hình phát triển:</strong> Biệt thự đơn lập, song lập, liền kề, shophouse và shop thương
          mại dịch vụ.
        </p>
        <p className="page-sub" style={{ maxWidth: "none", marginBottom: 4 }}>
          <strong>Các phân khu biệt thự:</strong>
        </p>
        <ul className="zone-spotlight-list">
          <li>
            <strong>Ngọc Trai:</strong> 458 căn, phân khu đóng, có chốt an ninh tại cổng vào.
          </li>
          <li>
            <strong>San Hô:</strong> 329 căn, phân khu mở.
          </li>
          <li>
            <strong>Hải Âu:</strong> 512 căn, phân khu mở.
          </li>
          <li>
            <strong>Sao Biển:</strong> 788 căn, phân khu mở.
          </li>
          <li>
            <strong>Shop thương mại dịch vụ:</strong> khoảng 1.500 căn.
          </li>
        </ul>
        <p className="page-sub" style={{ maxWidth: "none" }}>
          <strong>Khởi công:</strong> từ năm 2018.
        </p>
        <p className="page-sub" style={{ maxWidth: "none" }}>
          <strong>Bàn giao:</strong> từ cuối năm 2019.
        </p>
        <p className="page-sub" style={{ maxWidth: "none", marginBottom: 4 }}>
          <strong>Pháp lý:</strong>
        </p>
        <ul className="zone-spotlight-list">
          <li>Biệt thự, liền kề và shophouse: Không thời hạn.</li>
          <li>Shop thương mại dịch vụ: 50 năm.</li>
        </ul>
      </div>
      <div>
        <div className="location-map-wrap" style={{ marginBottom: 10 }}>
          <img
            src={VILLA_OVERVIEW_PHOTOS[activePhoto]}
            alt="Biệt thự Vinhomes Ocean Park"
            className="location-map-img"
          />
        </div>
        <div className="layout-gallery" style={{ gridTemplateColumns: "repeat(4, 1fr)", gap: 10 }}>
          {VILLA_OVERVIEW_PHOTOS.map((src, i) => (
            <button
              key={src}
              type="button"
              className={`layout-gallery-card layout-gallery-card--thumb ${i === activePhoto ? "layout-gallery-card--active" : ""}`}
              onMouseEnter={() => setActivePhoto(i)}
              onClick={() => setActivePhoto(i)}
            >
              <img src={src} alt="Biệt thự Vinhomes Ocean Park" />
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}

// Tab "Vi tri / Phoi canh" rieng cho Ngoc Trai — tham khao thiet ke trang mau
// (co them tab "Vi tri cac Tieu khu" nhung da co san o VillaLocationMap phia
// tren roi nen chi giu 2 tab con lai, tranh trung lap).
const NGOC_TRAI_LOCATION_TABS = [
  { label: "Vị trí Tiểu khu Ngọc Trai", src: "http://localhost:9000/project-images/ngoc-trai/vinhomes-ocean-park-ngoc-trai.jpg" },
  { label: "Phối cảnh Ngọc Trai", src: "http://localhost:9000/project-images/ngoc-trai/phan-khu-ngoc-trai-vinhomes-ocean-park.jpg" },
];

// Dien tich/so tang cac loai biet thu Ngoc Trai — lay dung tu pricing trong
// ngoc_trai.json (size_min_sqm/size_max_sqm/storeys), khong bia them so lieu.
const NGOC_TRAI_UNIT_TYPES = [
  { label: "Biệt thự đơn lập", size: "227,5 – 347,5m²", storeys: "3 tầng nổi và 1 tum" },
  { label: "Biệt thự song lập", size: "135 – 338m²", storeys: "3 tầng nổi và 1 tum" },
  { label: "Biệt thự liền kề", size: "70,8 - 121m²", storeys: "4 tầng nổi và 1 tum" },
  { label: "Nhà phố shophouse", size: "67,2 – 102m²", storeys: "4 tầng nổi và 1 tum" },
];

// Anh phoi canh (ngoai that) tung loai biet thu Ngoc Trai — muc rieng ngay
// duoi phan gioi thieu dien tich, TRUOC muc "mat bang" (ban ve ky thuat).
const NGOC_TRAI_UNIT_PHOTOS = [
  { label: "Đơn lập", src: "http://localhost:9000/project-images/ngoc-trai/vinhomes-ocean-park-don-lap.jpg" },
  { label: "Song lập", src: "http://localhost:9000/project-images/ngoc-trai/vinhomes-ocean-park-song-lap.jpg" },
  { label: "Liền kề", src: "http://localhost:9000/project-images/ngoc-trai/lien-ke-vinhomes-ocean-park.jpg" },
  { label: "Shophouse", src: "http://localhost:9000/project-images/ngoc-trai/vinhomes-ocean-park-shop-house.jpg" },
];

// Mat bang thuc te Ngoc Trai — co du don lap/song lap/lien ke/shophouse (theo
// dung file anh duoc crawl, khong bia them loai chua co anh).
const NGOC_TRAI_FLOOR_PLANS = [
  { label: "Đơn lập", src: "http://localhost:9000/project-images/ngoc-trai/don-lap-ngoc-trai-vinhomes-ocean-park-1500x925.jpg" },
  { label: "Song lập", src: "http://localhost:9000/project-images/ngoc-trai/song-lap-lap-ngoc-trai-vinhomes-ocean-park-1500x1024.jpg" },
  { label: "Song lập (mẫu 2)", src: "http://localhost:9000/project-images/ngoc-trai/song-lap-2-ngoc-trai-vinhomes-ocean-park-1500x968.jpg" },
  { label: "Liền kề", src: "http://localhost:9000/project-images/ngoc-trai/lien-ke-ngoc-trai-vinhomes-ocean-park-1500x959.jpg" },
  { label: "Shophouse (mẫu 1)", src: "http://localhost:9000/project-images/ngoc-trai/shophouse-1-ngoc-trai-vinhomes-ocean-park-1500x1009.jpg" },
  { label: "Shophouse (mẫu 2)", src: "http://localhost:9000/project-images/ngoc-trai/shophouse-2-ngoc-trai-vinhomes-ocean-park-1500x919.jpg" },
];

// Mat bang thuc te Hai Au — moi loai co 2 mau (theo dung file anh duoc crawl).
const HAI_AU_FLOOR_PLANS = [
  { label: "Đơn lập (mẫu 1)", src: "http://localhost:9000/project-images/hai-au/mat-bang-don-lap-1-hai-au-1202x1500.jpg" },
  { label: "Đơn lập (mẫu 2)", src: "http://localhost:9000/project-images/hai-au/mat-bang-don-lap-2-hai-au-1213x1500.jpg" },
  { label: "Song lập (mẫu 1)", src: "http://localhost:9000/project-images/hai-au/mat-bang-song-lap-1-hai-au-1217x1500.jpg" },
  { label: "Song lập (mẫu 2)", src: "http://localhost:9000/project-images/hai-au/mat-bang-song-lap-2-hai-au-1199x1500.jpg" },
  { label: "Liền kề (mẫu 1)", src: "http://localhost:9000/project-images/hai-au/mat-bang-lien-ke-1-hai-au-1162x1500.jpg" },
  { label: "Liền kề (mẫu 2)", src: "http://localhost:9000/project-images/hai-au/mat-bang-lien-ke-2-hai-au-1212x1500.jpg" },
];

// Tab "Vi tri" cho Hai Au — chi co 1 anh vi tri tong the (khong co anh "phoi
// canh tong the" rieng nhu Ngoc Trai; 3 anh phoi canh tung loai biet thu dung
// rieng o HAI_AU_UNIT_PHOTOS, giong cach Ngoc Trai tach 2 muc).
const HAI_AU_LOCATION_TABS = [
  { label: "Vị trí Tiểu khu Hải Âu", src: "http://localhost:9000/project-images/hai-au/vinhomes-ocean-park-hai-au.jpg" },
];

// Anh phoi canh (ngoai that) tung loai biet thu Hai Au — muc rieng ngay duoi
// phan gioi thieu dien tich, TRUOC muc "mat bang" (ban ve ky thuat), giong cau
// truc 2 muc cua Ngoc Trai (anh phoi canh vs ban ve mat bang).
const HAI_AU_UNIT_PHOTOS = [
  { label: "Đơn lập", src: "http://localhost:9000/project-images/hai-au/don-lap-hai-au.jpg" },
  { label: "Song lập", src: "http://localhost:9000/project-images/hai-au/song-lap-hai-au.jpg" },
  { label: "Liền kề", src: "http://localhost:9000/project-images/hai-au/lien-ke-vinhomes-ocean-park.jpg" },
];

// Dien tich/so tang cac loai biet thu Hai Au — lay dung tu pricing trong
// hai_au.json, khong bia them so lieu.
const HAI_AU_UNIT_TYPES = [
  { label: "Biệt thự đơn lập", size: "141,47 – 417,52m²", storeys: "3 tầng nổi và 1 tum" },
  { label: "Biệt thự song lập", size: "148 – 154,61m²", storeys: "3 tầng nổi và 1 tum" },
  { label: "Biệt thự liền kề", size: "89,96 – 145m²", storeys: "4 tầng nổi và 1 tum" },
];

// Tab "Vi tri / Phoi canh" cho Sao Bien — chi co 2 anh tong the (khong co anh
// phoi canh tung loai biet thu rieng nhu Hai Au, cung khong co anh mat bang
// tung loai nhu Ngoc Trai/Hai Au vi nguon crawl khong co san).
const SAO_BIEN_LOCATION_TABS = [
  { label: "Vị trí Tiểu khu Sao Biển", src: "http://localhost:9000/project-images/sao-bien/vinhomes-ocean-park-sao-bien.jpg" },
  { label: "Phối cảnh Sao Biển", src: "http://localhost:9000/project-images/sao-bien/phoi-canh-sao-bien-vinhomes-ocean-park.jpg" },
];

// Dien tich/so tang cac loai biet thu Sao Bien — lay dung tu pricing trong
// sao_bien.json, khong bia them so lieu.
const SAO_BIEN_UNIT_TYPES = [
  { label: "Biệt thự đơn lập", size: "148,5 – 368,6m²", storeys: "3 tầng nổi và 1 tum" },
  { label: "Biệt thự song lập", size: "127,5 – 150m²", storeys: "3 tầng nổi và 1 tum" },
  { label: "Biệt thự liền kề", size: "71,3 – 151,9m²", storeys: "4 tầng nổi và 1 tum" },
  { label: "Nhà phố shophouse", size: "67,5 – 173m²", storeys: "4 tầng nổi và 1 tum" },
];

// Du lieu 4 day Shop thuong mai dich vu (SH09/SB11A/HA08/BH9B) — lay dung tu
// 4 file JSON crawl rieng (shop_thuong_mai_*.json), KHONG dung chung 1 mau vi
// moi day co dia chi/dien tich/tien ich rieng. Anh da kiem tra tung file thuc
// te truoc khi gan (vi-tri = ban do vi tri, mat-bang = so do phan lo, con lai
// la anh thuc te/phoi canh ngoai that — vai file ten "mat_b1/mat_b2" (HA08)
// tuong tu la anh thuc te du ten goi de gay nham).
interface ShopTmdvProject {
  projectId: string;
  code: string;
  fullName: string;
  subtitle: string;
  anchorId: string;
  overview: {
    totalUnits: number;
    storeys: string;
    landArea: string;
    constructionArea: string;
    floorArea: string;
    handover: string;
    ownership: string;
  };
  locationTabs: { label: string; src: string }[];
  exteriorTabs: { label: string; src: string }[];
  masterPlanTabs: { label: string; src: string }[];
  businessNote?: string;
}

const SHOP_TMDV_PROJECTS: ShopTmdvProject[] = [
  {
    projectId: "shop-thuong-mai-sh09",
    code: "SH09",
    fullName: "Shop thương mại dịch vụ San Hô 09 (SH09)",
    subtitle: "Kế cận Đại lộ 52m và Đường 30m",
    anchorId: "shop-sh09",
    overview: {
      totalUnits: 24,
      storeys: "4 tầng nổi + 1 tum",
      landArea: "81 – 165,5m²",
      constructionArea: "57,9 – 61,2m²",
      floorArea: "218,1m²",
      handover: "Nhận nhà ngay",
      ownership: "Sở hữu 50 năm, được làm sổ hồng ngay",
    },
    locationTabs: [
      { label: "Vị trí SH09", src: "http://localhost:9000/project-images/shop-thuong-mai-sh09/vi-tri-shop-thuong-mai-dich-vu-bien-ho-sh09-vinhomes-ocean-park.jpg" },
      { label: "Vị trí SH09 (2)", src: "http://localhost:9000/project-images/shop-thuong-mai-sh09/vi-tri-shop-thuong-mai-dich-vu-bien-ho-sh09-vinhomes-ocean-park-1.jpg" },
    ],
    exteriorTabs: [
      { label: "Ảnh thực tế", src: "http://localhost:9000/project-images/shop-thuong-mai-sh09/shop-tmdv-sh09.jpg" },
      { label: "Ảnh thực tế (2)", src: "http://localhost:9000/project-images/shop-thuong-mai-sh09/sanho_anh_thuc_te_1.jpg" },
      { label: "Ảnh thực tế (3)", src: "http://localhost:9000/project-images/shop-thuong-mai-sh09/sanho_anh_thuc_te_2.jpg" },
      { label: "Ảnh thực tế (4)", src: "http://localhost:9000/project-images/shop-thuong-mai-sh09/sanho_anh_thuc_te_3.jpg" },
      { label: "Ảnh thực tế (5)", src: "http://localhost:9000/project-images/shop-thuong-mai-sh09/sanho_anh_thuc_te_4.jpg" },
    ],
    masterPlanTabs: [
      { label: "Tổng mặt bằng SH09", src: "http://localhost:9000/project-images/shop-thuong-mai-sh09/mat-bang-shop-thuong-mai-dich-vu-bien-ho-sh09-vinhomes-ocean-park-2048x1152.jpg" },
    ],
    businessNote: "Được phép kinh doanh đa dạng ngành nghề: văn phòng, nhà hàng, cafe, cửa hàng và các dịch vụ khác. Vỉa hè rộng được phép sử dụng cho hoạt động kinh doanh.",
  },
  {
    projectId: "shop-thuong-mai-sb11a",
    code: "SB11A",
    fullName: "Shop thương mại dịch vụ Sao Biển 11A (SB11A)",
    subtitle: "Điểm giao đường Sao Biển (30m) và đường Sao Biển 11 (20m)",
    anchorId: "shop-sb11a",
    overview: {
      totalUnits: 34,
      storeys: "4 tầng nổi + 1 tum",
      landArea: "99 – 164,6m²",
      constructionArea: "59 – 69,5m²",
      floorArea: "209,6 – 243,2m²",
      handover: "Nhận nhà ngay",
      ownership: "Sở hữu 50 năm, làm ngay sổ hồng",
    },
    // Nguon crawl SB11A khong co anh "vi tri" rieng — dung anh tong quan/phoi
    // canh de thay the, khong bia anh vi tri khong co thuc.
    locationTabs: [
      { label: "Tổng quan Thương mại dịch vụ", src: "http://localhost:9000/project-images/shop-thuong-mai-sb11a/Tong-quan-Thuong-mai-dich-vu-Vinhomes-Ocean-Park.jpg" },
    ],
    exteriorTabs: [
      { label: "Ảnh thực tế", src: "http://localhost:9000/project-images/shop-thuong-mai-sb11a/shop-tmdv-sb11a-vinhomes-ocean-park.jpg" },
    ],
    masterPlanTabs: [
      { label: "Tổng mặt bằng SB11A", src: "http://localhost:9000/project-images/shop-thuong-mai-sb11a/Mat-bang-Thuong-mai-dich-vu-Sao-Bien-Vinhomes-Ocean-Park.jpg" },
    ],
    businessNote: "Các căn shop sở hữu thiết kế vuông vắn, mặt tiền rộng và cửa kính lớn, cùng phần không gian vỉa hè rất rộng được phép sử dụng cho việc kinh doanh.",
  },
  {
    projectId: "shop-thuong-mai-ha08",
    code: "HA08",
    fullName: "Shop thương mại dịch vụ Hải Âu 08 (HA08)",
    subtitle: "Trung tâm phân khu Hải Âu",
    anchorId: "shop-ha08",
    overview: {
      totalUnits: 44,
      storeys: "4 tầng nổi + 1 tum",
      landArea: "88 – 232,8m²",
      constructionArea: "53,1 – 56,6m²",
      floorArea: "194,1 – 206,9m²",
      handover: "Nhận nhà ngay (bàn giao thô)",
      ownership: "Sở hữu 50 năm, làm ngay sổ hồng",
    },
    locationTabs: [
      { label: "Vị trí HA08", src: "http://localhost:9000/project-images/shop-thuong-mai-ha08/vi-tri-shop-thuong-mai-dich-vu-bien-ho-ha08-vinhomes-ocean-park.jpg" },
      { label: "Vị trí HA08 (2)", src: "http://localhost:9000/project-images/shop-thuong-mai-ha08/vi-tri-shop-thuong-mai-dich-vu-bien-ho-ha08-vinhomes-ocean-park-1.jpg" },
    ],
    exteriorTabs: [
      { label: "Phối cảnh", src: "http://localhost:9000/project-images/shop-thuong-mai-ha08/shop-thuong-mai-dich-vu-hai-au-vinhomes-ocean-park.jpg" },
      { label: "Ảnh thực tế", src: "http://localhost:9000/project-images/shop-thuong-mai-ha08/shop-thuong-mai-dich-vu-ha08-vinhomes-ocean-park.jpg" },
      { label: "Ảnh thực tế (2)", src: "http://localhost:9000/project-images/shop-thuong-mai-ha08/mat_b1.jpg" },
      { label: "Ảnh thực tế (3)", src: "http://localhost:9000/project-images/shop-thuong-mai-ha08/mat_b2.jpg" },
    ],
    masterPlanTabs: [
      { label: "Tổng mặt bằng HA08", src: "http://localhost:9000/project-images/shop-thuong-mai-ha08/mat-bang-shop-thuong-mai-dich-vu-bien-ho-ha08-vinhomes-ocean-park-2048x1152.jpg" },
    ],
    businessNote: "Phân khu Hải Âu quy hoạch 100% shophouse — các căn liền kề và biệt thự đều được phép kinh doanh, tạo lợi thế đa dạng cho các cửa hàng dịch vụ.",
  },
  {
    projectId: "shop-thuong-mai-bh9b",
    code: "BH9B",
    fullName: "Shop thương mại dịch vụ Biển Hồ 9B (BH9B)",
    subtitle: "Mặt đường Đại Tây Dương rộng 40m",
    anchorId: "shop-bh9b",
    overview: {
      totalUnits: 19,
      storeys: "4 tầng nổi + 1 tum",
      landArea: "107,3 – 159,2m²",
      constructionArea: "66,3 – 91m²",
      floorArea: "201,4 – 364,8m²",
      handover: "Nhận nhà ngay",
      ownership: "Sở hữu 50 năm, làm ngay sổ hồng",
    },
    locationTabs: [
      { label: "Vị trí BH9B", src: "http://localhost:9000/project-images/shop-thuong-mai-bh9b/vi-tri-shop-thuong-mai-dich-vu-bien-ho-9b-vinhomes-ocean-park.jpg" },
      { label: "Vị trí BH9B (2)", src: "http://localhost:9000/project-images/shop-thuong-mai-bh9b/vi-tri-shop-thuong-mai-dich-vu-bien-ho-9b-vinhomes-ocean-park-1.jpg" },
    ],
    exteriorTabs: [
      { label: "Ảnh thực tế", src: "http://localhost:9000/project-images/shop-thuong-mai-bh9b/shop-thuong-mai-dich-vu-bien-ho-9b-vinhomes-ocean-park.jpg" },
    ],
    masterPlanTabs: [
      { label: "Tổng mặt bằng BH9B", src: "http://localhost:9000/project-images/shop-thuong-mai-bh9b/mat-bang-shop-thuong-mai-dich-vu-bh9b-vinhomes-ocean-park-2048x1152.jpg" },
    ],
  },
];

// Chinh sach ban hang chung — 7 dieu GIONG NHAU o ca 4 day shop (doi chieu tung
// file JSON, chi khac ten du an trong "content"), nen gop thanh 1 khoi chung
// thay vi lap lai 4 lan.
const SHOP_TMDV_SALES_POLICIES = [
  "Thanh toán sớm 100% giá trị hợp đồng: chiết khấu 7,5% giá bán",
  "Hỗ trợ vay 70% giá trị, lãi suất 0%, ân hạn nợ gốc và không phạt trả nợ trước hạn trong 36 tháng",
  "Sau thời gian hỗ trợ vay: đảm bảo lãi suất 9%/năm trong 2 năm tiếp theo",
  "Gói hoàn thiện trị giá 500 triệu đồng, trừ trực tiếp vào giá bán",
  "Tặng miễn phí phí dịch vụ 60 tháng",
  "Hỗ trợ tiền thuê tương đương chiết khấu 2% giá bán",
  "Voucher Vinmec trị giá 100 triệu đồng",
];

// Anh nen tu luot cho banner dau trang "Shophouse" — 1 anh thuc te dai dien
// cho moi day shop (SH09/SB11A/HA08/BH9B), da co san tu du lieu crawl.
const SHOPHOUSE_BANNER_SLIDES = [
  "http://localhost:9000/project-images/shop-thuong-mai-sh09/shop-tmdv-sh09.jpg",
  "http://localhost:9000/project-images/shop-thuong-mai-sb11a/shop-tmdv-sb11a-vinhomes-ocean-park.jpg",
  "http://localhost:9000/project-images/shop-thuong-mai-ha08/shop-thuong-mai-dich-vu-ha08-vinhomes-ocean-park.jpg",
  "http://localhost:9000/project-images/shop-thuong-mai-bh9b/shop-thuong-mai-dich-vu-bien-ho-9b-vinhomes-ocean-park.jpg",
];

// 2 banner tien ich anh (thay cho chip "Diem noi bat"/"Tien ich" mac dinh) —
// chi dung cho tab Chung cu, theo dung mau thiet ke nguoi dung gui. Anh THAT
// da co san tu du lieu crawl (Senique Hanoi + Zurich + London), khong bia.
interface AmenityPhoto {
  label: string;
  src: string;
}

function AmenityPhotoBanner({
  title,
  paragraphs,
  photos,
  fit = "cover",
}: {
  title: string;
  paragraphs: string[];
  photos: AmenityPhoto[];
  /** "contain" cho anh dang graphic/poster co chu o sat vien (vd bo anh Biet
   * thu) — "cover" (mac dinh) cat cho vua khung, hop voi anh chup thuc te. */
  fit?: "cover" | "contain";
}) {
  return (
    <section className="amenity-banner">
      <div className="amenity-banner-head">
        <h3 className="amenity-banner-title">{title}</h3>
        {paragraphs.map((p, i) => (
          <p key={i} className="amenity-banner-text">
            {p}
          </p>
        ))}
      </div>
      <div className="amenity-banner-grid">
        {photos.map((p) => (
          <div key={p.label} className={`amenity-banner-card ${fit === "contain" ? "amenity-banner-card--contain" : ""}`}>
            <img src={p.src} alt={p.label} />
            <p>{p.label}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

// Tien ich chung cua ca Khu do thi Ocean Park (giao duc, y te, giai tri) — anh
// that lay tu bo anh crawl The Senique Hanoi (du an co crawl day du nhat bo
// anh tien ich toan khu, dung chung cho moi phan khu Chung cu).
const DISTRICT_AMENITY_PHOTOS: AmenityPhoto[] = [
  { label: "Vincom Mega Mall", src: "http://localhost:9000/project-images/the-senique-hanoi/tttm-vincom-mega-mall-ocean-park.jpg" },
  { label: "Phòng khám Vinmec", src: "http://localhost:9000/project-images/the-senique-hanoi/vinmec-ocean-park.jpg" },
  { label: "Hồ Ngọc Trai", src: "http://localhost:9000/project-images/the-senique-hanoi/ho-ngoc-trai-vinhomes-ocean-park.jpg" },
  { label: "Biển nhân tạo Crystal Lagoon", src: "http://localhost:9000/project-images/the-senique-hanoi/bien-crystal-largoon.jpg" },
  { label: "Hệ thống giáo dục Vinschool", src: "http://localhost:9000/project-images/the-senique-hanoi/giao-duc-ocean-park.jpg" },
  { label: "Đại học VinUni", src: "http://localhost:9000/project-images/the-senique-hanoi/dai-hoc-vinuni.jpg" },
];

// Tien ich noi khu tieu bieu cac toa can ho (gym/yoga/be boi/khu vui choi tre
// em/phong sinh hoat cong dong/phong dance) — anh that tu Zurich + London,
// dai dien chung cho cac toa can ho trong tab Chung cu (khong gan rieng 1 du
// an cu the vi day la section o cap category).
const TOWER_AMENITY_PHOTOS: AmenityPhoto[] = [
  { label: "Phòng gym", src: "http://localhost:9000/project-images/the-zurich/phong-gym-the-zurich.jpg" },
  { label: "Phòng yoga", src: "http://localhost:9000/project-images/the-zurich/phong-yoga-the-zurich.jpg" },
  { label: "Bể bơi khoáng nóng", src: "http://localhost:9000/project-images/the-zurich/be-boi-thermal-bath-the-zurich.jpg" },
  { label: "Khu vui chơi trẻ em trong nhà", src: "http://localhost:9000/project-images/the-zurich/khu-vui-choi-trong-nha-tre-e-the-zurich.jpg" },
  { label: "Phòng sinh hoạt cộng đồng", src: "http://localhost:9000/project-images/the-zurich/phong-sinh-hoat-cong-dong-the-zurich.jpg" },
  { label: "Phòng dance / aerobic", src: "http://localhost:9000/project-images/the-london/phong-dance-phan-khu-the-london-vinhomes-ocean-park.jpg" },
];

// Tien ich & dich vu rieng cho tab Biet thu — dung anh tu bo anh crawl Tieu khu Ngoc Trai
// (cac anh nay phu hop hon vi la anh tien ich chung khu, khong bi trung voi Chung cu).
const BIET_THU_AMENITY_PHOTOS: AmenityPhoto[] = [
  { label: "Vincom Mega Mall", src: "http://localhost:9000/project-images/ngoc-trai/vincom-mega-mall-768x768.jpg" },
  { label: "Đại học VinUni", src: "http://localhost:9000/project-images/ngoc-trai/vinuni-768x768-1.jpg" },
  { label: "Hệ thống giáo dục Vinschool", src: "http://localhost:9000/project-images/ngoc-trai/vinschool-1-705x705.jpg" },
  { label: "Bệnh viện Vinmec", src: "http://localhost:9000/project-images/ngoc-trai/vinmec-768x768-1.jpg" },
  { label: "Vườn nướng BBQ", src: "http://localhost:9000/project-images/ngoc-trai/vuong-nuong-bbq-705x705.jpg" },
  { label: "Công viên & khu gym ngoài trời", src: "http://localhost:9000/project-images/ngoc-trai/cong-vien-gym-768x768-2-705x705.jpg" },
];

function CategoryBanner({ category }: { category: CategoryDetail }) {
  const bannerSlides =
    category.name === "Chung cư"
      ? CHUNG_CU_BANNER_SLIDES
      : category.name === "Biệt thự"
        ? BIET_THU_BANNER_SLIDES
        : category.name === "Shophouse"
          ? SHOPHOUSE_BANNER_SLIDES
          : null;
  const [active, setActive] = useState(0);

  useEffect(() => {
    if (!bannerSlides) return;
    const timer = setInterval(() => {
      setActive((i) => (i + 1) % bannerSlides.length);
    }, 4500);
    return () => clearInterval(timer);
  }, [bannerSlides]);

  const singleImage = bannerSlides ? null : category.coverImage ?? category.gallery[0] ?? null;

  return (
    <div className="detail-banner">
      {bannerSlides ? (
        <>
          {bannerSlides.map((src, i) => (
            <div
              key={src}
              className={`detail-banner-slide ${i === active ? "detail-banner-slide--active" : ""}`}
              style={{ backgroundImage: `url(${src})` }}
            />
          ))}
          <div className="detail-banner-dots">
            {bannerSlides.map((_, i) => (
              <button
                key={i}
                type="button"
                aria-label={`Ảnh ${i + 1}`}
                className={`detail-banner-dot ${i === active ? "detail-banner-dot--active" : ""}`}
                onClick={() => setActive(i)}
              />
            ))}
          </div>
        </>
      ) : (
        singleImage && (
          <div
            className="detail-banner-slide detail-banner-slide--active"
            style={{ backgroundImage: `url(${singleImage})` }}
          />
        )
      )}
      <div className="detail-banner-scrim" />

      <BuildingHomeIcon size={40} className="detail-banner-icon" />
      <div className="detail-banner-content">
        <h1 className="detail-banner-title">{category.name}</h1>
      </div>
    </div>
  );
}

export function CategoryDetailPage() {
  const { categorySlug } = useParams();
  const location = useLocation();
  const [category, setCategory] = useState<CategoryDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [projects, setProjects] = useState<ProjectListItem[]>([]);

  useEffect(() => {
    if (!categorySlug) return;
    setLoading(true);
    fetchCategoryDetail(categorySlug)
      .then(setCategory)
      .catch(() => setCategory(null))
      .finally(() => setLoading(false));
  }, [categorySlug]);

  // Cuon toi dung phan khu khi vao trang qua link co #hash (dropdown menu
  // TopNavbar) — thay vi mo trang rieng cho tung nhom nhu truoc. Cac khoi phia
  // tren (TowerSpotlight/PriceTable...) tu fetch API rieng va render dan dan
  // sau khi "category" da load xong, nen chi cuon 1 lan la khong du — trang
  // con gian chieu cao SAU do, day lech vi tri khu can toi (dac biet ro voi
  // Senique Hanoi vi no nam cuoi trang, sau rat nhieu khoi async khac). Cuon
  // lai vai lan trong ~1.6s de bu vao, huy neu nguoi dung tu cuon tay giua chung.
  useEffect(() => {
    if (loading || !location.hash) return;
    const id = location.hash.slice(1);
    let cancelled = false;

    const scrollToAnchor = () => {
      if (cancelled) return;
      document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
    };

    const cancel = () => {
      cancelled = true;
    };
    window.addEventListener("wheel", cancel, { once: true, passive: true });
    window.addEventListener("touchmove", cancel, { once: true, passive: true });

    const timers = [0, 150, 450, 900, 1600].map((delay) => window.setTimeout(scrollToAnchor, delay));

    return () => {
      cancelled = true;
      timers.forEach(window.clearTimeout);
      window.removeEventListener("wheel", cancel);
      window.removeEventListener("touchmove", cancel);
    };
  }, [loading, location.hash]);

  useEffect(() => {
    fetchAllProjects()
      .then(setProjects)
      .catch(() => setProjects([]));
  }, []);

  const projectsById = new Map(projects.map((p) => [p.id, p]));
  const catalogCategorySlug = categorySlug ? CATEGORY_SLUG_TO_CATALOG_SLUG[categorySlug] : undefined;
  const catalogCategory = CATALOG[0].categories.find((c) => c.slug === catalogCategorySlug);

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
          <Link to="/home" className="btn btn-primary" style={{ marginTop: 16 }}>
            Về trang chủ
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="page inv-page">
      <CategoryBanner category={category} />

      <Link to="/home" className="detail-back">
        <ArrowLeftIcon size={15} />
        Trang chủ
      </Link>

      <div className="inv-main">
          {category.name === "Chung cư" ? (
            <section className="section-block intro-grid">
              <div className="intro-text">
                <h3 className="intro-title">
                  <span className="intro-title-bar" />
                  {category.name} Vinhomes Ocean Park
                </h3>
                <p className="page-sub" style={{ maxWidth: "none" }}>
                  {category.description}
                </p>
              </div>
              <IntroCarousel images={CHUNG_CU_INTRO_IMAGES} />
            </section>
          ) : (
            <section className="section-block">
              <h3 className="section-title">Giới thiệu</h3>
              <p className="page-sub" style={{ maxWidth: "none" }}>
                {category.description}
              </p>
            </section>
          )}

          {category.name === "Chung cư" && category.types.length > 0 && (
            <section className="pricing-hero">
              <div className="pricing-hero-bg" style={{ backgroundImage: `url(${CHUNG_CU_BANNER_IMAGE})` }} />
              <div className="pricing-card">
                <h3 className="pricing-card-title">Diện tích và giá bán</h3>
                <div className="pricing-table">
                  {category.types.map((t) => (
                    <div key={t.type} className="pricing-table-row">
                      <span className="pricing-table-name">{t.type}</span>
                      <span className="pricing-table-size">{t.sizeRange}</span>
                      <span className="pricing-table-price">{t.priceRange}</span>
                    </div>
                  ))}
                </div>
              </div>
            </section>
          )}

          {category.name === "Chung cư" && (
            <>
              <LocationMap />
              <div id="lumiere-orient-pearl" className="anchor-section">
                <LumiereOrientPearlSpotlight />
                <PriceTable projectId="the-palma" />
                <FloorPlanTabs title="Mặt bằng The Palma" tabs={PALMA_FLOOR_PLANS} />
              </div>
              <div id="the-metropolitan" className="anchor-section">
                <MetropolitanSpotlight />
                <MetropolitanLocationMap />
                <div id="the-zurich" className="anchor-section">
                  <TowerSpotlight projectId="the-zurich" image="/3d-the-zurich-vinhomes-ocean-park.jpg" />
                  <PriceTable projectId="the-zurich" />
                  <ZurichLayoutGallery />
                </div>
                <div id="the-beverly" className="anchor-section">
                  <MetropolitanLocationMap locations={BEVERLY_LOCATION} />
                  <TowerSpotlight
                    projectId="the-beverly"
                    image="http://localhost:9000/project-images/the-beverly/quang-truong-the-beverly.jpg"
                  />
                  <PriceTable projectId="the-beverly" />
                  <FloorPlanTabs title="Mặt bằng The Beverly" tabs={BEVERLY_FLOOR_PLANS} />
                </div>
                <div id="the-london" className="anchor-section">
                  <section className="section-block">
                    <div className="location-map-wrap">
                      <img
                        src="http://localhost:9000/project-images/the-london/phan-khu-the-london-rumor.jpg"
                        alt="Phân khu The London"
                        className="location-map-img"
                      />
                    </div>
                  </section>
                  <TowerSpotlight
                    projectId="the-london"
                    image="http://localhost:9000/project-images/the-london/sanh-le-tan-phan-khu-london-vinhomes-ocean-park-710x375.jpg"
                  />
                  <PriceTable projectId="the-london" />
                  <FloorPlanTabs title="Mặt bằng The London" tabs={LONDON_FLOOR_PLANS} />
                </div>
                <div id="the-paris" className="anchor-section">
                  <ParisLocationMap />
                  <TowerSpotlight
                    projectId="the-paris"
                    image="http://localhost:9000/project-images/the-paris/phoi-canh-phan-khu-the-paris-ocean-park.jpg"
                  />
                  <PriceTable projectId="the-paris" />
                  <FloorPlanTabs title="Mặt bằng The Paris" tabs={PARIS_FLOOR_PLANS} />
                </div>
              </div>
              <div id="the-ocean-view" className="anchor-section">
                <OceanViewSpotlight />
                <section className="section-block">
                  <div className="location-map-wrap">
                    <img
                      src="http://localhost:9000/project-images/the-ocean-view/tong-mat-bang-the-ocean-view.jpg"
                      alt="Tổng mặt bằng The Ocean View"
                      className="location-map-img"
                    />
                  </div>
                </section>
                <div id="the-zenpark" className="anchor-section">
                  <TowerSpotlight
                    projectId="the-zenpark"
                    image="http://localhost:9000/project-images/the-zenpark/can-ho-the-zenpark.jpg"
                  />
                  <PriceTable projectId="the-zenpark" />
                  <ZenparkLayoutGallery />
                </div>
                <div id="the-pavilion" className="anchor-section">
                  <TowerSpotlight
                    projectId="the-pavilion"
                    image="http://localhost:9000/project-images/the-pavilion/phoi-canh-the-pavilion-vinhomes-ocean-park.jpg"
                  />
                  <PriceTable projectId="the-pavilion" />
                  <PavilionLayoutGallery />
                </div>
              </div>
              <div id="the-sapphire" className="anchor-section">
                <SapphireSpotlight />
                <PriceTable projectId="the-sapphire" />
                <FloorPlanTabs title="Mặt bằng The Sapphire" tabs={SAPPHIRE_FLOOR_PLANS} />
              </div>
              <div id="the-senique-hanoi" className="anchor-section">
                <SeniqueSpotlight />
                <PriceTable projectId="the-senique-hanoi" />
                <SeniqueLayoutGallery />
                <div id="the-senique-1" className="anchor-section section-block">
                  <h3 className="intro-title">
                    <span className="intro-title-bar" />
                    Tòa The Senique 1
                  </h3>
                  <FloorPlanTabs title="Mặt bằng theo tầng" tabs={SENIQUE_1_FLOOR_PLANS} />
                </div>
                <div id="the-senique-2" className="anchor-section section-block">
                  <h3 className="intro-title">
                    <span className="intro-title-bar" />
                    Tòa The Senique 2
                  </h3>
                  <FloorPlanTabs title="Mặt bằng theo tầng" tabs={SENIQUE_2_FLOOR_PLANS} />
                </div>
                <div className="section-block">
                  <h3 className="intro-title">
                    <span className="intro-title-bar" />
                    Tòa The Senique Premier
                  </h3>
                  <FloorPlanTabs title="Mặt bằng theo tầng" tabs={SENIQUE_PREMIER_FLOOR_PLANS} />
                </div>
              </div>
            </>
          )}

          {category.name === "Biệt thự" && (
            <>
              <VillaOverviewIntro />
              <VillaLocationMap />
              <div className="section-divider">
                <span>Thiết kế các loại biệt thự</span>
              </div>
              <div id="tieu-khu-ngoc-trai" className="anchor-section">
                <ZoneHeaderBanner
                  title="Tiểu khu Ngọc Trai"
                  subtitle="Vị trí trung tâm - 'trái tim' của Vinhomes Ocean Park"
                />
                <TowerSpotlight
                  projectId="ngoc-trai"
                  image="http://localhost:9000/project-images/ngoc-trai/vinhomes-ocean-park-ngoc-trai.jpg"
                  oval={false}
                  hideImage
                />
                <FloorPlanTabs title="Vị trí & Phối cảnh Ngọc Trai" tabs={NGOC_TRAI_LOCATION_TABS} compact />
                <p className="page-sub" style={{ maxWidth: "none", marginTop: 16 }}>
                  <em>
                    Lưu ý: Vinhomes Ocean Park là dự án có quy mô lớn, chính vì vậy các hình ảnh và bản vẽ về Mặt
                    bằng chia lô chi tiết có độ phân giải và dung lượng file rất lớn. Vì vậy, quý khách hàng muốn
                    nhận File Mặt bằng chia lô xin vui lòng đăng ký địa chỉ email, chúng tôi sẽ gửi tới quý khách
                    hàng sớm nhất.
                  </em>
                </p>
                <section className="section-block zone-spotlight-media-solo">
                  <img
                    src="http://localhost:9000/project-images/ngoc-trai/tien-ich-ngoc-trai.jpg"
                    alt="Tiện ích Tiểu khu Ngọc Trai"
                  />
                </section>
                <div className="intro-text" style={{ marginBottom: 20 }}>
                  <p className="page-sub" style={{ maxWidth: "none" }}>
                    <strong>Tiểu khu Ngọc Trai</strong> bao gồm các loại biệt thự đơn lập, biệt thự song lập, biệt
                    thự liền kề và nhà phố thương mại shophouse. Dãy phố kinh doanh shophouse được bố trí tại mặt
                    trục đường chính rộng 52m của cả dự án Vinhomes Ocean Park, trong khi các loại hình đơn lập, song
                    lập và liền kề nằm các vị trí riêng tư bên trong.
                  </p>
                  <ul className="zone-spotlight-list">
                    {NGOC_TRAI_UNIT_TYPES.map((u) => (
                      <li key={u.label}>
                        <strong>{u.label}:</strong> diện tích {u.size}; xây dựng {u.storeys}.
                      </li>
                    ))}
                  </ul>
                </div>
                <FloorPlanTabs title="Thiết kế các loại biệt thự khu Ngọc Trai" tabs={NGOC_TRAI_UNIT_PHOTOS} />
                <FloorPlanTabs title="Thiết kế mặt bằng các loại biệt thự khu Ngọc Trai" tabs={NGOC_TRAI_FLOOR_PLANS} />
              </div>
              <div id="tieu-khu-hai-au" className="anchor-section">
                <ZoneHeaderBanner title="Tiểu khu Hải Âu" subtitle="Thiết kế theo hình cánh chim Hải Âu" />
                <TowerSpotlight
                  projectId="hai-au"
                  image="http://localhost:9000/project-images/hai-au/vinhomes-ocean-park-hai-au.jpg"
                  oval={false}
                  hideImage
                />
                <FloorPlanTabs title="Vị trí & Phối cảnh Hải Âu" tabs={HAI_AU_LOCATION_TABS} compact />
                <p className="page-sub" style={{ maxWidth: "none", marginTop: 16 }}>
                  <em>
                    Lưu ý: Vinhomes Ocean Park là dự án có quy mô lớn, chính vì vậy các hình ảnh và bản vẽ về Mặt
                    bằng chia lô chi tiết có độ phân giải và dung lượng file rất lớn. Vì vậy, quý khách hàng muốn
                    nhận File Mặt bằng chia lô xin vui lòng đăng ký địa chỉ email, chúng tôi sẽ gửi tới quý khách
                    hàng sớm nhất.
                  </em>
                </p>
                <section className="section-block zone-spotlight-media-solo">
                  <img
                    src="http://localhost:9000/project-images/hai-au/ho-dieu-hoa-bien-ho-1500x600.jpg"
                    alt="Cảnh quan Hồ điều hòa & Biển hồ Hải Âu"
                  />
                </section>
                <div className="intro-text" style={{ marginBottom: 20 }}>
                  <p className="page-sub" style={{ maxWidth: "none" }}>
                    <strong>Tiểu khu Hải Âu</strong> bao gồm các loại biệt thự thương mại đơn lập, song lập và liền
                    kề, được thiết kế theo hình cánh chim Hải Âu, sở hữu tầm nhìn ra hồ điều hòa và biển hồ nước mặn.
                  </p>
                  <ul className="zone-spotlight-list">
                    {HAI_AU_UNIT_TYPES.map((u) => (
                      <li key={u.label}>
                        <strong>{u.label}:</strong> diện tích {u.size}; xây dựng {u.storeys}.
                      </li>
                    ))}
                  </ul>
                </div>
                <FloorPlanTabs title="Thiết kế các loại biệt thự khu Hải Âu" tabs={HAI_AU_UNIT_PHOTOS} />
                <FloorPlanTabs title="Thiết kế mặt bằng các loại biệt thự khu Hải Âu" tabs={HAI_AU_FLOOR_PLANS} />
              </div>
              <div id="tieu-khu-sao-bien" className="anchor-section">
                <ZoneHeaderBanner title="Tiểu khu Sao Biển" subtitle="Ôm trọn hồ điều hòa trung tâm 25ha" />
                <TowerSpotlight
                  projectId="sao-bien"
                  image="http://localhost:9000/project-images/sao-bien/phoi-canh-sao-bien-vinhomes-ocean-park.jpg"
                  oval={false}
                  hideImage
                />
                <FloorPlanTabs title="Vị trí & Phối cảnh Sao Biển" tabs={SAO_BIEN_LOCATION_TABS} compact />
                <div className="intro-text" style={{ marginBottom: 20 }}>
                  <p className="page-sub" style={{ maxWidth: "none" }}>
                    <strong>Tiểu khu Sao Biển</strong> bao gồm các loại biệt thự đơn lập, biệt thự song lập, biệt
                    thự liền kề và nhà phố shophouse, ôm trọn hồ điều hòa trung tâm 25ha và biển hồ nước mặn 6,1ha
                    của Vinhomes Ocean Park.
                  </p>
                  <ul className="zone-spotlight-list">
                    {SAO_BIEN_UNIT_TYPES.map((u) => (
                      <li key={u.label}>
                        <strong>{u.label}:</strong> diện tích {u.size}; xây dựng {u.storeys}.
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
              <AmenityPhotoBanner
                title="Hệ thống Tiện ích & Dịch vụ"
                paragraphs={[
                  "Khu biệt thự Vinhomes Ocean Park sở hữu hệ sinh thái tiện ích và dịch vụ mang thương hiệu Vinhomes vô cùng đa dạng và đẳng cấp — từ giáo dục, chăm sóc sức khỏe đến vui chơi, giải trí và thể dục thể thao.",
                ]}
                photos={BIET_THU_AMENITY_PHOTOS}
                fit="contain"
              />
            </>
          )}

          {category.name === "Shophouse" && (
            <>
              <section className="section-block intro-grid">
                <div className="intro-text">
                  <h3 className="intro-title">
                    <span className="intro-title-bar" />
                    Shop thương mại dịch vụ Vinhomes Ocean Park
                  </h3>
                  <p className="page-sub" style={{ maxWidth: "none" }}>
                    Hệ thống Shop thương mại dịch vụ (Shop TMDV) gồm 4 dãy — San Hô 09 (SH09), Sao Biển 11A (SB11A),
                    Hải Âu 08 (HA08) và Biển Hồ 9B (BH9B) — với tổng cộng{" "}
                    <strong>{SHOP_TMDV_PROJECTS.reduce((sum, p) => sum + p.overview.totalUnits, 0)} căn</strong>,
                    đồng bộ 4 tầng nổi + 1 tum, mặt tiền rộng và cửa kính lớn, nằm rải khắp các phân khu để phục vụ
                    lượng lớn cư dân hiện hữu của Vinhomes Ocean Park.
                  </p>
                  <ul className="zone-spotlight-list">
                    {SHOP_TMDV_PROJECTS.map((p) => (
                      <li key={p.code}>
                        <strong>{p.code}:</strong> {p.overview.totalUnits} căn, diện tích đất {p.overview.landArea}.
                      </li>
                    ))}
                  </ul>
                  <p className="page-sub" style={{ maxWidth: "none", marginBottom: 4 }}>
                    <strong>Chính sách bán hàng chung (áp dụng cả 4 dãy):</strong>
                  </p>
                  <ul className="zone-spotlight-list">
                    {SHOP_TMDV_SALES_POLICIES.map((s) => (
                      <li key={s}>{s}</li>
                    ))}
                  </ul>
                </div>
                <IntroCarousel images={SHOPHOUSE_BANNER_SLIDES} />
              </section>

              {SHOP_TMDV_PROJECTS.map((p) => (
                <div key={p.projectId} id={p.anchorId} className="anchor-section">
                  <ZoneHeaderBanner title={p.fullName} subtitle={p.subtitle} />
                  <TowerSpotlight projectId={p.projectId} image={p.exteriorTabs[0].src} oval={false} hideImage />
                  <FloorPlanTabs title={`Vị trí ${p.code}`} tabs={p.locationTabs} compact />
                  <div className="intro-text" style={{ marginBottom: 20 }}>
                    <ul className="zone-spotlight-list">
                      <li>
                        <strong>Tổng số căn:</strong> {p.overview.totalUnits} căn
                      </li>
                      <li>
                        <strong>Số tầng:</strong> {p.overview.storeys}
                      </li>
                      <li>
                        <strong>Diện tích đất:</strong> {p.overview.landArea}
                      </li>
                      <li>
                        <strong>Diện tích xây dựng:</strong> {p.overview.constructionArea}
                      </li>
                      <li>
                        <strong>Tổng diện tích sàn:</strong> {p.overview.floorArea}
                      </li>
                      <li>
                        <strong>Sở hữu:</strong> {p.overview.ownership}
                      </li>
                      <li>
                        <strong>Bàn giao:</strong> {p.overview.handover}
                      </li>
                    </ul>
                    {p.businessNote && (
                      <p className="page-sub" style={{ maxWidth: "none" }}>
                        <em>{p.businessNote}</em>
                      </p>
                    )}
                  </div>
                  <FloorPlanTabs title={`Ảnh thực tế & Phối cảnh ${p.code}`} tabs={p.exteriorTabs} />
                  <FloorPlanTabs title={`Tổng mặt bằng ${p.code}`} tabs={p.masterPlanTabs} compact />
                </div>
              ))}
            </>
          )}

          {catalogCategory &&
            catalogCategory.groups.length > 0 &&
            category.name !== "Chung cư" &&
            category.name !== "Biệt thự" &&
            category.name !== "Shophouse" && (
            <section className="section-block">
              <h3 className="section-title">Các phân khu ({catalogCategory.groups.length})</h3>
              <p className="page-sub" style={{ maxWidth: "none", marginTop: -6, marginBottom: 14 }}>
                Xem chi tiết từng phân khu/dự án con thuộc {category.name.toLowerCase()}.
              </p>
              <div className="inv-grid">
                {catalogCategory.groups.map((g) => (
                  <GroupCard key={g.slug} group={g} projectsById={projectsById} />
                ))}
              </div>
            </section>
          )}

          {category.name === "Chung cư" ? (
            <>
              <AmenityPhotoBanner
                title="Hệ tiện ích đẳng cấp sẵn có của Khu đô thị Ocean Park"
                paragraphs={[
                  "Mọi phân khu căn hộ tại Vinhomes Ocean Park đều thừa hưởng trọn vẹn hệ sinh thái tiện ích sẵn có của Đại đô thị — từ giáo dục, chăm sóc sức khỏe đến vui chơi, giải trí và thể dục thể thao.",
                ]}
                photos={DISTRICT_AMENITY_PHOTOS}
              />
              <AmenityPhotoBanner
                title="Tiện ích nội khu tiêu biểu"
                paragraphs={[
                  "Bên cạnh hệ tiện ích toàn khu đô thị, mỗi tòa căn hộ còn có tầng tiện ích riêng phục vụ cư dân: phòng gym, yoga, bể bơi, khu vui chơi trẻ em, phòng sinh hoạt cộng đồng...",
                ]}
                photos={TOWER_AMENITY_PHOTOS}
              />
            </>
          ) : category.name === "Biệt thự" || category.name === "Shophouse" ? null : (
            <>
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
            </>
          )}
      </div>
    </div>
  );
}
