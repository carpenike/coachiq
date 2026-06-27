/**
 * Domain API Clients
 *
 * This module exports domain-specific API clients that match the backend
 * domain-driven architecture. Each domain provides enhanced capabilities
 * over the legacy monolithic API.
 */

// Entities Domain (includes both regular and validation-enhanced functions)
export * from './entities';

// Diagnostics Domain
export * from './diagnostics';

// Future domains (placeholders for Phase 3+)
// export * from './analytics';

//
// ===== DOMAIN FEATURE DETECTION =====
//

/**
 * Check if a domain API is available by testing the health endpoint
 *
 * @param domain - Domain name (e.g., 'entities', 'diagnostics', 'analytics')
 * @returns Promise resolving to availability status
 */
export async function isDomainAPIAvailable(domain: string): Promise<boolean> {
  try {
    const response = await fetch(`/api/v2/${domain}/health`);
    return response.ok;
  } catch {
    return false;
  }
}

/**
 * Get the status of all available domain APIs
 *
 * @returns Promise resolving to domain availability map
 */
export async function getDomainAPIStatus(): Promise<Record<string, boolean>> {
  const domains = ['entities', 'diagnostics', 'analytics'];
  const statusChecks = domains.map(async (domain) => ({
    [domain]: await isDomainAPIAvailable(domain),
  }));

  const results = await Promise.all(statusChecks);
  return Object.assign({}, ...results);
}
