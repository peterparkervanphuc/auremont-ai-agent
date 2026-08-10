// Kiểu dữ liệu hiển thị cho trang Tra cứu — công cụ Sale nội bộ của MỘT đại đô thị (Vinhomes Ocean Park),
// duyệt theo loại hình sản phẩm (Chung cư/Biệt thự/Shophouse), không phải nhiều dự án khác nhau.

export const PROJECT_ID = "vinhomes-ocean-park";

export interface CategorySummary {
  slug: string;
  name: string;
  priceFrom: string;
  priceTo: string;
  sizeFrom?: number;
  sizeTo?: number;
  typesCount: number;
  coverImage?: string;
  typeNames: string[];
}

export interface CategoryTypeRow {
  type: string;
  sizeRange: string;
  priceRange: string;
  description?: string;
  storeys?: string;
}

export interface CategoryDetail {
  slug: string;
  name: string;
  description: string;
  coverImage?: string;
  types: CategoryTypeRow[];
  amenities: string[];
  highlights: string[];
  gallery: string[];
}

/** Phân khu/giai đoạn khác của đại đô thị — chưa có dữ liệu riêng, hiện dạng "sắp cập nhật". */
export interface UpcomingPhase {
  slug: string;
  name: string;
}

export const UPCOMING_PHASES: UpcomingPhase[] = [
  { slug: "ocean-park-2", name: "Ocean Park 2" },
  { slug: "ocean-park-3", name: "Ocean Park 3" },
];
