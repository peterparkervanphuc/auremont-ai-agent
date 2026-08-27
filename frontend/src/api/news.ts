import { api } from "./client";

export type NewsTopic =
  | "official_update"
  | "project_progress"
  | "infrastructure"
  | "market_potential"
  | "promotion";

export interface NewsArticle {
  id: number;
  canonicalUrl: string;
  sourceId: string;
  sourceName: string;
  title: string;
  summary: string | null;
  imageUrl: string | null;
  topic: NewsTopic;
  projectNames: string[];
  publishedAt: string | null;
  fetchedAt: string;
}

interface ApiNewsArticle {
  id: number;
  canonical_url: string;
  source_id: string;
  source_name: string;
  title: string;
  summary: string | null;
  image_url: string | null;
  topic: NewsTopic;
  project_names: string[];
  published_at: string | null;
  fetched_at: string;
}

interface ApiNewsList {
  items: ApiNewsArticle[];
  total: number;
  offset: number;
  limit: number;
}

export interface NewsPageResult {
  items: NewsArticle[];
  total: number;
}

function mapArticle(row: ApiNewsArticle): NewsArticle {
  return {
    id: row.id,
    canonicalUrl: row.canonical_url,
    sourceId: row.source_id,
    sourceName: row.source_name,
    title: row.title,
    summary: row.summary,
    imageUrl: row.image_url,
    topic: row.topic,
    projectNames: row.project_names,
    publishedAt: row.published_at,
    fetchedAt: row.fetched_at,
  };
}

export async function fetchNews(params: {
  offset?: number;
  limit?: number;
  topic?: NewsTopic;
  query?: string;
}): Promise<NewsPageResult> {
  const search = new URLSearchParams();
  search.set("offset", String(params.offset ?? 0));
  search.set("limit", String(params.limit ?? 12));
  if (params.topic) search.set("topic", params.topic);
  if (params.query?.trim()) search.set("q", params.query.trim());
  const response = await api.get<ApiNewsList>(`/news?${search.toString()}`);
  return { items: response.items.map(mapArticle), total: response.total };
}
