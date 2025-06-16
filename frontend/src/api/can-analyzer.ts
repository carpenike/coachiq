/**
 * CAN Protocol Analyzer API Client
 *
 * API client for CAN protocol analysis functionality.
 */

import { apiGet, apiPost, apiDelete } from './client';

// Types
export interface DecodedField {
  name: string;
  value: any;
  unit?: string;
  raw_value?: number;
  scale: number;
  offset: number;
  min_value?: number;
  max_value?: number;
  valid: boolean;
}

export interface AnalyzedMessage {
  timestamp: number;
  can_id: string;
  data: string;
  interface: string;
  protocol: string;
  message_type: string;
  source_address?: number;
  destination_address?: number;
  pgn?: string;
  function_code?: number;
  decoded_fields: DecodedField[];
  description?: string;
  warnings: string[];
}

export interface CommunicationPattern {
  pattern_type: string;
  participants: string[];
  interval_ms?: number;
  confidence: number;
}

export interface ProtocolStatistics {
  runtime_seconds: number;
  total_messages: number;
  total_bytes: number;
  overall_message_rate: number;
  bus_utilization_percent: number;
  protocols: Record<string, {
    message_count: number;
    byte_count: number;
    error_count: number;
    unique_ids: number;
    message_types: Record<string, number>;
    percentage: number;
  }>;
  detected_patterns: number;
  buffer_usage: number;
  buffer_capacity: number;
}

export interface ProtocolReport {
  detected_protocols: Record<string, {
    can_ids: string[];
    count: number;
    confidence: string;
  }>;
  communication_patterns: {
    type: string;
    participants: string[];
    interval_ms?: number;
    confidence: number;
  }[];
  protocol_compliance: Record<string, {
    error_rate: number;
    issues: string[];
  }>;
  recommendations: string[];
}

export interface LiveAnalysis {
  messages: AnalyzedMessage[];
  patterns: CommunicationPattern[];
  statistics: ProtocolStatistics;
}

// API Functions
export async function getStatistics(): Promise<ProtocolStatistics> {
  return apiGet<ProtocolStatistics>('/api/can-analyzer/statistics');
}

export async function getProtocolReport(): Promise<ProtocolReport> {
  return apiGet<ProtocolReport>('/api/can-analyzer/report');
}

export async function getRecentMessages(params: {
  limit?: number;
  protocol?: string;
  message_type?: string;
  can_id?: string;
}): Promise<AnalyzedMessage[]> {
  const queryParams = new URLSearchParams();
  if (params.limit) queryParams.append('limit', params.limit.toString());
  if (params.protocol) queryParams.append('protocol', params.protocol);
  if (params.message_type) queryParams.append('message_type', params.message_type);
  if (params.can_id) queryParams.append('can_id', params.can_id);

  return apiGet<AnalyzedMessage[]>(`/api/can-analyzer/messages?${queryParams}`);
}

export async function getCommunicationPatterns(pattern_type?: string): Promise<CommunicationPattern[]> {
  const queryParams = pattern_type ? `?pattern_type=${pattern_type}` : '';
  return apiGet<CommunicationPattern[]>(`/api/can-analyzer/patterns${queryParams}`);
}

export async function getDetectedProtocols(): Promise<Record<string, string[]>> {
  return apiGet<Record<string, string[]>>('/api/can-analyzer/protocols');
}

export async function analyzeMessage(params: {
  can_id: string;
  data: string;
  interface?: string;
}): Promise<AnalyzedMessage> {
  const queryParams = new URLSearchParams({
    can_id: params.can_id,
    data: params.data,
    interface: params.interface || 'can0',
  });

  return apiPost<AnalyzedMessage>(`/api/can-analyzer/analyze?${queryParams}`, {});
}

export async function getLiveAnalysis(duration_seconds = 5): Promise<LiveAnalysis> {
  return apiGet<LiveAnalysis>(`/api/can-analyzer/live?duration_seconds=${duration_seconds}`);
}

export async function clearAnalyzer(): Promise<{ status: string; timestamp: string }> {
  return apiDelete<{ status: string; timestamp: string }>('/api/can-analyzer/clear');
}
