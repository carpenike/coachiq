/**
 * CAN Bus Recorder API Client
 *
 * API client for CAN bus recording and replay functionality.
 */

import { apiGet, apiPost, apiDelete } from './client';

// Types
export interface RecordingFilters {
  can_ids?: number[];
  interfaces?: string[];
  pgns?: number[];
}

export interface StartRecordingRequest {
  name: string;
  description?: string;
  format?: 'json' | 'csv' | 'binary' | 'candump';
  filters?: RecordingFilters;
}

export interface RecordingSession {
  session_id: string;
  name: string;
  description: string;
  start_time: string;
  end_time?: string;
  message_count: number;
  interfaces: string[];
  filters: Record<string, any>;
  format: string;
  file_path?: string;
}

export interface RecorderStatus {
  state: string;
  current_session?: RecordingSession;
  buffer_size: number;
  buffer_capacity: number;
  messages_recorded: number;
  messages_dropped: number;
  bytes_recorded: number;
  filters: Record<string, any>;
}

export interface RecordingFile {
  filename: string;
  path: string;
  size_bytes: number;
  size_mb: number;
  modified: string;
  format: string;
}

export interface ReplayOptions {
  speed_factor?: number;
  loop?: boolean;
  start_offset?: number;
  end_offset?: number;
  interface_mapping?: Record<string, string>;
  filter_can_ids?: number[];
}

export interface StartReplayRequest {
  filename: string;
  options?: ReplayOptions;
}

// API Functions
export async function getRecorderStatus(): Promise<RecorderStatus> {
  return apiGet<RecorderStatus>('/api/can-recorder/status');
}

export async function startRecording(request: StartRecordingRequest): Promise<RecordingSession> {
  return apiPost<RecordingSession>('/api/can-recorder/start', request);
}

export async function stopRecording(): Promise<RecordingSession | null> {
  return apiPost<RecordingSession | null>('/api/can-recorder/stop', {});
}

export async function pauseRecording(): Promise<{ status: string }> {
  return apiPost<{ status: string }>('/api/can-recorder/pause', {});
}

export async function resumeRecording(): Promise<{ status: string }> {
  return apiPost<{ status: string }>('/api/can-recorder/resume', {});
}

export async function listRecordings(): Promise<RecordingFile[]> {
  return apiGet<RecordingFile[]>('/api/can-recorder/list');
}

export async function deleteRecording(filename: string): Promise<{ status: string; filename: string }> {
  return apiDelete<{ status: string; filename: string }>(`/api/can-recorder/${filename}`);
}

export async function startReplay(request: StartReplayRequest): Promise<{ status: string; filename: string }> {
  return apiPost<{ status: string; filename: string }>('/api/can-recorder/replay/start', request);
}

export async function stopReplay(): Promise<{ status: string }> {
  return apiPost<{ status: string }>('/api/can-recorder/replay/stop', {});
}

export async function uploadRecording(file: File): Promise<{ status: string; filename: string; size_bytes: number }> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch('/api/can-recorder/upload', {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    throw new Error(`Upload failed: ${response.statusText}`);
  }

  return response.json();
}

export function getDownloadUrl(filename: string): string {
  return `/api/can-recorder/download/${filename}`;
}
