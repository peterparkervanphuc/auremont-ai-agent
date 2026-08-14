// Mirrors backend/schemas/*.py — keep field names in sync with the Pydantic response models.

export type UserRole = "sale" | "admin";
export type DocumentVisibility = "internal" | "public";
export type MessageSender = "sale" | "agent";
export type DocumentReviewStatus = "pending" | "approved" | "rejected";
export type LegalStatus =
  | "unknown"
  | "not_yet_effective"
  | "effective"
  | "expired"
  | "repealed"
  | "replaced";
export type DocumentCategory =
  | "sales_policy"
  | "price_list"
  | "inventory_snapshot"
  | "subdivision_info"
  | "building_info"
  | "floor_plan"
  | "payment_schedule"
  | "promotion"
  | "legal_document"
  | "contract_template"
  | "internal_guide"
  | "other";

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

export interface AnswerImage {
  url: string;
  project_id: string;
  project_name: string;
}

export interface MessageResponse {
  id: number;
  session_id: number | null;
  sender: MessageSender;
  content: string;
  citations: Citation[] | null;
  images: AnswerImage[] | null;
  verifier_score: number | null;
  requires_hitl: boolean;
  created_at: string;
}

export interface ProjectResponse {
  id: string;
  name: string;
  location: string | null;
  description: string | null;
  created_at: string;
}

export interface ChatSessionResponse {
  id: number;
  sale_id: number;
  title: string | null;
  customer_name: string | null;
  // The project this session is about. The agent needs it to query real-time
  // inventory, so a session without one cannot answer stock questions.
  project_id: string | null;
  created_at: string;
}

export interface DocumentResponse {
  id: number;
  title: string;
  file_path: string | null;
  project_id: string | null;
  status: string;
  visibility: DocumentVisibility;
  category: DocumentCategory;
  subcategory: string | null;
  subdivision_names: string[] | null;
  building_codes: string[] | null;
  unit_types: string[] | null;
  applicable_area: string | null;
  document_summary: string | null;
  version_label: string | null;
  issued_date: string | null;
  effective_date: string | null;
  expiry_date: string | null;
  applicable_period: string | null;
  legal_document_type: string | null;
  legal_document_number: string | null;
  legal_issuer: string | null;
  legal_domain: string | null;
  legal_status: LegalStatus;
  review_status: DocumentReviewStatus;
  classification_confidence: number | null;
  classification_reason: string | null;
  classified_at: string | null;
  reviewed_by: number | null;
  reviewed_at: string | null;
  uploaded_by: number | null;
  uploaded_at: string | null;
  created_at: string;
}

export interface DocumentClassificationUpdate {
  category: DocumentCategory;
  subcategory: string | null;
  subdivision_names: string[] | null;
  building_codes: string[] | null;
  unit_types: string[] | null;
  applicable_area: string | null;
  document_summary: string | null;
  version_label: string | null;
  issued_date: string | null;
  effective_date: string | null;
  expiry_date: string | null;
  applicable_period: string | null;
  legal_document_type: string | null;
  legal_document_number: string | null;
  legal_issuer: string | null;
  legal_domain: string | null;
  legal_status: LegalStatus;
}

export type DocumentRelationType = "replaces" | "amends" | "repeals" | "updates" | "supersedes" | "guides" | "related_to";

export interface DocumentRelationResponse {
  id: number;
  source_document_id: number;
  target_document_id: number;
  relation_type: DocumentRelationType;
  scope_note: string | null;
  evidence: string | null;
  confidence: number | null;
  review_status: DocumentReviewStatus;
  reviewed_by: number | null;
  reviewed_at: string | null;
  created_at: string;
}
