export type SystemCriticality = 'low' | 'medium' | 'high' | 'critical'
export type SystemStatus = 'active' | 'maintenance' | 'retired'

export type NotificationSeverity = 'info' | 'warning' | 'critical'

export interface InAppNotification {
  id: string
  severity: NotificationSeverity
  title: string
  message: string
  entity_type: string | null
  entity_id: string | null
  read_at: string | null
  created_at: string
}

export type PublicStatusValue = 'operational' | 'degraded' | 'down' | 'unknown'

export interface PublicSystemStatus {
  name: string
  category: string | null
  status: PublicStatusValue
  last_checked_at: string | null
}

export interface PublicServerStatus {
  hostname: string
  site_name: string | null
  status: ServerStatus
  last_heartbeat_at: string | null
}

export interface System {
  id: string
  name: string
  slug: string
  description: string | null
  category: string | null
  criticality: SystemCriticality
  status: SystemStatus
  owner_user_id: string | null
  repo_url: string | null
  default_branch: string | null
  repo_local_path: string | null
  deploy_build_command: string | null
  created_at: string
  updated_at: string
}

export interface SystemInput {
  name: string
  slug: string
  description: string | null
  category: string | null
  criticality: SystemCriticality
  repo_url: string | null
  default_branch: string | null
  repo_local_path: string | null
  deploy_build_command: string | null
}

export type OSType = 'linux' | 'windows'
export type ServerStatus = 'online' | 'offline' | 'degraded' | 'unknown'
export type AgentStatus = 'pending' | 'active' | 'revoked' | 'unreachable'

export type ServerHealth = 'ok' | 'warning' | 'critical'

export const SERVER_USAGE_TAGS = [
  'SINOE',
  'EJE',
  'NCPP',
  'VISOR',
  'SIGRA',
  'REPOSITORIO',
  'WSUS',
  'DHCP',
  'ANTIVIRUS',
] as const

export type ServerUsageTag = (typeof SERVER_USAGE_TAGS)[number]

export interface Server {
  id: string
  site_id: string | null
  hostname: string
  ip_address: string | null
  os_type: OSType
  os_version: string | null
  cpu_cores: number | null
  ram_mb: number | null
  disk_gb: number | null
  status: ServerStatus
  created_at: string
  usage_tags: string[]
  primary_responsible_user_id: string | null
  primary_responsible_user_name: string | null
  health: ServerHealth
  health_reasons: string[]
  active_maintenance: MaintenanceWindowBrief | null
  is_synthetic_probe: boolean
}

export interface ServerInput {
  site_id: string | null
  hostname: string
  ip_address: string | null
  os_type: OSType
  os_version: string | null
  cpu_cores: number | null
  ram_mb: number | null
  disk_gb: number | null
  usage_tags: ServerUsageTag[]
  primary_responsible_user_id: string | null
  is_synthetic_probe: boolean
}

export interface DiskMetric {
  mount: string
  total_gb: number
  free_gb: number
  percent_used: number
  inode_total: number | null
  inode_used_percent: number | null
}

export interface ProcessMetric {
  pid: number
  name: string | null
  cpu_percent: number
  ram_mb: number
}

export interface DiskHealthInfo {
  device: string
  type: string
  power_on_hours: number | null
  smart_passed: boolean | null
  wearout_percent: number | null
  temperature_c: number | null
  error_count: number | null
}

export interface DiskIoInfo {
  device: string
  read_mbps: number
  write_mbps: number
}

export interface PortConnectionInfo {
  port: number
  connection_count: number
}

export interface ServerMetrics {
  agent_status: AgentStatus | null
  last_heartbeat_at: string | null
  metrics_updated_at: string | null
  cpu_percent: number | null
  ram_total_mb: number | null
  ram_used_mb: number | null
  ram_percent: number | null
  disks: DiskMetric[] | null
  net_bytes_sent: number | null
  net_bytes_recv: number | null
  uptime_seconds: number | null
  net_sent_rate_mbps: number | null
  net_recv_rate_mbps: number | null
  disk_read_mbps: number | null
  disk_write_mbps: number | null
  disk_io: DiskIoInfo[] | null
  top_cpu_processes: ProcessMetric[] | null
  top_ram_processes: ProcessMetric[] | null
  port_connections: PortConnectionInfo[] | null
  processes_updated_at: string | null
  agent_version: string | null
  kernel_version: string | null
  cpu_model: string | null
  load_average_1m: number | null
  disk_health: DiskHealthInfo[] | null
  disk_health_available: boolean | null
}

export interface ServerNote {
  id: string
  server_id: string
  author_id: string | null
  author_name: string | null
  body: string
  created_at: string
}

export interface ServerEvent {
  id: string
  server_id: string
  log_name: string
  event_record_id: number
  level: number
  provider: string | null
  event_id: number | null
  message: string | null
  occurred_at: string
  received_at: string
}

export interface SiteUserBrief {
  id: string
  full_name: string
}

export interface OfflineServerBrief {
  id: string
  hostname: string
  status: string
}

export interface OpenAlertBrief {
  id: string
  hostname: string | null
  rule_name: string
  severity: string
  value: number | null
  acknowledged: boolean
}

export interface FailedBackupBrief {
  id: string
  service_name: string
  type: string
  error_message: string | null
  started_at: string | null
}

export interface WeeklyReport {
  site_id: string | null
  site_name: string | null
  window_start: string
  window_end: string
  servers_total: number
  servers_online: number
  servers_offline: number
  offline_servers: OfflineServerBrief[]
  open_alerts_by_severity: Record<string, number>
  unacknowledged_open_alerts: number
  open_alerts: OpenAlertBrief[]
  backup_failures: number
  failed_backups: FailedBackupBrief[]
}

export interface ServerMetricHistoryPoint {
  recorded_at: string
  cpu_percent: number | null
  ram_percent: number | null
  disk_percent_used: number | null
  net_bytes_sent: number | null
  net_bytes_recv: number | null
}

export interface ServerActivityItem {
  kind: 'service_action' | 'notification'
  occurred_at: string
  title: string
  detail: string | null
  status: string
}

export interface ServerOutage {
  started_at: string
  ended_at: string | null
  duration_seconds: number
}

export interface ServerUptimeSummary {
  window_days: number
  uptime_percent: number
  outages: ServerOutage[]
}

export interface FleetConnectivityEvent {
  id: string
  server_id: string
  hostname: string
  site_id: string | null
  site_name: string | null
  event_type: 'disconnected' | 'reconnected'
  occurred_at: string
  message: string
}

export interface CriticalConnectivityAlert {
  id: string
  server_id: string
  hostname: string
  site_name: string | null
  occurred_at: string
  message: string
}

export interface ServerConnectivitySummary {
  server_id: string
  hostname: string
  site_id: string | null
  site_name: string | null
  status: 'online' | 'offline' | 'degraded' | 'unknown'
  uptime_percent: number | null
  outage_count: number
  last_event_type: 'disconnected' | 'reconnected' | null
  last_event_at: string | null
  last_event_message: string | null
}

export interface DiskForecast {
  sample_days: number
  sample_count: number
  current_percent: number | null
  trend_percent_per_day: number | null
  days_until_full: number | null
}

export interface NetworkHop {
  hop_number: number
  address: string | null
  avg_latency_ms: number | null
  packet_loss_percent: number | null
}

export interface NetworkPathSample {
  recorded_at: string
  target: string
  reachable: boolean
  hops: NetworkHop[]
  quality_score: number | null
}

export interface NetworkPathHistory {
  current: NetworkPathSample | null
  samples: NetworkPathSample[]
}

export interface NetworkPathFleetRow {
  server_id: string
  hostname: string
  site_id: string | null
  site_name: string | null
  target: string | null
  reachable: boolean | null
  hop_count: number | null
  final_latency_ms: number | null
  destination_loss_percent: number | null
  intermediate_max_loss_percent: number | null
  quality_score: number | null
  recorded_at: string | null
}

export interface NetworkLatencySparklinePoint {
  recorded_at: string
  latency_ms: number | null
}

export interface NetworkLatencySparkline {
  server_id: string
  points: NetworkLatencySparklinePoint[]
}

export interface OsComparison {
  os_type: string
  server_count: number
  ok_count: number
  warning_count: number
  critical_count: number
  avg_cpu_percent: number | null
  avg_ram_percent: number | null
  avg_uptime_percent: number | null
}

export interface SiteRanking {
  site_id: string
  site_name: string
  server_count: number
  ok_count: number
  warning_count: number
  critical_count: number
  avg_cpu_percent: number | null
  avg_ram_percent: number | null
  avg_uptime_percent: number | null
  avg_network_score: number | null
  open_alerts: number
  servers_in_maintenance: number
}

export interface AlertTrendPoint {
  week_start: string
  critical: number
  warning: number
  info: number
}

export interface TopOffender {
  server_id: string
  hostname: string
  site_name: string | null
  value: number
}

export interface MaintenanceFleetItem {
  id: string
  scope_type: MaintenanceScope
  scope_label: string
  reason: string
  starts_at: string
  ends_at: string
}

export interface MaintenanceSummary {
  active_count: number
  scheduled_count: number
  active: MaintenanceFleetItem[]
}

export interface FleetDashboard {
  os_comparison: OsComparison[]
  site_ranking: SiteRanking[]
  alert_trend: AlertTrendPoint[]
  worst_uptime: TopOffender[]
  most_alerts: TopOffender[]
  highest_cpu: TopOffender[]
  highest_ram: TopOffender[]
  worst_network: TopOffender[]
  maintenance: MaintenanceSummary
}

export interface ServerSparklinePoint {
  recorded_at: string
  cpu_percent: number | null
  ram_percent: number | null
}

export interface ServerSparkline {
  server_id: string
  points: ServerSparklinePoint[]
}

export type AlertScope = 'server' | 'service' | 'system'
export type AlertCondition = 'gt' | 'lt' | 'gte' | 'lte' | 'eq'
export type AlertSeverityLevel = 'info' | 'warning' | 'critical'
export type AlertEventStatus = 'open' | 'resolved'
export type AlertMetric =
  | 'ram_percent'
  | 'cpu_percent'
  | 'disk_percent_used'
  | 'network_reachable'
  | 'network_latency_ms'
  | 'network_loss_percent'

export interface AlertRule {
  id: string
  name: string
  scope_type: AlertScope
  scope_id: string | null
  metric: AlertMetric
  metric_target: string | null
  condition: AlertCondition
  threshold: number
  severity: AlertSeverityLevel
  custom_message: string | null
  cooldown_minutes: number
  enabled: boolean
  created_at: string
}

export interface AlertRuleInput {
  name: string
  scope_type: AlertScope
  scope_id: string | null
  metric: AlertMetric
  metric_target: string | null
  condition: AlertCondition
  threshold: number
  severity: AlertSeverityLevel
  custom_message: string | null
  cooldown_minutes: number
  enabled: boolean
}

export interface AlertEvent {
  id: string
  alert_rule_id: string
  rule_name: string
  severity: AlertSeverityLevel
  metric: AlertMetric
  metric_target: string | null
  server_id: string | null
  hostname: string | null
  site_id: string | null
  site_name: string | null
  triggered_at: string
  resolved_at: string | null
  value: number | null
  status: AlertEventStatus
  acknowledged_at: string | null
  acknowledged_by_id: string | null
  acknowledged_by_name: string | null
  during_maintenance: boolean
}

export type MaintenanceScope = 'server' | 'site'
export type MaintenanceStatus = 'scheduled' | 'active' | 'ended' | 'cancelled'

export interface MaintenanceWindowBrief {
  id: string
  scope_type: MaintenanceScope
  reason: string
  ends_at: string
}

export interface MaintenanceWindow {
  id: string
  scope_type: MaintenanceScope
  scope_id: string
  scope_label: string
  reason: string
  description: string | null
  starts_at: string
  ends_at: string
  cancelled_at: string | null
  status: MaintenanceStatus
  created_by_id: string | null
  created_by_name: string | null
  created_at: string
}

export interface MaintenanceWindowInput {
  scope_type: MaintenanceScope
  scope_id: string
  reason: string
  description: string | null
  starts_at: string
  ends_at: string
}

export type ProblemKind =
  | 'alert'
  | 'server_offline'
  | 'server_degraded'
  | 'service_degraded'
  | 'backup_failed'
  | 'deploy_failed'
  | 'synthetic_failed'

export interface ProblemRow {
  id: string
  kind: ProblemKind
  severity: AlertSeverityLevel
  title: string
  detail: string | null
  server_id: string | null
  hostname: string | null
  site_id: string | null
  site_name: string | null
  system_id: string | null
  system_name: string | null
  occurred_at: string
  during_maintenance: boolean
  alert_event_id: string | null
  acknowledged_at: string | null
}

export interface FleetStatusCounts {
  online: number
  offline: number
  degraded: number
  unknown: number
}

export interface FleetAgentStatusCounts {
  pending: number
  active: number
  revoked: number
  unreachable: number
}

export interface SiteAverage {
  site_id: string | null
  site_name: string | null
  server_count: number
}

export interface BreachingServer {
  server_id: string
  hostname: string
  site_name: string | null
  rule_name: string
  metric: string
  mount: string | null
  severity: string
  value: number
  threshold: number
}

export interface RecentIncident {
  id: string
  severity: string
  title: string
  message: string
  created_at: string
}

export interface FleetSummary {
  status_counts: FleetStatusCounts
  agent_status_counts: FleetAgentStatusCounts
  site_averages: SiteAverage[]
  breaching_servers: BreachingServer[]
}

export type ServiceType =
  | 'frontend'
  | 'backend'
  | 'database'
  | 'cache'
  | 'proxy'
  | 'windows_service'
  | 'pm2_process'
  | 'ftp'
  | 'smtp'
  | 'cron_job'
  | 'other'

export type ControlStrategy = 'systemd' | 'windows_service' | 'pm2' | 'docker' | 'script'
export type ServiceStatus = 'running' | 'stopped' | 'degraded' | 'unknown'
export type ServiceAction = 'start' | 'stop' | 'restart' | 'force_restart'

export interface Service {
  id: string
  system_id: string
  server_id: string | null
  name: string
  type: ServiceType
  control_strategy: ControlStrategy
  control_identifier: string | null
  port: number | null
  health_check_url: string | null
  status: ServiceStatus
  last_checked_at: string | null
}

export interface ServiceInput {
  system_id: string
  server_id: string | null
  name: string
  type: ServiceType
  control_strategy: ControlStrategy
  control_identifier: string | null
  port: number | null
  health_check_url: string | null
}

export interface ServiceActionLog {
  id: string
  service_id: string
  action: ServiceAction
  status: string
  started_at: string | null
  finished_at: string | null
  output: string | null
}

export interface SyntheticCheckResult {
  id: string
  service_id: string
  prober_server_id: string | null
  prober_hostname: string | null
  success: boolean
  status_code: number | null
  latency_ms: number | null
  error_message: string | null
  checked_at: string
}

export type SyntheticOverallStatus = 'up' | 'degraded' | 'down' | 'unknown'

export interface SyntheticProberStatus {
  prober_server_id: string | null
  prober_hostname: string | null
  success: boolean
  status_code: number | null
  latency_ms: number | null
  error_message: string | null
  checked_at: string
  uptime_percent: number | null
}

export interface SyntheticCheckSummary {
  service_id: string
  service_name: string
  system_id: string
  system_name: string
  health_check_url: string
  server_id: string | null
  hostname: string | null
  site_id: string | null
  site_name: string | null
  overall_status: SyntheticOverallStatus
  uptime_percent: number | null
  avg_latency_ms: number | null
  probers: SyntheticProberStatus[]
}

export type BackupType = 'database' | 'files' | 'full'
export type RunStatus = 'pending' | 'running' | 'success' | 'failed'

export interface BackupJob {
  id: string
  service_id: string
  type: BackupType
  source_path: string
  storage_path: string
  retention_days: number
  schedule_cron: string | null
  enabled: boolean
  created_at: string
}

export interface BackupJobInput {
  service_id: string
  type: BackupType
  source_path: string
  storage_path: string
  retention_days: number
  schedule_cron?: string | null
}

export interface BackupRun {
  id: string
  backup_job_id: string
  status: RunStatus
  triggered_by: 'manual' | 'scheduled'
  size_bytes: number | null
  sha256_hash: string | null
  storage_path: string | null
  started_at: string | null
  finished_at: string | null
  error_message: string | null
}

export interface BackupRunPage {
  items: BackupRun[]
  total: number
}

export interface ConfigEntry {
  id: string
  service_id: string
  key: string
  value: string | null
  is_secret: boolean
  description: string | null
  version: number
  updated_at: string
}

export interface ConfigEntryInput {
  service_id: string
  environment_code: string
  key: string
  value: string
  is_secret: boolean
  description: string | null
}

export interface ConfigEntryHistoryEntry {
  id: string
  previous_value: string | null
  changed_at: string
}

export type VersionStatus = 'active' | 'rolled_back' | 'deprecated'

export interface SystemVersion {
  id: string
  system_id: string
  version_number: string
  git_commit_hash: string | null
  git_branch: string | null
  release_notes: string | null
  status: VersionStatus
  released_by_id: string | null
  released_at: string | null
  created_at: string
}

export interface DeployCheckResult {
  is_dirty: boolean
  dirty_files: string[]
  current_commit: string | null
  remote_commit: string | null
  commits_behind: number
  error: string | null
}

export type DeploymentStatus = 'pending' | 'running' | 'success' | 'failed' | 'rolled_back'

export interface Deployment {
  id: string
  system_id: string
  version_id: string | null
  source: 'git' | 'zip' | 'manual'
  status: DeploymentStatus
  triggered_by_id: string | null
  started_at: string | null
  finished_at: string | null
  log_output: string | null
  rollback_of_id: string | null
}

export interface SystemVersionInput {
  version_number: string
  git_commit_hash: string | null
  git_branch: string | null
  release_notes: string | null
}

export type DocumentType =
  | 'manual_tecnico'
  | 'manual_usuario'
  | 'arquitectura'
  | 'diagrama'
  | 'script'
  | 'pdf'
  | 'imagen'
  | 'video'
  | 'procedimiento'

export interface DocumentEntry {
  id: string
  system_id: string
  title: string
  doc_type: DocumentType
  file_path: string
  version: string | null
  uploaded_by_id: string | null
  uploaded_at: string
}

export interface License {
  id: string
  name: string
  vendor: string | null
  system_id: string | null
  server_id: string | null
  expiry_date: string | null
  seats: number | null
  cost: number | null
  notes: string | null
  created_at: string
}

export interface LicenseInput {
  name: string
  vendor: string | null
  system_id: string | null
  server_id: string | null
  expiry_date: string | null
  seats: number | null
  cost: number | null
  notes: string | null
}

export type DependencyType = 'library' | 'service' | 'external_api'

export interface Dependency {
  id: string
  system_id: string
  name: string
  type: DependencyType
  version: string | null
  criticality: string | null
  notes: string | null
}

export interface DependencyInput {
  system_id: string
  name: string
  type: DependencyType
  version: string | null
  criticality: string | null
  notes: string | null
}

export type NotificationChannelType = 'email' | 'telegram' | 'whatsapp' | 'teams'

export interface NotificationChannel {
  id: string
  type: NotificationChannelType
  name: string
  enabled: boolean
  created_at: string
}

export interface NotificationLogEntry {
  id: string
  channel_id: string
  alert_event_id: string | null
  sent_at: string
  status: 'sent' | 'failed'
  error_message: string | null
}

export interface NotificationLogPage {
  items: NotificationLogEntry[]
  total: number
}

export interface RestoreOperation {
  id: string
  backup_run_id: string
  status: RunStatus
  restored_to_path: string | null
  started_at: string | null
  finished_at: string | null
  notes: string | null
}

export interface Site {
  id: string
  name: string
  code: string
  address: string | null
  timezone: string
}

export interface SiteInput {
  name: string
  code: string
  address: string | null
  timezone: string
}

export interface Permission {
  id: string
  code: string
  description: string | null
}

export interface Role {
  id: string
  name: string
  description: string | null
  is_system_role: boolean
  permission_codes: string[]
}

export interface RoleInput {
  name: string
  description: string | null
  permission_codes: string[]
}

export interface AdminUser {
  id: string
  dni: string
  email: string | null
  username: string
  full_name: string
  phone: string | null
  site_ids: string[]
  site_names: string[]
  role_id: string | null
  role_name: string | null
  permission_codes: string[]
  is_active: boolean
  is_superuser: boolean
  mfa_enabled: boolean
  last_login_at: string | null
  created_at: string
}

export interface AdminUserCreateInput {
  dni: string
  email: string | null
  username: string
  full_name: string
  password: string
  phone: string | null
  site_ids: string[]
  role_id: string | null
  is_superuser: boolean
  is_active: boolean
}

export interface AuditLogEntry {
  id: string
  user_id: string | null
  user_full_name: string | null
  action: string
  entity_type: string
  entity_id: string | null
  details: Record<string, unknown> | null
  ip_address: string | null
  created_at: string
}

export interface AdminUserUpdateInput {
  email?: string | null
  username?: string
  full_name?: string
  phone?: string | null
  site_ids?: string[]
  role_id?: string | null
  is_active?: boolean
  is_superuser?: boolean
}
