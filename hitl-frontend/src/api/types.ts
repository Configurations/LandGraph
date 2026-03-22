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
  agent_name: string;
  agent_id: string;
  team_id: string;
  question_type: 'approval' | 'question';
  prompt: string;
  context: string;
  status: 'pending' | 'answered' | 'timeout' | 'cancelled';
  response: string | null;
  reviewer: string | null;
  channel: string;
  created_at: string;
  answered_at: string | null;
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
