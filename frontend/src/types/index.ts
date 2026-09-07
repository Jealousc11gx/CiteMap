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
  categories: string;
  source: "local" | "arxiv";
  arxiv_url?: string;
  pdf_path?: string;
  md_path?: string;
  note_edited_at?: string;
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
  paper_id?: string;
  team_type?: "confirmed" | "inferred";
  confidence?: "low" | "medium" | "high";
  description?: string;
  representative_author?: string;
  latest_paper_date?: string;
  venue?: string;
  venue_year?: number;
}

export interface GraphPaperReference {
  id: string;
  title: string;
  date?: string;
  venue?: string;
  venue_year?: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  title?: string;
  relation_types?: Array<"author" | "institution" | "paper" | "produced" | "collaboration">;
  papers?: GraphPaperReference[];
  shared_authors?: string[];
  shared_institutions?: string[];
  weight?: number;
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
