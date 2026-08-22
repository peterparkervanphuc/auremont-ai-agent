// Mirrors backend/schemas/*.py — keep field names in sync with the Pydantic response models.

export type UserRole = "sale" | "admin" | "customer";
export type DocumentVisibility = "internal" | "public";
export type MessageSender = "sale" | "agent" | "customer";
/** Drives AuremontAvatar.tsx — mirrors backend/core/enums.py::MessageEmotion. `null` on a
 * Sale/Customer's own message, or an older AGENT message from before this field existed. */
export type MessageEmotion = "happy" | "regretful" | "respectful";
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
  /**
   * Tells two same-named sources apart ("tr.5", "#37"); null when the title is already
   * unique. Deliberately separate from `title`, which must keep its ".pdf" ending for
   * withPageAnchor and the inline preview. Absent on messages stored before this existed.
   */
  qualifier?: string | null;
  page: number | null;
  /** PDF points from the page's top — see CitationList.tsx's withPageAnchor. */
  y_position: number | null;
}

export interface AnswerImage {
  url: string;
  project_id: string;
  project_name: string;
}

/** One recommended unit, rendered as its own card (with paging arrows between cards)
 * instead of as a bullet line in `content` — see backend/ai/prompts.py::PropertyListing.
 * `image_urls`/`amenities`/`project_id` are resolved server-side, never supplied by the
 * model, and default empty when the project/gallery could not be resolved (the card still
 * renders, with a placeholder instead of photos). */
export interface PropertyListing {
  project_name: string;
  unit_type: string;
  area_range: string;
  price_range: string;
  image_urls: string[];
  amenities: string[];
  project_id: string | null;
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
  /** Derived server-side from the audit trail; never sent by this client. */
  hitl_confirmed: boolean;
  emotion: MessageEmotion | null;
  /** Short reply options to tap instead of typing — only ever set on a customer-facing
   * AGENT message asking a discovery question with a natural short list of answers. */
  quick_replies: string[] | null;
  /** Recommended units rendered as their own cards — see PropertyListing above. */
  listings: PropertyListing[] | null;
  /** Follow-up questions the asker may want next, offered on both the Sale and customer
   * surfaces. Distinct from `quick_replies`: those answer a question the assistant just
   * asked, these start the asker's next one. */
  suggested_questions: string[] | null;
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

// ── Customer chat (public/anonymous flow) — mirrors backend/schemas/customer.py ──

export interface AnonymousSessionResponse {
  session_id: number;
  visitor_token: string;
}

/** Who is currently answering a customer-chat session — see backend/core/enums.py::SessionStatus. */
export type SessionStatus = "bot_handling" | "waiting_sale" | "sale_handling";

export interface CustomerChatSessionResponse {
  id: number;
  customer_id: number | null;
  title: string | null;
  project_id: string | null;
  status: SessionStatus;
  created_at: string;
}

export interface CustomerRegisterRequest {
  email: string;
  password: string;
  full_name?: string | null;
  session_id?: number | null;
  visitor_token?: string | null;
}

/** Which soft-paywall trigger intercepted this turn — null on a normally-answered turn.
 * "human_request" is an anonymous visitor asking for a live Sale — routed into the same
 * register/login gate as every other lead-qualification trigger, not a direct handoff. */
export type CustomerGate = "turn_limit" | "closing_intent" | "human_request";

export interface CustomerAskResponse extends MessageResponse {
  gate: CustomerGate | null;
  status: SessionStatus;
}

// ── Sale live inbox (AI -> Sale handoff) — mirrors backend/schemas/sale_live.py ──

export interface LiveInboxEntry {
  session_id: number;
  customer_label: string;
  last_message_preview: string;
  // When this session entered the waiting queue — not when the session itself was created.
  waiting_since: string | null;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: UserResponse;
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
