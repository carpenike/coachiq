/**
 * CAN Message Filter API Client
 *
 * API client for CAN message filtering functionality.
 */

import { apiGet, apiPost, apiPut, apiDelete } from './client';

// Types
export enum FilterOperator {
  EQUALS = "equals",
  NOT_EQUALS = "not_equals",
  GREATER_THAN = "greater_than",
  LESS_THAN = "less_than",
  GREATER_EQUAL = "greater_equal",
  LESS_EQUAL = "less_equal",
  IN = "in",
  NOT_IN = "not_in",
  CONTAINS = "contains",
  NOT_CONTAINS = "not_contains",
  MATCHES = "matches",
  WILDCARD = "wildcard",
}

export enum FilterField {
  CAN_ID = "can_id",
  PGN = "pgn",
  SOURCE_ADDRESS = "source_address",
  DESTINATION_ADDRESS = "destination_address",
  DATA = "data",
  DATA_LENGTH = "data_length",
  INTERFACE = "interface",
  PROTOCOL = "protocol",
  MESSAGE_TYPE = "message_type",
  DECODED_FIELD = "decoded_field",
}

export enum FilterAction {
  PASS = "pass",
  BLOCK = "block",
  LOG = "log",
  ALERT = "alert",
  CAPTURE = "capture",
  FORWARD = "forward",
  MODIFY = "modify",
}

export interface FilterCondition {
  field: FilterField;
  operator: FilterOperator;
  value: any;
  case_sensitive?: boolean;
  negate?: boolean;
}

export interface FilterRule {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  priority: number;
  conditions: FilterCondition[];
  condition_logic: "AND" | "OR";
  actions: {
    action: FilterAction;
    [key: string]: any;
  }[];
  statistics: {
    matches: number;
    last_match: number;
  };
}

export interface FilterStatistics {
  messages_processed: number;
  messages_passed: number;
  messages_blocked: number;
  messages_captured: number;
  alerts_sent: number;
  processing_time_ms: number;
  active_rules: number;
  total_rules: number;
  capture_buffer_size: number;
  rules: {
    id: string;
    name: string;
    enabled: boolean;
    priority: number;
    matches: number;
    last_match: number;
  }[];
}

export interface CapturedMessage {
  timestamp: number;
  can_id: string;
  data: string;
  interface: string;
  protocol?: string;
  message_type?: string;
  decoded?: Record<string, any>;
}

export interface FilterStatus {
  enabled: boolean;
  healthy: boolean;
  total_rules: number;
  active_rules: number;
  statistics: FilterStatistics;
}

// API Functions
export async function getFilterStatus(): Promise<FilterStatus> {
  return apiGet<FilterStatus>('/api/can-filter/status');
}

export async function listFilterRules(enabled_only = false): Promise<FilterRule[]> {
  const params = enabled_only ? '?enabled_only=true' : '';
  return apiGet<FilterRule[]>(`/api/can-filter/rules${params}`);
}

export async function getFilterRule(ruleId: string): Promise<FilterRule> {
  return apiGet<FilterRule>(`/api/can-filter/rules/${ruleId}`);
}

export async function createFilterRule(rule: Omit<FilterRule, 'id' | 'statistics'>): Promise<FilterRule> {
  return apiPost<FilterRule>('/api/can-filter/rules', rule);
}

export async function updateFilterRule(
  ruleId: string,
  updates: Partial<Omit<FilterRule, 'id' | 'statistics'>>
): Promise<FilterRule> {
  return apiPut<FilterRule>(`/api/can-filter/rules/${ruleId}`, updates);
}

export async function deleteFilterRule(ruleId: string): Promise<{ status: string; rule_id: string }> {
  return apiDelete<{ status: string; rule_id: string }>(`/api/can-filter/rules/${ruleId}`);
}

export async function getFilterStatistics(): Promise<FilterStatistics> {
  return apiGet<FilterStatistics>('/api/can-filter/statistics');
}

export async function resetFilterStatistics(): Promise<{ status: string }> {
  return apiPost<{ status: string }>('/api/can-filter/statistics/reset', {});
}

export async function getCapturedMessages(
  limit?: number,
  since_timestamp?: number
): Promise<CapturedMessage[]> {
  const params = new URLSearchParams();
  if (limit) params.append('limit', limit.toString());
  if (since_timestamp) params.append('since_timestamp', since_timestamp.toString());

  return apiGet<CapturedMessage[]>(`/api/can-filter/capture?${params}`);
}

export async function clearCaptureBuffer(): Promise<{ status: string }> {
  return apiDelete<{ status: string }>('/api/can-filter/capture');
}

export async function exportFilterRules(): Promise<{ rules: string; count: number }> {
  return apiGet<{ rules: string; count: number }>('/api/can-filter/export');
}

export async function importFilterRules(rulesJson: string): Promise<{ status: string; imported: number }> {
  return apiPost<{ status: string; imported: number }>('/api/can-filter/import', {
    rules: rulesJson,
  });
}
