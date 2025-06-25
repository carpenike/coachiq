/**
 * API Types for CoachIQ Frontend
 *
 * TypeScript interfaces that match the backend API models.
 * These types ensure type safety when working with API responses.
 */

// Base Entity Interface
export interface EntityBase {
  entity_id: string;
  name?: string;  // Made optional since backend may not always include this
  friendly_name: string | null;
  device_type: string;
  suggested_area: string;
  state: string;
  raw: Record<string, unknown>;
  capabilities: string[];
  timestamp: number;  // Backend returns timestamp, not last_updated
  value: Record<string, unknown>;  // Backend includes value field
  groups: string[];  // Backend includes groups field
  // Legacy fields for backward compatibility
  id?: string;
  last_updated?: string;
  source_type?: string;
  entity_type?: string;
  current_state?: string;
}

// Light-specific interface extending base entity
export interface LightEntity extends EntityBase {
  device_type: "light";
  brightness?: number;
}

// Lock-specific interface extending base entity
export interface LockEntity extends EntityBase {
  device_type: "lock";
}

// Temperature sensor interface extending base entity
export interface TemperatureEntity extends EntityBase {
  device_type: "temperature";
  temperature?: number;
  units?: string;
}

// Tank sensor interface extending base entity
export interface TankEntity extends EntityBase {
  device_type: "tank";
  level?: number;
  capacity?: number;
  tank_type?: string;
}

// Aliases for backward compatibility
export type TankSensorEntity = TankEntity;
export type TemperatureSensorEntity = TemperatureEntity;
export type EntityData = Entity;

// Union type for all entity types
export type Entity = LightEntity | LockEntity | TemperatureEntity | TankEntity | EntityBase;

// Entity collections (API responses return dictionaries keyed by entity ID)
export type EntityCollection = Record<string, Entity>;

// Control Command Structure (matches backend ControlCommand model)
export interface ControlCommand {
  command: string;
  command_type?: string;
  parameters?: Record<string, unknown>;
  state?: boolean | null;
  brightness?: number;
  level?: number;
  temperature?: number;
}

// Control Response Structure (matches backend ControlEntityResponse model)
export interface ControlEntityResponse {
  success: boolean;
  message: string;
  entity_id: string;
  entity_type?: string;
  command: ControlCommand;
  timestamp: string;
  execution_time_ms?: number;
}

// Entity Mapping Creation Request (matches backend CreateEntityMappingRequest model)
export interface CreateEntityMappingRequest {
  // Source unmapped entry information
  pgn_hex: string;
  instance: string;

  // Entity configuration
  entity_id: string;
  friendly_name: string;
  device_type: string;
  suggested_area?: string;
  capabilities?: string[];
  notes?: string;
}

// Entity Mapping Creation Response (matches backend CreateEntityMappingResponse model)
export interface CreateEntityMappingResponse {
  status: "success" | "error";
  entity_id: string;
  message: string;
  entity_data: Record<string, unknown> | null;
}

// Entity History Entry
export interface HistoryEntry {
  timestamp: string;
  state: string;
  raw: Record<string, unknown>;
  source: string;
}

// CAN Interface Stats (matches backend CANInterfaceStats model)
export interface CANInterfaceStats {
  name: string;
  state: string | null;
  restart_ms: number | null;
  bitrate: number | null;
  sample_point: number | null;
  tx_count: number | null;
  rx_count: number | null;
  error_count: number | null;
  parentdev: string | null;
  error_warning: number | null;
  error_passive: number | null;
  bus_off: number | null;
  raw_details: string | null;
}

// All CAN Stats (matches backend AllCANStats model)
export interface AllCANStats {
  interfaces: Record<string, CANInterfaceStats>;
  total_messages?: number;
  total_errors?: number;
}

// CAN Message Structure
export interface CANMessage {
  timestamp: string;
  pgn: string;
  instance?: number;
  source: number;
  data: number[];
  error?: boolean;
  interface?: string;
}

// CAN Metrics (for bus health monitoring)
export interface CANMetrics {
  messageRate: number;
  totalMessages: number;
  errorCount: number;
  uptime: number;
}

// Unmapped Entry Model (matches backend UnmappedEntryModel)
export interface UnmappedEntry {
  pgn_hex: string;
  pgn_name: string;
  dgn_hex: string;
  dgn_name: string;
  instance: string;
  last_data_hex: string;
  decoded_signals: Record<string, unknown>;
  first_seen_timestamp: number;
  last_seen_timestamp: number;
  count: number;
  suggestions: string[];
  spec_entry: Record<string, unknown>;
}

// Unknown PGN Entry (matches backend UnknownPGNEntry)
export interface UnknownPGNEntry {
  pgn_hex: string;
  pgn_name: string;
  arbitration_id_hex?: string;
  first_seen_timestamp: number;
  last_seen_timestamp: number;
  count: number;
  example_data: string;
  last_data_hex?: string;
  source_addresses: string[];
}

// API Response Collections
export interface UnmappedResponse {
  unmapped_entries: Record<string, UnmappedEntry>;
}

export interface UnknownPGNResponse {
  unknown_pgns: Record<string, UnknownPGNEntry>;
}

// Metadata Response Structure
export interface MetadataResponse {
  device_types: string[];
  areas: string[];
  capabilities: string[];
  states: string[];
}

// Health Status Response (matches backend /healthz)
export interface ServiceMetadata {
  name: string;
  version: string;
  environment: string;
  hostname: string;
  platform: string;
}

export interface HealthStatus {
  status: "healthy" | "degraded" | "failed";
  features: Record<string, string>;
  unhealthy_features?: Record<string, string>;
  all_features?: Record<string, string>;

  // Enhanced metadata from Domain API v2
  response_time_ms?: number;
  service?: ServiceMetadata;
  description?: string;
}

// Feature Status from /api/status/features
export interface FeatureInfo {
  enabled: boolean;
  core: boolean;
  health: string;
  type: string;
}

export interface FeatureStatusResponse {
  total_features: number;
  enabled_count: number;
  core_count: number;
  optional_count: number;
  features: Record<string, FeatureInfo>;
}

// Legacy FeatureStatus (for backward compatibility)
export interface FeatureStatus {
  name: string;
  enabled: boolean;
  core: boolean;
  depends_on: string[];
  description: string;
}

// Queue Status Response (matches backend CAN service response)
export interface QueueStatus {
  length: number;
  maxsize: number | "unbounded";
}

// WebSocket Message Types
export interface WebSocketMessage {
  type: string;
  data: unknown;
  timestamp: string;
}

export interface EntityUpdateMessage extends WebSocketMessage {
  type: "entity_update";
  data: {
    entity_id: string;
    entity_data: Entity;
  };
}

export interface CANMessageUpdate extends WebSocketMessage {
  type: "can_message";
  data: CANMessage;
}

export interface SystemStatusMessage extends WebSocketMessage {
  type: "system_status";
  data: {
    connected_clients: number;
    can_interfaces: string[];
    last_message_time: string;
  };
}

// Union type for all WebSocket message types
export type WebSocketMessageType = EntityUpdateMessage | CANMessageUpdate | SystemStatusMessage | WebSocketMessage;

// WebSocket Handlers Interface
export interface WebSocketHandlers {
  onEntityUpdate?: (data: EntityUpdateMessage['data']) => void;
  onCANMessage?: (data: CANMessage) => void;
  onSystemStatus?: (data: SystemStatusMessage['data']) => void;
  onDiagnosticUpdate?: (data: DiagnosticUpdateMessage['data']) => void;
  onPerformanceUpdate?: (data: PerformanceUpdateMessage['data']) => void;
  onMultiProtocolUpdate?: (data: MultiProtocolUpdateMessage['data']) => void;
  onMessage?: (message: ExtendedWebSocketMessageType) => void;
  onOpen?: () => void;
  onClose?: (event: CloseEvent) => void;
  onError?: (error: Event) => void;
}

// API Error Response
export interface APIError {
  detail: string;
  status_code: number;
  timestamp: string;
}

// Generic API Response Wrapper
export interface APIResponse<T> {
  data: T;
  success: boolean;
  message?: string;
  timestamp: string;
}

// Query Parameters for API endpoints
export interface EntitiesQueryParams extends Record<string, unknown> {
  device_type?: string;
  area?: string;
}

export interface HistoryQueryParams extends Record<string, unknown> {
  limit?: number;
  since?: number;
}

export interface CANSendParams {
  arbitration_id: number;
  data: string;
  interface: string;
}

// Light Control Helpers (common commands)
export interface LightControlCommands {
  turnOn: () => ControlCommand;
  turnOff: () => ControlCommand;
  toggle: () => ControlCommand;
  setBrightness: (brightness: number) => ControlCommand;
  brightnessUp: () => ControlCommand;
  brightnessDown: () => ControlCommand;
}

// Dashboard aggregation types
export interface EntitySummary {
  total_entities: number;
  online_entities: number;
  active_entities: number;
  device_type_counts: Record<string, number>;
  area_counts: Record<string, number>;
  health_score: number;
}

export interface SystemMetrics {
  uptime_seconds: number;
  message_rate: number;
  error_rate: number;
  memory_usage_mb: number;
  cpu_usage_percent: number;
  websocket_connections: number;
}

export interface CANBusSummary {
  interfaces_count: number;
  total_messages: number;
  messages_per_minute: number;
  error_count: number;
  queue_length: number;
  bus_load_percent: number;
}

export interface ActivityEntry {
  id: string;
  timestamp: string;
  event_type: string;
  entity_id?: string;
  title: string;
  description: string;
  severity: string;
  metadata: Record<string, unknown>;
}

export interface ActivityFeed {
  entries: ActivityEntry[];
  total_count: number;
  has_more: boolean;
}

export interface DashboardSummary {
  timestamp: string;
  entities: EntitySummary;
  system: SystemMetrics;
  can_bus: CANBusSummary;
  activity: ActivityFeed;
  alerts: string[];
  quick_stats: Record<string, unknown>;
}

export interface BulkControlRequest {
  entity_ids: string[];
  command: string;
  parameters: Record<string, unknown>;
  ignore_errors: boolean;
}

export interface BulkControlResult {
  entity_id: string;
  success: boolean;
  message: string;
  error?: string;
}

export interface BulkControlResponse {
  total_requested: number;
  successful: number;
  failed: number;
  results: BulkControlResult[];
  summary: string;
}

export interface AlertDefinition {
  id: string;
  name: string;
  description: string;
  condition: string;
  severity: string;
  enabled: boolean;
  threshold?: number;
}

export interface ActiveAlert {
  alert_id: string;
  triggered_at: string;
  current_value: number;
  threshold: number;
  message: string;
  severity: string;
  acknowledged: boolean;
}

export interface SystemAnalytics {
  alerts: ActiveAlert[];
  performance_trends: Record<string, number[]>;
  health_checks: Record<string, boolean>;
  recommendations: string[];
}

//
// ===== ADVANCED DIAGNOSTICS TYPES =====
//

// System Health Response (matches backend SystemHealthResponse)
export interface SystemHealthResponse {
  overall_health: number; // 0.0-1.0
  system_scores: Record<string, number>;
  status: "healthy" | "warning" | "critical";
  recommendations: string[];
  last_assessment: number;
  active_dtcs: number;
}

// DTC Filters for API queries
export interface DTCFilters {
  system_type?: string;
  severity?: string;
  protocol?: string;
}

// Diagnostic Trouble Code (matches backend DTC models)
export interface DiagnosticTroubleCode {
  id: string;
  code: string;
  protocol: "rvc" | "j1939" | "firefly" | "spartan_k2";
  system_type: string;
  severity: "low" | "medium" | "high" | "critical";
  description: string;
  first_seen: string;
  last_seen: string;
  count: number;
  resolved: boolean;
  source_address: number;
  pgn?: number;
  dgn?: number;
  metadata: Record<string, unknown>;
}

// DTC Collection Response
export interface DTCCollection {
  dtcs: DiagnosticTroubleCode[];
  total_count: number;
  active_count: number;
  by_severity: Record<string, number>;
  by_protocol: Record<string, number>;
}

// DTC Resolution Response
export interface DTCResolutionResponse {
  resolved: boolean;
  dtc_id: string;
  message: string;
  timestamp: string;
}

// Fault Correlation
export interface FaultCorrelation {
  primary_dtc: string;
  related_dtcs: string[];
  confidence: number; // 0.0-1.0
  temporal_relationship: "simultaneous" | "sequential" | "intermittent";
  suggested_cause: string;
  correlation_id: string;
  detected_at: string;
  pattern_type: string;
}

// Maintenance Prediction
export interface MaintenancePrediction {
  component_name: string;
  system_type: string;
  failure_probability: number; // 0.0-1.0
  predicted_failure_date: string;
  confidence: number; // 0.0-1.0
  recommended_action: string;
  urgency: "low" | "medium" | "high" | "critical";
  estimated_cost: number;
  historical_patterns: string[];
}

// Maintenance Alert
export interface MaintenanceAlert {
  alert_id: string;
  component_name: string;
  prediction_id: string;
  urgency: "low" | "medium" | "high" | "critical";
  message: string;
  recommended_action: string;
  deadline: string;
  estimated_cost: number;
  acknowledged: boolean;
}

// Diagnostic Statistics
export interface DiagnosticStats {
  total_dtcs: number;
  active_dtcs: number;
  resolved_dtcs: number;
  processing_rate: number;
  correlation_accuracy: number;
  prediction_accuracy: number;
  system_health_trend: "improving" | "stable" | "degrading";
  last_updated: string;
}

//
// ===== PERFORMANCE ANALYTICS TYPES =====
//

// Performance Metrics
export interface PerformanceMetrics {
  protocol_performance: Record<string, ProtocolPerformance>;
  api_performance: APIPerformance;
  websocket_performance: WebSocketPerformance;
  overall_health: number; // 0.0-1.0
  last_updated: string;
}

// Protocol Performance
export interface ProtocolPerformance {
  message_rate: number;
  decode_rate: number;
  error_rate: number;
  latency_ms: number;
  throughput_mbps: number;
  efficiency: number; // 0.0-1.0
}

// API Performance
export interface APIPerformance {
  average_response_time: number;
  requests_per_second: number;
  error_rate: number;
  success_rate: number; // 0.0-1.0
  slow_queries: number;
}

// WebSocket Performance
export interface WebSocketPerformance {
  message_rate: number;
  latency_ms: number;
  connection_stability: number; // 0.0-1.0
  active_connections: number;
  dropped_messages: number;
}

// Resource Usage
export interface ResourceUsage {
  cpu_usage: number; // 0.0-1.0
  memory_usage: number; // 0.0-1.0
  disk_usage: number; // 0.0-1.0
  network_usage: number; // bytes/sec
  can_interface_usage: Record<string, number>; // 0.0-1.0 per interface
  queue_lengths: Record<string, number>;
}

// Trend Data
export interface TrendData {
  metric_name: string;
  time_series: TimeSeriesPoint[];
  trend_direction: "up" | "down" | "stable";
  trend_strength: number; // 0.0-1.0
  prediction_confidence: number; // 0.0-1.0
}

// Time Series Point
export interface TimeSeriesPoint {
  timestamp: string;
  value: number;
  baseline_deviation: number;
}

// Optimization Suggestion
export interface OptimizationSuggestion {
  suggestion_id: string;
  category: "performance" | "reliability" | "efficiency" | "cost";
  title: string;
  description: string;
  impact_score: number; // 0.0-1.0
  implementation_effort: "low" | "medium" | "high";
  estimated_improvement: string;
  implementation_steps: string[];
  priority: "low" | "medium" | "high" | "critical";
}

// Baseline Deviation
export interface BaselineDeviation {
  metric_name: string;
  current_value: number;
  baseline_value: number;
  deviation_percent: number;
  severity: "low" | "medium" | "high" | "critical";
  threshold_breached: boolean;
  detected_at: string;
  trend: "improving" | "stable" | "degrading";
}

// Performance Analytics Statistics
export interface PerformanceAnalyticsStats {
  feature: Record<string, unknown>;
  telemetry: Record<string, unknown>;
  benchmarking: Record<string, unknown>;
  trends: Record<string, unknown>;
  optimization: Record<string, unknown>;
}

// Performance Report
export interface PerformanceReport {
  report_id: string;
  generated_at: string;
  time_window_seconds: number;
  summary: {
    overall_performance: number; // 0.0-1.0
    key_insights: string[];
    critical_issues: number;
    improvement_opportunities: number;
  };
  metrics: PerformanceMetrics;
  trends: TrendData[];
  baseline_deviations: BaselineDeviation[];
  optimization_recommendations: OptimizationSuggestion[];
  resource_utilization: ResourceUsage;
  protocol_throughput: Record<string, number>;
}

//
// ===== MULTI-PROTOCOL ENTITY TYPES =====
//

// J1939 Entity
export interface J1939Entity extends EntityBase {
  protocol: "j1939";
  system_type: "engine" | "transmission" | "chassis";
  manufacturer?: "cummins" | "allison" | "generic";
  engine_data?: {
    rpm?: number;
    coolant_temp?: number;
    oil_pressure?: number;
    fuel_rate?: number;
  };
}

// Firefly Entity
export interface FireflyEntity extends EntityBase {
  protocol: "firefly";
  multiplexed: boolean;
  safety_interlocks?: string[];
  zone_controls?: {
    scene_id?: string;
    fade_time?: number;
    zone_priority?: number;
  };
}

// Spartan K2 Entity
export interface SpartanK2Entity extends EntityBase {
  protocol: "spartan_k2";
  system_type: "brake" | "suspension" | "steering" | "electrical";
  safety_status: "safe" | "warning" | "critical";
  chassis_data?: {
    brake_pressure?: number;
    suspension_level?: number;
    steering_angle?: number;
  };
}

// Protocol Bridge Status
export interface ProtocolBridgeStatus {
  bridges_active: number;
  total_bridges: number;
  translation_rate: number;
  error_rate: number;
  health_score: number; // 0.0-1.0
  bridge_statuses: Record<string, BridgeStatus>;
}

// Individual Bridge Status
export interface BridgeStatus {
  from_protocol: string;
  to_protocol: string;
  active: boolean;
  translation_count: number;
  error_count: number;
  last_activity: string;
}

//
// ===== ENHANCED WEBSOCKET TYPES =====
//

// Diagnostic Update Message
export interface DiagnosticUpdateMessage extends WebSocketMessage {
  type: "diagnostic_update";
  data: {
    dtc_id?: string;
    health_score_change?: number;
    new_correlation?: FaultCorrelation;
    maintenance_alert?: MaintenanceAlert;
    system_health?: SystemHealthResponse;
  };
}

// Performance Update Message
export interface PerformanceUpdateMessage extends WebSocketMessage {
  type: "performance_update";
  data: {
    metric_name: string;
    current_value: number;
    baseline_deviation: number;
    trend: "improving" | "stable" | "degrading";
    resource_usage?: ResourceUsage;
  };
}

// Multi-Protocol Update Message
export interface MultiProtocolUpdateMessage extends WebSocketMessage {
  type: "multi_protocol_update";
  data: {
    protocol: string;
    entity_updates: EntityCollection;
    bridge_status?: ProtocolBridgeStatus;
    performance_metrics?: ProtocolPerformance;
  };
}

// Extended WebSocket Message Types
export type ExtendedWebSocketMessageType =
  | EntityUpdateMessage
  | CANMessageUpdate
  | SystemStatusMessage
  | DiagnosticUpdateMessage
  | PerformanceUpdateMessage
  | MultiProtocolUpdateMessage
  | WebSocketMessage;

//
// ===== CONFIGURATION MANAGEMENT TYPES =====
//

// System Settings Overview
export interface SystemSettings {
  sections: {
    server?: ServerSettingsSection;
    security?: SecuritySettingsSection;
    logging?: LoggingSettingsSection;
    can?: CANSettingsSection;
    rvc?: RVCSettingsSection;
    persistence?: PersistenceSettingsSection;
    notifications?: NotificationSettingsSection;
    auth?: AuthSettingsSection;
  };
  metadata: {
    environment: string;
    debug: boolean;
    version: string;
    app_name: string;
    source_priority: string[];
  };
  environment_variables: Record<string, string>;
  config_sources: {
    env_file?: string | null;
    system_env: boolean;
    defaults: boolean;
  };
}

// Server Configuration Section
export interface ServerSettingsSection {
  host: string;
  port: number;
  workers: number;
  reload: boolean;
  debug: boolean;
  root_path: string;
}

// Security Configuration Section
export interface SecuritySettingsSection {
  allowed_hosts: string[];
  enable_csrf: boolean;
  enable_xss_protection: boolean;
  enable_content_security_policy: boolean;
  max_upload_size: number;
  rate_limit_enabled: boolean;
  rate_limit_requests: number;
  rate_limit_window: number;
}

// Logging Configuration Section
export interface LoggingSettingsSection {
  level: string;
  format: string;
  file_enabled: boolean;
  file_path: string | null;
  max_file_size: number;
  backup_count: number;
  console_enabled: boolean;
}

// CAN Configuration Section
export interface CANSettingsSection {
  interfaces: string[];
  bitrate: number;
  timeout: number;
  buffer_size: number;
  enable_statistics: boolean;
  enable_error_frames: boolean;
  enable_fd: boolean;
  fd_bitrate: number;
}

// RVC Configuration Section
export interface RVCSettingsSection {
  enable_encoder: boolean;
  enable_decoder: boolean;
  spec_file: string;
  message_timeout: number;
  enable_caching: boolean;
  cache_ttl: number;
  enable_validation: boolean;
  strict_validation: boolean;
}

// Persistence Configuration Section
export interface PersistenceSettingsSection {
  enabled: boolean;
  backend_type: string;
  data_dir: string;
  persistent_data_dir: string;
  enable_compression: boolean;
  sync_interval: number;
  max_file_size: number;
  retention_days: number;
}

// Notifications Configuration Section
export interface NotificationSettingsSection {
  enabled: boolean;
  max_history: number;
  default_severity: string;
  batch_interval: number;
  rate_limit_per_minute: number;
}

// Auth Configuration Section
export interface AuthSettingsSection {
  enabled: boolean;
  provider: string;
  session_timeout: number;
  refresh_enabled: boolean;
  refresh_timeout: number;
  max_sessions: number;
  require_email_verification: boolean;
}

// Database Configuration
export interface DatabaseConfiguration {
  backend: string;
  sqlite: {
    path: string;
    timeout: number;
    optimizations_enabled: boolean;
    cache_size: number;
    mmap_size: number;
    wal_autocheckpoint: number;
  };
  postgresql: {
    host: string;
    port: number;
    user: string;
    database: string;
    schema: string;
  };
  pool: {
    size: number;
    max_overflow: number;
    timeout: number;
    recycle: number;
  };
  performance: {
    echo_sql: boolean;
    echo_pool: boolean;
  };
  health_status: string;
}

// Legacy Server Configuration (for backward compatibility)
export interface ServerSettings {
  host: string;
  port: number;
  ssl_enabled: boolean;
  ssl_cert_path?: string;
  ssl_key_path?: string;
  workers: number;
  max_connections: number;
  keepalive_timeout: number;
  debug_mode: boolean;
}

// CAN Bus Configuration
export interface CANSettings {
  interfaces: Record<string, string>; // logical_name -> physical_interface
  default_bitrate: number;
  buffer_size: number;
  receive_timeout: number;
  error_handling: "strict" | "lenient" | "ignore";
  interface_validation: boolean;
}

// CORS Configuration
export interface CORSSettings {
  allow_origins: string[];
  allow_methods: string[];
  allow_headers: string[];
  allow_credentials: boolean;
  max_age: number;
}

// Security Configuration
export interface SecuritySettings {
  api_key_required: boolean;
  api_keys: string[];
  rate_limiting_enabled: boolean;
  rate_limit_requests_per_minute: number;
  allowed_ips: string[];
  require_https: boolean;
}

// Logging Configuration
export interface LoggingSettings {
  level: "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL";
  format: string;
  file_enabled: boolean;
  file_path?: string;
  file_rotation: boolean;
  file_max_size_mb: number;
  file_backup_count: number;
  console_enabled: boolean;
  structured_logging: boolean;
}

// RV-C Protocol Configuration
export interface RVCSettings {
  spec_file_path: string;
  coach_mapping_file: string;
  coach_model_detection: boolean;
  custom_dgn_ranges: number[][];
  performance_tuning: {
    decode_timeout_ms: number;
    cache_size: number;
    parallel_processing: boolean;
  };
}

// J1939 Protocol Configuration
export interface J1939Settings {
  enabled: boolean;
  manufacturer_extensions: {
    cummins_enabled: boolean;
    allison_enabled: boolean;
  };
  chassis_support: {
    spartan_k2_enabled: boolean;
  };
  address_range: {
    min: number;
    max: number;
  };
  priority_pgns: number[];
}

// Firefly Configuration
export interface FireflySettings {
  enabled: boolean;
  zone_controls_enabled: boolean;
  scene_management: boolean;
  safety_interlocks: boolean;
  multiplexing_support: boolean;
  fade_time_default_ms: number;
}

// Spartan K2 Configuration
export interface SpartanK2Settings {
  enabled: boolean;
  safety_validation: boolean;
  brake_system_monitoring: boolean;
  suspension_control: boolean;
  steering_monitoring: boolean;
  safety_thresholds: {
    brake_pressure_min: number;
    brake_pressure_max: number;
    steering_angle_max: number;
  };
}

// Multi-Network Configuration
export interface MultiNetworkSettings {
  enabled: boolean;
  bridge_protocols: string[];
  isolation_enabled: boolean;
  fault_containment: boolean;
  health_monitoring_interval_ms: number;
  bridge_timeout_ms: number;
}

// Persistence Configuration
export interface PersistenceSettings {
  enabled: boolean;
  backend_type: "memory" | "sqlite" | "postgresql";
  backup_enabled: boolean;
  backup_interval_hours: number;
  retention_days: number;
  compression_enabled: boolean;
}

// Advanced Diagnostics Configuration
export interface AdvancedDiagnosticsSettings {
  enabled: boolean;
  health_score_calculation: boolean;
  fault_correlation: boolean;
  predictive_maintenance: boolean;
  correlation_confidence_threshold: number;
  health_update_interval_ms: number;
  maintenance_prediction_horizon_days: number;
}

// Performance Analytics Configuration
export interface PerformanceAnalyticsSettings {
  enabled: boolean;
  metrics_collection: boolean;
  baseline_calculation: boolean;
  optimization_recommendations: boolean;
  telemetry_interval_ms: number;
  baseline_window_hours: number;
  deviation_threshold_percent: number;
}

// Feature Flag with Dependencies
export interface FeatureFlag {
  name: string;
  enabled: boolean;
  description: string;
  dependencies: string[];
  dependent_features: string[];
  category: "core" | "protocol" | "advanced" | "experimental";
  stability: "stable" | "beta" | "alpha";
  environment_restrictions?: string[];
}

// Feature Management Response
export interface FeatureManagementResponse {
  features: Record<string, FeatureFlag>;
  dependency_graph: Record<string, string[]>;
  conflict_resolution: Record<string, string>;
  validation_errors: string[];
}

// CAN Interface Mapping
export interface CANInterfaceMapping {
  logical_name: string;
  physical_interface: string;
  bitrate: number;
  is_active: boolean;
  last_activity?: string;
  message_count: number;
  error_count: number;
  validation_status: "valid" | "invalid" | "warning";
  validation_message?: string;
}

// Coach Configuration Metadata
export interface CoachConfiguration {
  model: string;
  year: number;
  manufacturer: string;
  config_file: string;
  interface_requirements: string[];
  device_mappings: Record<string, unknown>;
  validation_status: "valid" | "invalid" | "warning";
  last_validated: string;
}

// Configuration Validation Result
export interface ConfigurationValidation {
  valid: boolean;
  errors: string[];
  warnings: string[];
  suggestions: string[];
  affected_features: string[];
}

// Configuration Update Request
export interface ConfigurationUpdateRequest {
  section: string;
  key: string;
  value: unknown;
  persist: boolean;
  validate_before_apply: boolean;
}

// Configuration Update Response
export interface ConfigurationUpdateResponse {
  success: boolean;
  message: string;
  previous_value?: unknown;
  validation_result?: ConfigurationValidation;
  restart_required: boolean;
  affected_services: string[];
}

// System Status for Configuration
export interface ConfigurationSystemStatus {
  server_status: "running" | "starting" | "stopping" | "error";
  can_interfaces_status: Record<string, "active" | "inactive" | "error">;
  feature_status: Record<string, "enabled" | "disabled" | "error">;
  protocol_status: Record<string, "active" | "inactive" | "error">;
  validation_status: "valid" | "invalid" | "warning";
  last_config_change: string;
  pending_restarts: string[];
}

// Performance Analytics Types (missing from previous implementations)
export interface BaselineDeviation {
  metric_name: string;
  current_value: number;
  baseline_value: number;
  deviation_percent: number;
  trend: "improving" | "stable" | "degrading";
  severity: "low" | "medium" | "high" | "critical";
  timestamp: string;
}


export interface PerformanceAnalyticsStats {
  total_metrics_collected: number;
  active_monitoring_interval_ms: number;
  baseline_calculation_status: "active" | "inactive" | "error";
  last_optimization_run: string;
  metrics_retention_days: number;
  telemetry_endpoints_active: number;
}

// Device Discovery Types
export interface DeviceInfo {
  source_address: number;
  protocol: string;
  device_type?: string;
  status: "discovered" | "online" | "offline" | "error";
  last_seen: number;
  first_seen: number;
  response_count: number;
  capabilities: string[];
}

export interface NetworkTopology {
  devices: Record<string, DeviceInfo[]>;
  total_devices: number;
  online_devices: number;
  health_score: number;
  last_discovery: number;
  active_polls: number;
  discovery_active: boolean;
}

export interface DeviceAvailability {
  total_devices: number;
  online_devices: number;
  offline_devices: number;
  recent_devices: number;
  protocols: Record<string, number>;
  device_types: Record<string, number>;
}

export interface DiscoverDevicesRequest {
  protocol: string;
}

export interface DiscoverDevicesResponse {
  protocol: string;
  devices_found: number;
  devices: Record<string, DeviceInfo>;
}

export interface PollDeviceRequest {
  source_address: number;
  pgn: number;
  protocol?: string;
  instance?: number;
}

export interface PollDeviceResponse {
  success: boolean;
  message: string;
  request: PollDeviceRequest;
}

export interface DeviceDiscoveryStatus {
  enabled: boolean;
  feature_info: {
    name: string;
    friendly_name: string;
    description: string;
    enabled: boolean;
    version: string;
    runtime_info?: {
      discovery_active: boolean;
      total_devices: number;
      supported_protocols: string[];
      polling_interval: number;
      discovery_interval: number;
    };
  };
  health: {
    status: "healthy" | "warning" | "error" | "disabled";
    message: string;
    metrics?: {
      discovery_active: boolean;
      total_devices: number;
      online_devices: number;
      active_polls: number;
      last_discovery: number;
    };
  };
  service_status: string;
}

export interface SupportedProtocols {
  supported_protocols: string[];
  discovery_pgns: Record<string, number[]>;
  status_pgns: Record<string, number>;
  configuration: {
    polling_interval: number;
    discovery_interval: number;
    poll_timeout: number;
    max_retries: number;
  };
}

//
// ===== AUTHENTICATION TYPES =====
//

export interface User {
  user_id: string;
  username: string | null;
  email: string | null;
  role: 'admin' | 'user' | 'readonly';
  mode: 'none' | 'single' | 'multi';
  authenticated: boolean;
}

export interface AuthStatus {
  enabled: boolean;
  mode: 'none' | 'single' | 'multi';
  jwt_available: boolean;
  magic_links_enabled: boolean;
  oauth_enabled: boolean;
}

export interface LoginCredentials {
  username: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  refresh_expires_in: number;
  mfa_required?: boolean;
  user_id?: string;
}

export interface RefreshTokenRequest {
  refresh_token: string;
}

export interface MFAStatus {
  user_id: string;
  mfa_enabled: boolean;
  setup_initiated: boolean;
  created_at?: string;
  last_used?: string;
  backup_codes_remaining: number;
  backup_codes_total: number;
  available: boolean;
}

export interface MFASetupResponse {
  secret: string;
  qr_code: string;
  provisioning_uri: string;
  backup_codes: string[];
  issuer: string;
}

export interface MFAVerificationRequest {
  totp_code: string;
}

export interface BackupCodesResponse {
  backup_codes: string[];
  warning: string;
}

export interface RefreshTokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  refresh_expires_in: number;
}

export interface MagicLinkRequest {
  email: string;
  redirect_url?: string;
}

export interface MagicLinkResponse {
  message: string;
  email: string;
  expires_in_minutes: number;
}

export interface AdminCredentials {
  username: string;
  password: string;
  created_at: string;
  warning: string;
}

export interface LogoutResponse {
  message: string;
  detail: string;
}

export interface AccountLockoutError {
  error: "account_locked";
  message: string;
  lockout_until: string;
  failed_attempts: number;
}

export interface LockoutStatus {
  username: string;
  is_locked: boolean;
  lockout_until: string | null;
  failed_attempts: number;
  escalation_level: number;
  last_attempt: string | null;
  consecutive_successful_logins: number;
  lockout_enabled: boolean;
  max_failed_attempts: number;
  lockout_duration_minutes: number;
}

export interface UnlockAccountRequest {
  username: string;
}

//
// ===== BULK OPERATIONS TYPES =====
//

export interface BulkOperationPayload {
  command: string;
  state?: "on" | "off";
  brightness?: number;
  value?: string | number | boolean;
  unit?: string;
}

export interface BulkOperationRequest {
  operation_type: string;
  targets: string[];
  payload: BulkOperationPayload;
  description?: string;
}

export interface BulkOperationResponse {
  status: string;
  operation_id: string;
  total_tasks: number;
  queued_at: string;
}

export interface BulkOperationStatus {
  operation_id: string;
  status: string;
  operation_type: string;
  description?: string;
  total_tasks: number;
  success_count: number;
  failure_count: number;
  progress_percentage: number;
  failed_devices: {
    device_id: string;
    error: string;
    timestamp: string;
  }[];
  created_at: string;
  updated_at: string;
}

export interface DeviceGroupRequest {
  name: string;
  description?: string;
  device_ids: string[];
  exemptions?: Record<string, string | number | boolean | string[]>;
}

export interface DeviceGroup {
  id: string;
  name: string;
  description?: string;
  device_ids: string[];
  exemptions?: Record<string, string | number | boolean | string[]>;
  created_at: string;
  updated_at: string;
}

//
// ===== PREDICTIVE MAINTENANCE TYPES =====
//

export interface ComponentHealth {
  component_id: string;
  component_type: string;
  component_name: string;
  health_score: number;
  status: "healthy" | "watch" | "advise" | "alert";
  remaining_useful_life_days?: number;
  last_maintenance?: string;
  next_maintenance_due?: string;
  usage_hours?: number;
  usage_cycles?: number;
  anomaly_count: number;
  trend_direction: "improving" | "stable" | "degrading";
  created_at: string;
  updated_at: string;
}

export interface RVHealthOverview {
  overall_health_score: number;
  status: "healthy" | "watch" | "advise" | "alert";
  critical_alerts: number;
  active_recommendations: number;
  components_monitored: number;
  last_updated: string;
  system_health_breakdown: Record<string, number>;
}

export interface MaintenanceRecommendation {
  recommendation_id: string;
  component_id: string;
  component_name: string;
  level: "watch" | "advise" | "alert";
  title: string;
  message: string;
  priority: number;
  estimated_cost?: number;
  estimated_time_hours?: number;
  urgency_days?: number;
  created_at: string;
  acknowledged_at?: string;
  dismissed: boolean;
  maintenance_type: "inspection" | "service" | "replacement";
}

export interface ComponentTrendData {
  component_id: string;
  metric_name: string;
  trend_points: {
    timestamp: string;
    value: number;
    metric: string;
  }[];
  normal_range: {
    min: number;
    max: number;
    metric: string;
  };
  anomalies: {
    timestamp: string;
    value: number;
    severity: "medium" | "high";
    description: string;
  }[];
  prediction_confidence: number;
  trend_analysis: string;
}

export interface MaintenanceLogEntry {
  component_id: string;
  maintenance_type: string;
  description: string;
  cost?: number;
  performed_by?: string;
  location?: string;
  notes?: string;
}

export interface MaintenanceHistory {
  entry_id: string;
  component_id: string;
  component_name: string;
  maintenance_type: string;
  description: string;
  performed_at: string;
  cost?: number;
  performed_by?: string;
  location?: string;
  notes?: string;
}

//
// ===== ENHANCED DEVICE DISCOVERY TYPES =====
//

export interface DiscoveredDevice {
  address: number;
  protocol: string;
  device_type?: string;
  manufacturer?: string;
  product_id?: string;
  version?: string;
  capabilities: string[];
  last_seen: number;
  first_seen: number;
  response_count: number;
  response_times: number[];
  status: "discovered" | "online" | "offline" | "error";
}

export interface DeviceProfile {
  device_address: number;
  protocol: string;
  basic_info: {
    source_address: number;
    device_type: string;
    manufacturer: string;
    product_id: string;
    version: string;
    status: string;
    last_seen: number;
    first_seen: number;
    response_count: number;
  };
  capabilities: {
    detected: string[];
    inferred: string[];
    pgns_supported: number[];
  };
  setup_guidance: string[];
  configuration_options: Record<string, string | number | boolean>;
  recommended_name: string;
  recommended_area: string;
  health_metrics: {
    response_rate: number;
    average_response_time: number;
    reliability_score: number;
  };
}

export interface AutoDiscoveryRequest {
  protocols: string[];
  scan_duration_seconds: number;
  deep_scan: boolean;
  save_results: boolean;
}

export interface AutoDiscoveryResults {
  scan_id: string;
  protocols_scanned: string[];
  scan_duration: number;
  deep_scan: boolean;
  total_devices: number;
  devices_by_protocol: Record<string, number>;
  device_profiles: Record<string, DeviceProfile>;
  setup_recommendations: DeviceRecommendation[];
  network_topology: NetworkTopologyData;
  scan_summary: {
    status: string;
    devices_found: number;
    profiles_generated: number;
    recommendations: number;
    scan_completed_at: number;
  };
}

export interface DeviceRecommendation {
  device_address: number;
  protocol: string;
  current_status: string;
  device_type: string;
  recommended_name: string;
  recommended_area: string;
  priority: "low" | "medium" | "high";
  setup_complexity: "simple" | "moderate" | "complex";
  estimated_time_minutes: number;
}

export interface SetupRecommendations {
  total_devices: number;
  unconfigured_devices: number;
  recommendations: DeviceRecommendation[];
  priority_actions: PriorityAction[];
  device_groupings: DeviceGrouping[];
  area_suggestions: Record<string, number[]>;
  generated_at: number;
  message?: string;
}

export interface PriorityAction {
  action: string;
  device_type: string;
  device_count: number;
  message: string;
  priority: "low" | "medium" | "high";
  time_saved: string;
}

export interface DeviceGrouping {
  group_type: string;
  group_name: string;
  device_addresses: number[];
  suggested_operations: string[];
}

export interface NetworkTopologyData {
  protocols: string[];
  device_count_by_protocol: Record<string, number>;
  total_devices: number;
  network_segments: NetworkSegment[];
  device_density: Record<string, number>;
}

export interface NetworkSegment {
  protocol: string;
  address_range: {
    min: number;
    max: number;
  };
  device_count: number;
}

export interface EnhancedNetworkMap {
  total_devices: number;
  online_devices: number;
  offline_devices: number;
  device_groups: Record<string, DiscoveredDevice[]>;
  protocol_distribution: Record<string, number>;
  device_relationships: DeviceRelationship[];
  network_health: {
    score: number;
    status: "healthy" | "degraded" | "poor" | "no_devices";
    online_percentage: number;
    responsive_percentage: number;
  };
  topology_metrics: {
    protocol_diversity: number;
    device_type_diversity: number;
    average_response_count: number;
    newest_device_age: number;
    oldest_device_age: number;
  };
  last_updated: number;
}

export interface DeviceRelationship {
  relationship_type: string;
  device_type: string;
  devices: number[];
  strength: "low" | "medium" | "high";
  description: string;
}

export interface DeviceSetupRequest {
  device_address: number;
  device_name: string;
  device_type: string;
  area: string;
  capabilities: string[];
  configuration: Record<string, string | number | boolean>;
}

export interface DeviceSetupResult {
  device_address: number;
  device_name: string;
  device_type: string;
  area: string;
  setup_status: "success" | "validation_failed" | "error";
  entity_id: string;
  capabilities_configured: string[];
  configuration_applied: Record<string, string | number | boolean>;
  setup_timestamp: number;
  validation_results: {
    valid: boolean;
    errors: string[];
    warnings: string[];
    recommendations: string[];
  };
  next_steps: string[];
  entity_config?: Record<string, string | number | boolean>;
  errors?: string[];
  error?: string;
}
