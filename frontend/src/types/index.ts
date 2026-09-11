export interface Paper {
  id: string;
  title: string;
  abstract: string;
  published_date: string;
  venue?: string;
  venue_year?: number;
  venue_evidence?: string;
  venue_checked_at?: string;
  venue_source?: "automatic" | "manual";
  citation_count?: number;
  reference_count?: number;
  citation_synced_at?: string;
  semantic_scholar_id?: string;
  categories: string;
  source: "local" | "arxiv";
  arxiv_url?: string;
  pdf_path?: string;
  md_path?: string;
  note_edited_at?: string;
  created_at?: string;
  tldr?: string;
  core_contribution?: string;
  primary_domain?: string;
  subfields?: string[];
  tags?: PaperTag[];
  authors?: string[];
  teams?: string[];
  projects?: Array<{ id: string; name: string }>;
}

export interface PaperTag {
  name: string;
  type: "task" | "method" | "model" | "dataset" | "modality" | "application";
}

export interface Project {
  id: string;
  name: string;
  description?: string;
  is_system: number;
  paper_count: number;
  created_at: string;
  updated_at: string;
}

export interface ArxivSearchResult {
  id: string;
  title: string;
  abstract: string;
  published_date: string;
  categories: string;
  arxiv_url: string;
  authors: string[];
}

export interface GraphNode {
  id: string;
  label?: string;
  title?: string;
  group?: string;
  degree?: number;
  weighted_degree?: number;
  published_date?: string;
  core_contribution?: string;
  categories?: string;
  arxiv_url?: string;
  source?: string;
  institution?: string;
  authors?: string[];
  institutions?: string[];
  members?: string[];
  papers?: GraphPaperReference[];
  paper_count?: number;
  citation_synced_paper_count?: number;
  paper_id?: string;
  team_type?: "confirmed" | "inferred";
  confidence?: "low" | "medium" | "high";
  description?: string;
  representative_author?: string;
  latest_paper_date?: string;
  venue?: string;
  venue_year?: number;
  citation_count?: number;
  reference_count?: number;
  citation_synced_at?: string;
  scholar_id?: string;
  is_seed?: boolean;
  external?: boolean;
  similarity_score?: number;
  citation_role?: "seed" | "reference" | "citing";
}

export interface GraphPaperReference {
  id: string;
  title: string;
  date?: string;
  venue?: string;
  venue_year?: number;
  citation_count?: number;
  reference_count?: number;
  citation_synced_at?: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  title?: string;
  relation_types?: Array<"author" | "institution" | "paper" | "produced" | "collaboration" | "citation" | "similarity">;
  papers?: GraphPaperReference[];
  shared_authors?: string[];
  shared_institutions?: string[];
  weight?: number;
  directed?: boolean;
  similarity?: number;
  shared_references?: number;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  papers?: Paper[];
  tool_calls?: Array<{
    tool: string;
    arguments?: Record<string, any>;
    result?: any;
    status?: "running" | "done";
  }>;
  created_at?: string;
}

export interface ChatSession {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  project_id?: string;
}

export interface NoteItem {
  paper_id: string;
  title: string;
  path?: string;
  updated_at: string;
  note_edited_at?: string;
  content?: string;
}

export interface RadarConfig {
  project_id: string;
  enabled: boolean;
  categories: string[];
  include_keywords: string[];
  exclude_keywords: string[];
  profile_override: string;
  anchor_paper_ids: string[];
  top_k: number;
  min_score: number;
  include_cross_list: boolean;
  send_empty: boolean;
  fetch_limit: number;
  debug: boolean;
  compute_mode: "cloud" | "local" | "hybrid";
  updated_at?: string | null;
}

export type RadarState = "unread" | "read" | "saved" | "dismissed";

export interface RadarMatch {
  id: string;
  project_id: string;
  candidate_id: string;
  arxiv_id: string;
  title: string;
  abstract: string;
  authors: string[];
  categories: string[];
  affiliations?: string[];
  corresponding_authors?: string[];
  published_date?: string | null;
  updated_date?: string | null;
  arxiv_url: string;
  pdf_url?: string | null;
  score: number;
  reason: string;
  state: RadarState;
  created_at: string;
  updated_at: string;
  tldr?: string | null;
  ai_summary?: string | null;
  title_zh?: string | null;
  abstract_zh?: string | null;
  core_contribution?: string | null;
  method?: string | null;
  result?: string | null;
  limitations?: string | null;
}

export type ExploreTriageStatus = "unreviewed" | "read" | "later" | "ignored" | "project";

export interface ExploreProfile {
  id: string;
  name: string;
  description: string;
  categories: string[];
  include_keywords: string[];
  exclude_keywords: string[];
  enabled: boolean;
  updated_at?: string;
}

export interface AppSettings {
  values: Record<string, string>;
  secrets: Record<string, boolean>;
}

export interface RadarConnection {
  remote_url: string;
  token_configured: boolean;
  updated_at?: string | null;
}

export interface ExploreSource {
  source: string;
  source_rank?: number | null;
  first_seen_at?: string;
  metadata?: Record<string, unknown>;
}

export interface ExploreCandidate {
  id: string;
  arxiv_id: string;
  title: string;
  abstract: string;
  authors: string[];
  categories: string[];
  published_date?: string | null;
  updated_date?: string | null;
  arxiv_url: string;
  pdf_url?: string | null;
  code_url?: string | null;
  code_meta?: Record<string, unknown>;
  topic?: string | null;
  topic_bucket?: string | null;
  heat_score: number;
  ranking_score: number;
  relevance_score?: number | null;
  topic_relevance_score?: number | null;
  practicality_score?: number | null;
  relevance_breakdown: Record<string, unknown>;
  judge_reason?: string | null;
  judge_reason_en?: string | null;
  gate_status: string;
  judge_status: string;
  summary_status: string;
  triage_status: ExploreTriageStatus;
  discovered_at?: string;
  sources: ExploreSource[];
  watched_author: boolean;
  title_zh?: string | null;
  abstract_zh?: string | null;
  summary_zh?: string | null;
  summary_en?: string | null;
  highlights_zh: string[];
  highlights_en: string[];
  related_methods_zh: Array<{ name: string; relation: string; arxiv_id?: string | null }>;
  related_methods_en: Array<{ name: string; relation: string; arxiv_id?: string | null }>;
}

export interface ExploreDigestBucket {
  id: string;
  title: string;
  cap: number;
  papers: ExploreCandidate[];
}

export interface ExploreDigest {
  profile_id: string;
  digest_date: string;
  period: string;
  summary: string;
  scanned_count: number;
  pending_count: number;
  judged_count: number;
  rejected_count: number;
  surviving_count: number;
  highlighted_count: number;
  watched_count: number;
  watched: ExploreCandidate[];
  buckets: ExploreDigestBucket[];
  topic_counts: Record<string, number>;
  source_counts: Record<string, number>;
  spotlight: ExploreCandidate[];
  generated_at: string;
}

export interface ExploreTrends {
  profile_id: string;
  days: number;
  series: Record<string, Record<string, number>>;
  topics: Record<string, number>;
}

export interface ExploreRollup {
  profile_id: string;
  period: string;
  start_date: string;
  end_date: string;
  require_complete: boolean;
  missing_days: string[];
  papers: ExploreCandidate[];
  buckets: Array<{ id: string; title: string; papers: ExploreCandidate[] }>;
  paper_count: number;
}

export interface VenueTrendRunSummary {
  id: string;
  venue: string;
  model: string;
  accepted_count: number;
  in_scope_count: number;
  created_at: string;
}

export interface VenueTrendRun extends VenueTrendRunSummary {
  groups: Record<string, Array<Record<string, unknown>>>;
  report: Record<string, unknown>;
}
