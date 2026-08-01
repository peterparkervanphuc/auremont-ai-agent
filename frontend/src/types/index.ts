// Mirrors backend/schemas/*.py — keep field names in sync with the Pydantic response models.

export type UserRole = "sale" | "admin";
export type DocumentVisibility = "internal" | "public";
export type SessionSource = "sale_initiated" | "live_chat";
export type MessageSender = "customer" | "sale" | "agent";
export type LiveChatStatus = "waiting" | "active" | "ended";
export type UnitStatus = "available" | "reserved" | "sold" | "locked";

export interface UserResponse {
  id: number;
  username: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface CustomerResponse {
  id: string;
  phone: string | null;
  email: string | null;
  full_name: string | null;
  is_verified: boolean;
  created_at: string;
}

export interface InventoryUnitImageResponse {
  id: number;
  image_path: string;
}

export interface InventoryUnitResponse {
  id: number;
  unit_code: string;
  project_id: string;
  building: string | null;
  floor: string | null;
  unit_type: string | null;
  area_sqm: number | null;
  price: number | null;
  status: UnitStatus;
  extra_attributes: Record<string, unknown> | null;
  is_public: boolean;
  has_images: boolean;
  images: InventoryUnitImageResponse[];
  created_at: string;
  updated_at: string;
}

export interface InventoryBulkUploadRow {
  unit_code: string;
  has_image: boolean;
  error: string | null;
}

export interface InventoryBulkUploadPreview {
  rows: InventoryBulkUploadRow[];
  total: number;
  missing_images: number;
}

export interface Citation {
  document_id: number;
  title: string;
  page: number | null;
}

export interface MessageResponse {
  id: number;
  session_id: number | null;
  sender: MessageSender;
  content: string;
  citations: Citation[] | null;
  verifier_score: number | null;
  requires_hitl: boolean;
  created_at: string;
}

export interface ChatSessionResponse {
  id: number;
  sale_id: number;
  customer_id: string | null;
  source: SessionSource;
  title: string | null;
  created_at: string;
}

export interface LiveChatRequestResponse {
  id: number;
  customer_id: string;
  sale_id: number | null;
  session_id: number | null;
  status: LiveChatStatus;
  created_at: string;
  accepted_at: string | null;
  ended_at: string | null;
}

export interface DocumentResponse {
  id: number;
  title: string;
  file_path: string | null;
  project_id: string | null;
  status: string;
  visibility: DocumentVisibility;
  created_at: string;
}
