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

//
// ===== DOMAIN API MIGRATION HELPERS =====
//

/**
 * Options for progressive migration from legacy to domain APIs
 */
export interface MigrationOptions {
  /** Prefer domain API over legacy when available */
  preferDomainAPI?: boolean;
  /** Fallback to legacy API if domain API fails */
  fallbackToLegacy?: boolean;
  /** Log migration attempts for monitoring */
  logMigration?: boolean;
}

/**
 * Default migration options for progressive rollout
 */
export const defaultMigrationOptions: MigrationOptions = {
  preferDomainAPI: true,
  fallbackToLegacy: true,
  logMigration: true,
};

/**
 * Execute a function with domain API preference and legacy fallback
 *
 * @param domainFn - Function using domain API
 * @param legacyFn - Function using legacy API
 * @param options - Migration options
 * @returns Promise resolving to the result from either API
 */
export async function withDomainAPIFallback<T>(
  domainFn: () => Promise<T>,
  legacyFn: () => Promise<T>,
  options: MigrationOptions = defaultMigrationOptions
): Promise<T> {
  if (options.preferDomainAPI) {
    try {
      if (options.logMigration) {
        console.log('🚀 Attempting domain API call');
      }
      const result = await domainFn();
      if (options.logMigration) {
        console.log('✅ Domain API call successful');
      }
      return result;
    } catch (error) {
      if (options.fallbackToLegacy) {
        if (options.logMigration) {
          console.warn('⚠️  Domain API failed, falling back to legacy:', error);
        }
        return legacyFn();
      }
      throw error;
    }
  }

  return legacyFn();
}
