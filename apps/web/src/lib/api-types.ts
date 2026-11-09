export type SourceFormat = "pdf" | "docx" | "tex" | "zip" | "txt";
export type Severity = "info" | "warning" | "error";
export type ScoreKey =
  | "keyword_match"
  | "semantic_relevance"
  | "experience_fit"
  | "parseability"
  | "impact"
  | "education"
  | "readability";

export interface SourceRef {
  kind: "latex_line" | "pdf_bbox" | "text_offset" | "unknown";
  line?: number | null;
  page?: number | null;
  bbox?: number[] | null;
  start?: number | null;
  end?: number | null;
  quote?: string | null;
  confidence?: number;
}

export interface ParseIssue {
  code: string;
  severity: Severity;
  message: string;
  source_ref?: SourceRef | null;
  auto_fixable: boolean;
}

export interface ResumeBasics {
  name?: string | null;
  label?: string | null;
  email?: string | null;
  phone?: string | null;
  url?: string | null;
  summary?: string | null;
}

export interface WorkItem {
  name?: string | null;
  position?: string | null;
  startDate?: string | null;
  endDate?: string | null;
  summary?: string | null;
  highlights: string[];
}

export interface EducationItem {
  institution?: string | null;
  area?: string | null;
  studyType?: string | null;
  score?: string | null;
}

export interface SkillGroup {
  name?: string | null;
  keywords: string[];
}

export interface Resume {
  basics: ResumeBasics;
  work: WorkItem[];
  education: EducationItem[];
  skills: SkillGroup[];
  projects: Array<{ name?: string | null; highlights: string[] }>;
  certifications: Array<{ name?: string | null; issuer?: string | null }>;
}

export interface ResumeDocument {
  format: SourceFormat;
  canonical: Resume;
  source_map: Record<string, SourceRef>;
  issues: ParseIssue[];
  raw_text?: string | null;
  structuring: {
    method: "heuristic" | "llm";
    confidence: number;
    model: string;
    prompt_version: string;
  };
}

export interface ResumeRead {
  id: string;
  filename: string;
  source_format: SourceFormat;
  document: ResumeDocument;
  created_at: string;
}

export type Importance = "must" | "nice";

export interface SkillRequirement {
  skill: string;
  canonical: string;
  importance: Importance;
  weight: number;
  category: string;
}

export interface KnockoutCriterion {
  kind:
    | "clearance"
    | "work_authorization"
    | "degree"
    | "location"
    | "experience"
    | "certification"
    | "other";
  text: string;
  hard: boolean;
}

export interface JDAnalysis {
  title?: string | null;
  company?: string | null;
  seniority?: string | null;
  years_min?: number | null;
  years_max?: number | null;
  must_have: SkillRequirement[];
  nice_to_have: SkillRequirement[];
  responsibilities: string[];
  keywords: string[];
  domain_terms: string[];
  knockouts: KnockoutCriterion[];
  analyser_version: string;
  analyzed_at: string;
}

export interface JDAnalysisResponse {
  id: string;
  analysis: JDAnalysis;
  warnings: string[];
  created_at: string;
}

export interface ComponentScore {
  score: number;
  weight: number;
  [key: string]: unknown;
}

export type ScoreBreakdown = Record<ScoreKey, ComponentScore>;

export interface CapApplied {
  code: string;
  reason: string;
  cap: number;
}

export interface PenaltyApplied {
  code: string;
  reason: string;
  points: number;
}

export interface Recommendation {
  priority: "high" | "medium" | "low";
  type: string;
  text: string;
  evidence: string[];
  component?: ScoreKey | null;
}

export interface ParseFidelity {
  score: number;
  field_recall: number;
  missing_fields: string[];
  issues: string[];
}

export interface ScoreReport {
  id?: string | null;
  resume_id: string;
  jd_id: string;
  overall_score: number;
  raw_score: number;
  grade: string;
  breakdown: ScoreBreakdown;
  knockouts: string[];
  caps: CapApplied[];
  penalties: PenaltyApplied[];
  recommendations: Recommendation[];
  parse_fidelity: ParseFidelity;
  weights: Record<string, number>;
  model_versions: Record<string, string>;
  scoring_version: string;
  created_at: string;
}

export type ChangeKind =
  | "rewrite_bullet"
  | "reorder_skills"
  | "reorder_bullets"
  | "condense_bullets"
  | "placeholder_metric"
  | "missing_skill_question"
  | "parse_fix"
  | "summary_tailor";

export type ChangeStatus = "pending" | "accepted" | "rejected";
export type Truthfulness = "verified" | "needs_user_input" | "rejected";

export interface ChangeProposal {
  id: string;
  kind: ChangeKind;
  section: string;
  target_ref?: string | null;
  original: string;
  proposed: string;
  rationale: string;
  evidence_spans: string[];
  jd_keywords_used: string[];
  risk: "low" | "medium" | "high";
  status: ChangeStatus;
  truthfulness: Truthfulness;
  edited_by_user?: boolean;
  verification_notes?: string[];
}

export interface VerifierSummary {
  checked: number;
  rejected: number;
  needs_user_input: number;
  reasons: string[];
}

export interface IterationRecord {
  iteration: number;
  baseline_score: number;
  candidate_score: number;
  score_delta: number;
  compile_status: string;
  parse_fidelity_before: Record<string, unknown>;
  parse_fidelity_after: Record<string, unknown>;
  rolled_back: boolean;
  reason?: string | null;
}

export interface OptimiseResult {
  job_id: string;
  resume_id: string;
  jd_id: string;
  baseline_score: number;
  target_score: number;
  score_after_accepted: number;
  estimated_pages_before: number;
  estimated_pages_after: number;
  iterations: number;
  stopped_reason:
    | "target_reached"
    | "no_further_gains"
    | "max_iterations"
    | "failed";
  proposals: ChangeProposal[];
  verifier: VerifierSummary;
  notes: string[];
  iteration_history: IterationRecord[];
  model_versions: Record<string, string>;
  created_at: string;
}

export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface JobRead {
  id: string;
  type: "optimise" | "score" | "ingest";
  status: JobStatus;
  progress: number;
  message?: string | null;
  result?: OptimiseResult | null;
  error?: { code?: string; message?: string } | null;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
}

export interface JobEventPayload {
  job_id: string;
  status: JobStatus;
  progress: number;
  message?: string | null;
  error?: { code?: string; message?: string } | null;
  result?: OptimiseResult | null;
  at: string;
}

export interface ChangeDecisionResponse {
  job_id: string;
  change: ChangeProposal;
  score_after_accepted: number;
  version_id?: string | null;
  score_id?: string | null;
  snapshot_url?: string | null;
  pdf_url?: string | null;
  previous_status?: ChangeStatus | null;
  idempotent_replay?: boolean;
}

export interface ResumeVersionRead {
  id: string;
  resume_id: string;
  version: number;
  parent_version_id?: string | null;
  tex_url?: string | null;
  pdf_url?: string | null;
  snapshot_url?: string | null;
  change_log: Array<Record<string, unknown>>;
  score_id?: string | null;
  created_at: string;
}

export interface ResumeVersionDetail extends ResumeVersionRead {
  document: ResumeDocument;
}

export interface FieldDiff {
  path: string;
  change: "added" | "removed" | "changed";
  before?: string | null;
  after?: string | null;
}

export interface VersionDiffResponse {
  version_id: string;
  against_version_id?: string | null;
  changed_fields: number;
  fields: FieldDiff[];
  note: string;
}

export interface Fact {
  id: string;
  fact_text: string;
  source: string;
  tags: string[];
  confirmed_at?: string | null;
  created_at?: string | null;
}

export interface FactsList {
  items: Fact[];
  total: number;
}

export interface DeleteAllResponse {
  deleted: PurgeResponse;
  audit_retained: boolean;
}

export interface PurgeResponse {
  resumes_deleted: number;
  versions_deleted: number;
  scores_deleted: number;
  jds_deleted: number;
  facts_deleted: number;
  jobs_deleted: number;
  audit_rows_deleted: number;
  storage_objects_deleted: number;
}
