// Mirrors backend/schemas/*.py — keep field names in sync with the Pydantic response models.

export type UserRole = "sale" | "admin";
export type DocumentVisibility = "internal" | "public";
export type MessageSender = "customer" | "sale" | "agent";

export interface UserResponse {
  id: number;
  username: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
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
  title: string | null;
  created_at: string;
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
