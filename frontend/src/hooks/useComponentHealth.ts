import { useQuery } from '@tanstack/react-query';
import { apiGet } from '@/api/client';

interface ComponentHealth {
  id: string;
  name: string;
  status: 'healthy' | 'degraded' | 'unhealthy' | 'unknown';
  message?: string;
  category: 'core' | 'network' | 'storage' | 'external';
  last_checked: number;
  safety_classification?: string;
}

interface ComponentHealthResponse {
  components: ComponentHealth[];
  total_components: number;
  healthy_components: number;
  degraded_components: number;
  unhealthy_components: number;
  timestamp: number;
}

export function useComponentHealth() {
  return useQuery({
    queryKey: ['componentHealth'],
    queryFn: async () => {
      return await apiGet<ComponentHealthResponse>('/api/v2/system/components/health');
    },
    refetchInterval: 30000, // Refresh every 30 seconds
    staleTime: 25000,
  });
}
