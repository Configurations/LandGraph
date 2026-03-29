export interface UserResponse {
  id: string;
  email: string;
  display_name: string;
  role: 'admin' | 'member' | 'undefined';
  teams: string[];
  auth_type?: 'local' | 'google';
  culture?: string;
}

export interface LoginResponse {
  token: string;
  user: UserResponse;
}

export interface RegisterResponse {
  ok: boolean;
  id: string;
  message: string;
}

export interface GoogleClientIdResponse {
  enabled: boolean;
  client_id: string;
}

export interface TeamResponse {
  id: string;
  name: string;
  directory: string;
}

export interface MemberResponse {
  id: string;
  email: string;
  display_name: string;
  role: string;
  team_role: string;
  is_active: boolean;
  auth_type: string;
  last_login: string | null;
}

export interface QuestionResponse {
  id: string;
  thread_id: string;
  agent_id: string;
  team_id: string;
  request_type: 'approval' | 'question';
  prompt: string;
  context: Record<string, unknown> | null;
  status: 'pending' | 'answered' | 'timeout' | 'cancelled';
  response: string | null;
  reviewer: string | null;
  channel: string;
  created_at: string;
  answered_at: string | null;
  agent_avatar_url: string | null;
}

export interface QuestionStatsResponse {
  total: number;
  pending: number;
  answered: number;
  timeout: number;
  cancelled: number;
}

export interface QuestionListParams {
  status?: string;
  channel?: string;
  limit?: number;
  offset?: number;
}

export interface InviteMemberPayload {
  email: string;
  display_name: string;
  role: string;
}

export interface AnswerPayload {
  response: string;
  action: 'approve' | 'reject' | 'answer';
}

export interface WebSocketEvent {
  type: string;
  data: Record<string, unknown>;
  timestamp?: string;
}

/* ── Projects ── */

export interface CreateProjectPayload {
  name: string;
  slug: string;
  language: string;
  team_id: string;
  git_config?: GitTestPayload;
}

export interface ProjectResponse {
  id: string;
  name: string;
  slug: string;
  team_id: string;
  language: string;
  git_service: string;
  git_url: string;
  git_login: string;
  git_repo_name: string;
  git_connected: boolean;
  git_repo_exists: boolean;
  wizard_pending: boolean;
  status: string;
  color: string;
  created_at: string;
  updated_at: string;
}

export interface SlugCheckResponse {
  exists: boolean;
  path: string;
}

export interface GitTestPayload {
  service: string;
  url: string;
  login: string;
  token: string;
  repo_name: string;
}

export interface GitTestResponse {
  connected: boolean;
  repo_exists: boolean;
  message: string;
}

export interface GitStatusResponse {
  connected: boolean;
  repo_exists: boolean;
  branch?: string;
  last_commit?: string;
}

/* ── RAG / Documents ── */

export interface UploadResponse {
  filename: string;
  size: number;
  content_type: string;
  chunks_indexed: number;
  files_extracted: number;
}

export interface UploadedFile {
  name: string;
  size: number;
  content_type: string;
  type?: 'file' | 'directory';
  file_count?: number;
}

export interface RagSearchResult {
  content: string;
  score: number;
  source: string;
}

export type AnalysisStatus = 'not_started' | 'in_progress' | 'waiting_input' | 'completed' | 'failed';

export interface AnalysisStartResponse {
  task_id: string;
  agent_id: string;
  status: string;
}

export interface AnalysisStatusResponse {
  status: AnalysisStatus;
  task_id: string | null;
  has_pending_question: boolean;
  pending_request_id: string | null;
}

export interface AnalysisMessage {
  id: string;
  sender: 'agent' | 'user' | 'system';
  type: 'progress' | 'question' | 'reply' | 'artifact' | 'result' | 'system';
  content: string;
  request_id?: string;
  status?: string;
  artifact_key?: string;
  created_at: string;
}

export interface ConversationMessage {
  id: number;
  project_slug: string;
  task_id: string | null;
  sender: string;
  content: string;
  created_at: string;
}

/* ── Deliverables ── */

export type DeliverableStatus = 'pending' | 'approved' | 'rejected';

export interface DeliverableResponse {
  id: string;
  task_id: string;
  key: string;
  deliverable_type: string;
  file_path: string;
  git_branch: string;
  category: string;
  status: DeliverableStatus;
  reviewer: string | null;
  review_comment: string | null;
  reviewed_at: string | null;
  created_at: string;
  agent_id: string;
  phase: string;
  project_slug: string;
}

export interface DeliverableDetail extends DeliverableResponse {
  content: string;
  cost_usd: number;
}

export interface RemarkResponse {
  id: string;
  artifact_id: string;
  reviewer: string;
  comment: string;
  created_at: string;
}

export interface BranchInfo {
  name: string;
  ahead: number;
  behind: number;
  last_commit: string;
}

export interface BranchDiffFile {
  path: string;
  status: string;
  additions: number;
  deletions: number;
}

export interface DeliverableListParams {
  phase?: string;
  status?: string;
  agent_id?: string;
}

/* ── Chat ── */

export interface ChatMessage {
  id: string;
  team_id: string;
  agent_id: string;
  thread_id: string;
  sender: string;
  content: string;
  created_at: string;
}

/* ── Agents ── */

export interface AgentInfo {
  id: string;
  name: string;
  llm: string;
  type: string;
  pending_questions: number;
  avatar_url: string | null;
}

/* ── Dashboard ── */

export interface ActiveTask {
  task_id: string;
  agent_id: string;
  team_id: string;
  project_slug: string;
  phase: string;
  status: string;
  cost_usd: number;
  started_at: string;
}

export interface CostSummary {
  project_slug: string;
  team_id: string;
  phase: string;
  agent_id: string;
  total_cost_usd: number;
  task_count: number;
  avg_cost_per_task: number;
}

export interface OverviewData {
  pending_questions: number;
  active_tasks: number;
  total_cost: number;
}

/* ── Issues (PM) ── */

export type IssueStatus = 'backlog' | 'todo' | 'in-progress' | 'in-review' | 'done';
export type IssuePriority = 1 | 2 | 3 | 4;
export type IssueGroupBy = 'status' | 'team' | 'assignee' | 'dependency';

export interface IssueResponse {
  id: string;
  project_id: string;
  title: string;
  description: string;
  status: IssueStatus;
  priority: IssuePriority;
  assignee: string;
  team_id: string;
  tags: string[];
  phase: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  is_blocked: boolean;
  blocking_count: number;
  blocked_by_count: number;
}

export interface IssueDetail extends IssueResponse {
  relations: RelationResponse[];
  project_name: string;
}

export interface IssueCreatePayload {
  title: string;
  description?: string;
  priority?: IssuePriority;
  status?: IssueStatus;
  assignee?: string;
  tags?: string[];
  project_id?: string;
  phase?: string;
}

export type IssueUpdatePayload = Partial<IssueCreatePayload>;

export interface IssueListParams {
  team_id?: string;
  project_id?: string;
  status?: IssueStatus;
  assignee?: string;
}

/* ── Relations ── */

export type RelationType = 'blocks' | 'relates_to' | 'parent_of' | 'duplicates';

export interface RelationResponse {
  id: string;
  type: RelationType;
  direction: 'outgoing' | 'incoming';
  display_type: string;
  issue_id: string;
  issue_title: string;
  issue_status: IssueStatus;
  reason: string;
  created_by: string;
  created_at: string;
}

export interface RelationCreatePayload {
  type: RelationType;
  target_issue_id: string;
  reason?: string;
}

/* ── PM Notifications ── */

export type PMNotificationType = 'assigned' | 'status_changed' | 'blocked' | 'mentioned' | 'comment';

export interface PMNotification {
  id: string;
  user_email: string;
  type: PMNotificationType;
  text: string;
  issue_id: string;
  related_issue_id: string;
  relation_type: string;
  avatar: string;
  read: boolean;
  created_at: string;
}

/* ── Activity ── */

export type ActivitySource = 'pm' | 'agent';

export interface ActivityEntry {
  id: string;
  project_id: string;
  user_name: string;
  action: string;
  issue_id: string;
  detail: string;
  created_at: string;
  source: ActivitySource;
}

/* ── Pull Requests ── */

export type PRStatus = 'draft' | 'open' | 'approved' | 'changes_requested' | 'merged' | 'closed';

export interface PRResponse {
  id: string;
  project_id: string;
  title: string;
  description: string;
  branch: string;
  target_branch: string;
  status: PRStatus;
  author: string;
  issue_id: string | null;
  files_changed: number;
  additions: number;
  deletions: number;
  remote_url: string | null;
  created_at: string;
  updated_at: string;
}

export interface PRCreatePayload {
  title: string;
  description?: string;
  branch: string;
  target_branch?: string;
  issue_id?: string;
}

export interface PRStatusUpdatePayload {
  status: PRStatus;
  comment?: string;
}

export interface PRListParams {
  project_id?: string;
  status?: PRStatus;
}

/* ── Pulse ── */

export interface MetricValue {
  value: string;
  sub: string;
}

export interface TeamMemberActivity {
  name: string;
  completed: number;
  total: number;
}

export interface DependencyHealth {
  blocked: number;
  blocking: number;
  chains: number;
  bottlenecks: IssueResponse[];
}

export interface BurndownPoint {
  date: string;
  remaining: number;
  completed: number;
}

export interface PulseResponse {
  velocity: MetricValue;
  throughput: MetricValue;
  cycle_time: MetricValue;
  status_distribution: Record<string, number>;
  team_activity: TeamMemberActivity[];
  dependency_health: DependencyHealth;
  burndown: BurndownPoint[];
}

/* ── Workflow ── */

export type PhaseRunStatus = 'pending' | 'active' | 'completed' | 'skipped';
export type AgentRunStatus = 'idle' | 'running' | 'completed' | 'error';
export type DeliverableRunStatus = 'pending' | 'produced' | 'approved' | 'rejected';

export interface PhaseAgent {
  agent_id: string;
  name: string;
  status: AgentRunStatus;
  task_id: string | null;
}

export interface PhaseDeliverable {
  key: string;
  deliverable_type: string;
  status: DeliverableRunStatus;
  agent_id: string;
}

export interface PhaseStatus {
  id: string;
  name: string;
  status: PhaseRunStatus;
  agents: PhaseAgent[];
  deliverables: PhaseDeliverable[];
}

export interface WorkflowStatusResponse {
  project_slug: string;
  current_phase: string;
  phases: PhaseStatus[];
}

/* ── Project Types ── */

export interface WorkflowTemplate {
  id: string;
  name: string;
  filename: string;
  type: string;
  mode: 'sequential' | 'parallel';
  priority: number;
  depends_on: string | null;
}

export interface PhaseFile {
  phase_id: string;
  filename: string;
}

export interface PhaseFileContent {
  phase_id: string;
  filename: string;
  content: string;
}

export interface ChatTemplate {
  id: string;
  type: string;
  agents: string[];
  source_prompt: string;
}

export interface ProjectTypeResponse {
  id: string;
  name: string;
  description: string;
  team: string;
  workflows: WorkflowTemplate[];
  chats: ChatTemplate[];
}

/* ── Project Workflows ── */

export type ProjectWorkflowStatus = 'draft' | 'active' | 'paused' | 'completed';

export interface ProjectWorkflowResponse {
  id: string;
  project_id: string;
  workflow_template_id: string;
  name: string;
  type: string;
  mode: 'sequential' | 'parallel';
  status: ProjectWorkflowStatus;
  progress: number;
  depends_on: string[];
  created_at: string;
  updated_at: string;
}

export interface ProjectWorkflowCreatePayload {
  workflow_template_id: string;
  depends_on?: string[];
}

/* ── Automation ── */

export interface AutomationRule {
  id: string;
  project_id: string;
  workflow_type: string;
  deliverable_type: string;
  auto_approve: boolean;
  confidence_threshold: number;
  min_history: number;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export interface AutomationRuleCreatePayload {
  workflow_type: string;
  deliverable_type: string;
  auto_approve: boolean;
  confidence_threshold: number;
  min_history: number;
}

export interface AutomationStats {
  total_decisions: number;
  auto_approved: number;
  manual_reviewed: number;
  rejected: number;
}

export interface AgentConfidence {
  agent_id: string;
  confidence: number;
  decisions_count: number;
}

/* ── Project Detail ── */

export type ProjectHealth = 'on-track' | 'at-risk' | 'off-track';

export interface ProjectOverviewData {
  health: ProjectHealth;
  lead: string;
  start_date: string;
  end_date: string | null;
  members: string[];
  total_cost: number;
  issues_by_status: Record<IssueStatus, number>;
  deliverables_count: number;
  current_phase: string;
}

