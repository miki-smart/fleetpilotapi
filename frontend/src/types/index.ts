export type VehicleStatus = 'ACTIVE' | 'MAINTENANCE_DUE' | 'OUT_OF_SERVICE';
export type IncidentSeverity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL';
export type IncidentStatus = 'NEW' | 'ANALYZING' | 'AWAITING_APPROVAL' | 'APPROVED' | 'IN_PROGRESS' | 'RESOLVED' | 'REJECTED';
export type TaskStatus = 'PENDING_APPROVAL' | 'APPROVED' | 'ASSIGNED' | 'IN_PROGRESS' | 'COMPLETED' | 'CANCELLED';
export type NotificationStatus = 'PENDING' | 'SENT' | 'SIMULATED' | 'FAILED';
export type AgentActionStatus = 'PENDING' | 'SUCCESS' | 'FAILED';

export interface Vehicle {
  id: string;
  fleet_number: string;
  vin?: string;
  make: string;
  model: string;
  year: number;
  mileage: number;
  status: VehicleStatus;
  fuel_type?: string;
  last_service_date?: string;
  next_service_mileage?: number;
  km_until_service?: number;
  created_at?: string;
  updated_at?: string;
}

export interface MaintenanceRecord {
  id: string;
  maintenance_type: string;
  description?: string;
  mileage?: number;
  performed_at: string;
  status: string;
}

export interface Incident {
  id: string;
  vehicle_id: string;
  vehicle_fleet_number?: string;
  vehicle_make?: string;
  vehicle_model?: string;
  reported_by: string;
  description: string;
  severity?: IncidentSeverity;
  category?: string;
  status: IncidentStatus;
  ai_analysis?: IncidentAnalysis | null;
  created_at: string;
  updated_at?: string;
  agent_actions?: AgentAction[];
  maintenance_tasks?: MaintenanceTaskSummary[];
  vehicle?: VehicleRef;
}

export interface VehicleRef {
  fleet_number: string;
  make: string;
  model: string;
  year: number;
  mileage: number;
  status: VehicleStatus;
}

export interface IncidentAnalysis {
  category: string;
  severity: IncidentSeverity;
  vehicle_status: VehicleStatus;
  summary: string;
  possible_causes: string[];
  recommended_actions: string[];
  required_parts: { name: string; quantity: number }[];
  related_recalls?: string[];
  requires_manager_approval: boolean;
}

/** Response of POST /api/incidents/{id}/analyze */
export interface AnalyzeResult {
  incident_id: string;
  analysis: IncidentAnalysis | null;
  agent_actions: AgentAction[];
  status: IncidentStatus;
  provider?: string;
  analysis_source?: 'model' | 'synthesized_from_actions';
  demo_mode?: boolean;
  demo_reason?: string;
  error?: string;
}

export interface MaintenanceTask {
  id: string;
  vehicle_id: string;
  incident_id?: string;
  title: string;
  description?: string;
  severity: IncidentSeverity;
  status: TaskStatus;
  assigned_to?: string;
  due_date?: string;
  ai_generated: boolean;
  created_at: string;
  updated_at?: string;
  vehicle?: { fleet_number: string; make: string; model: string; year: number } | null;
  parts_count?: number;
  parts_requests?: PartsRequest[];
  vehicle_status?: VehicleStatus | null;
  vehicle_restored?: boolean;
}

export interface MaintenanceTaskSummary {
  id: string;
  title: string;
  severity: IncidentSeverity;
  status: TaskStatus;
  ai_generated: boolean;
}

export interface PartsRequest {
  id: string;
  part_name: string;
  quantity: number;
  priority: string;
  status: string;
}

export interface Notification {
  id: string;
  recipient: string;
  channel: string;
  subject: string;
  message: string;
  status: NotificationStatus;
  related_entity_type?: string;
  related_entity_id?: string;
  created_at: string;
}

export interface AgentAction {
  id: string;
  action_type: string;
  description?: string;
  status: AgentActionStatus;
  tool_name?: string;
  tool_input?: Record<string, unknown>;
  tool_output?: Record<string, unknown>;
  created_at: string;
  completed_at?: string;
  incident_id?: string;
}

export interface LastScan {
  id: string;
  ran_at: string | null;
  triggered_by: string;
  description?: string;
  overdue?: number;
  upcoming?: number;
  recalls?: number;
  tasks_created?: number;
  notifications_sent?: number;
  reminders_sent?: number;
  digest_provider?: string;
  digest_email_status?: string | null;
  duration_s?: number;
}

export interface AutomationSummary {
  last_scan: LastScan | null;
  next_run_at: string | null;
  schedule_cron: string;
  timezone: string;
  scheduler_running: boolean;
}

export interface DashboardData {
  fleet_stats: {
    total: number;
    healthy: number;
    maintenance_due: number;
    out_of_service: number;
    pending_approvals: number;
  };
  risk_score: number;
  critical_alerts: CriticalAlert[];
  upcoming_maintenance: UpcomingMaintenance[];
  recent_agent_actions: AgentAction[];
  automation: AutomationSummary;
}

export interface CriticalAlert {
  incident_id: string;
  vehicle_fleet_number: string;
  vehicle_make: string;
  vehicle_model: string;
  description: string;
  severity: IncidentSeverity;
  status: IncidentStatus;
  category?: string;
  created_at: string;
}

export interface UpcomingMaintenance {
  vehicle_id: string;
  fleet_number: string;
  make: string;
  model: string;
  km_until_service: number;
  next_service_mileage: number;
  current_mileage: number;
  status: VehicleStatus;
}

export interface FleetScanResult {
  scanned_at: string;
  triggered_by: string;
  vehicles_scanned: number;
  overdue_found: number;
  upcoming_found: number;
  recalls_found: number;
  tasks_created: number;
  notifications_sent: number;
  reminders_sent: number;
  findings: FleetScanFinding[];
  digest: string | null;
  digest_provider: string | null;
  digest_email_status: NotificationStatus | null;
}

export interface FleetScanFinding {
  type: 'OVERDUE' | 'UPCOMING' | 'RECALL';
  fleet_number: string;
  make: string;
  model: string;
  current_mileage: number;
  km_remaining?: number;
  km_overdue?: number;
  recall_count?: number;
  campaign_number?: string | null;
  component?: string | null;
  summary?: string | null;
  remedy?: string | null;
  severity?: IncidentSeverity;
  task_created: boolean;
  notification_sent: boolean;
}

export interface SchedulerStatus {
  enabled: boolean;
  running: boolean;
  timezone: string;
  cron: string;
  interval_minutes: number;
  external_token_configured: boolean;
  jobs: { id: string; trigger: string; next_run_at: string | null }[];
}

export interface AutomationStatus {
  scheduler: SchedulerStatus;
  last_scan: LastScan | null;
}

export type AIProvider = 'groq' | 'gemini';

export interface AIProviderConfig {
  model: string;
  key_configured: boolean;
  key_hint?: string | null;
  available: boolean;
}

export interface KeyValidation {
  provider: string;
  ok: boolean;
  error?: string | null;
  models: number;
}

export interface AISettings {
  provider: AIProvider;
  active_key_configured: boolean;
  groq: AIProviderConfig;
  gemini: AIProviderConfig;
  validation?: KeyValidation;
}

export interface UpdateAISettingsPayload {
  provider?: AIProvider;
  groq_model?: string;
  groq_api_key?: string;
  gemini_model?: string;
  gemini_api_key?: string;
}
