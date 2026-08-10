import { api } from "./client";
import { PROJECT_ID, type CategoryDetail, type CategorySummary } from "../types/project";

interface ApiCategorySummary {
  slug: string;
  name: string;
  price_from: string;
  price_to: string;
  size_from: number | null;
  size_to: number | null;
  types_count: number;
  cover_image: string | null;
  type_names: string[];
}

interface ApiCategoryTypeRow {
  type: string;
  size_range: string;
  price_range: string;
  description: string | null;
  storeys: string | null;
}

interface ApiAmenity {
  id: string;
  name: string;
  category: string;
  description?: string | null;
}

interface ApiCategoryDetail {
  slug: string;
  name: string;
  description: string;
  cover_image: string | null;
  types: ApiCategoryTypeRow[];
  amenities: ApiAmenity[];
  highlights: string[];
  gallery: string[];
}

function toSummary(row: ApiCategorySummary): CategorySummary {
  return {
    slug: row.slug,
    name: row.name,
    priceFrom: row.price_from,
    priceTo: row.price_to,
    sizeFrom: row.size_from ?? undefined,
    sizeTo: row.size_to ?? undefined,
    typesCount: row.types_count,
    coverImage: row.cover_image ?? undefined,
    typeNames: row.type_names,
  };
}

function toDetail(row: ApiCategoryDetail): CategoryDetail {
  return {
    slug: row.slug,
    name: row.name,
    description: row.description,
    coverImage: row.cover_image ?? undefined,
    types: row.types.map((t) => ({
      type: t.type,
      sizeRange: t.size_range,
      priceRange: t.price_range,
      description: t.description ?? undefined,
      storeys: t.storeys ?? undefined,
    })),
    amenities: row.amenities.map((a) => a.name),
    highlights: row.highlights,
    gallery: row.gallery,
  };
}

export async function fetchCategories(): Promise<CategorySummary[]> {
  const rows = await api.get<ApiCategorySummary[]>(`/projects/${PROJECT_ID}/categories`);
  return rows.map(toSummary);
}

export async function fetchCategoryDetail(slug: string): Promise<CategoryDetail> {
  const row = await api.get<ApiCategoryDetail>(`/projects/${PROJECT_ID}/categories/${slug}`);
  return toDetail(row);
}

export interface ProjectOverview {
  name: string;
  description: string;
  highlights: string[];
  gallery: string[];
}

interface ApiProjectDetail {
  name: string;
  description: string | null;
  highlights: string[];
  gallery: string[];
}

export async function fetchProjectOverview(): Promise<ProjectOverview> {
  const row = await api.get<ApiProjectDetail>(`/projects/${PROJECT_ID}`);
  return {
    name: row.name,
    description: row.description ?? "",
    highlights: row.highlights,
    gallery: row.gallery,
  };
}
