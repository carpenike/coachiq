import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/api/client';

interface EventLogEntry {
  id: string;
  timestamp: number;
  level: 'debug' | 'info' | 'warning' | 'error' | 'critical';
  component: string;
  message: string;
  details?: Record<string, any>;
}

interface EventLogResponse {
  events: EventLogEntry[];
  total_events: number;
  timestamp: number;
}

interface EventLogFilter {
  limit?: number;
  level?: string;
  component?: string;
  start_time?: number;
  end_time?: number;
}

export function useEventLogs(filter?: EventLogFilter) {
  const queryParams = new URLSearchParams();

  if (filter?.limit) queryParams.append('limit', filter.limit.toString());
  if (filter?.level) queryParams.append('level', filter.level);
  if (filter?.component) queryParams.append('component', filter.component);
  if (filter?.start_time) queryParams.append('start_time', filter.start_time.toString());
  if (filter?.end_time) queryParams.append('end_time', filter.end_time.toString());

  const queryString = queryParams.toString();
  const url = `/api/v2/system/events${queryString ? `?${queryString}` : ''}`;

  return useQuery({
    queryKey: ['eventLogs', filter],
    queryFn: async () => {
      return await apiGet<EventLogResponse>(url);
    },
    refetchInterval: 5000, // Refresh every 5 seconds for real-time updates
    staleTime: 4000,
  });
}
