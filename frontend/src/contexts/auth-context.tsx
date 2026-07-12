/**
 * Authentication Context for CoachIQ Frontend
 *
 * Provides authentication state management using React Query and Context API.
 * All business logic remains in the backend - this only manages UI state and API calls.
 */

import {
  completeOidcLogin as apiCompleteOidcLogin,
  login as apiLogin,
  logout as apiLogout,
  getAdminCredentials,
  getAuthStatus,
  getCurrentUser,
  sendMagicLink,
} from '@/api/endpoints';
import type {
  AdminCredentials,
  AuthStatus,
  LoginCredentials,
  LoginResponse,
  MagicLinkRequest,
  User,
} from '@/api/types';
import { clearProtectedQueries, queryKeys } from '@/lib/query-client';
import {
  cleanupTokenStorage,
  initializeTokenStorage,
  setRefreshCallbacks,
  tokenStorage,
  type TokenData
} from '@/lib/token-storage';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { createContext, useContext, useEffect, useMemo, useState } from 'react';

interface AuthContextType {
  // Current state
  user: User | null;
  authStatus: AuthStatus | null;
  isLoading: boolean;
  isAuthenticated: boolean;

  // Authentication actions
  login: (credentials: LoginCredentials) => Promise<LoginResponse>;
  completeOidcLogin: (sessionCode: string) => Promise<LoginResponse>;
  logout: () => Promise<void>;
  sendMagicLink: (request: MagicLinkRequest) => Promise<void>;

  // Admin credential retrieval
  getAdminCredentials: () => Promise<AdminCredentials>;
  hasGeneratedCredentials: boolean;

  // Error states
  loginError: Error | null;
  userError: Error | null;
  statusError: Error | null;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const queryClient = useQueryClient();

  // Fetch authentication status
  const {
    data: authStatus,
    error: statusError,
    isLoading: statusLoading,
  } = useQuery({
    queryKey: queryKeys.auth.status(),
    queryFn: getAuthStatus,
    staleTime: 30000, // Auth status is fairly static
    retry: 1, // Don't retry auth status failures aggressively
  });

  // Fetch current user (only if auth is enabled)
  const {
    data: user,
    error: userError,
    isLoading: userLoading,
  } = useQuery({
    queryKey: queryKeys.auth.user(),
    queryFn: getCurrentUser,
    enabled: authStatus?.enabled ?? false, // Only fetch if auth is enabled
    staleTime: 60000, // User info doesn't change often
    retry: (failureCount, error) => {
      // Don't retry 401/403 errors
      const httpError = error as { status?: number };
      if (httpError?.status === 401 || httpError?.status === 403) {
        return false;
      }
      return failureCount < 2;
    },
  });

  // Calculate authentication state early, before using it in other queries
  const isAuthenticated = !!(user?.authenticated && authStatus?.enabled);

  // Check if there are generated credentials available
  // Try to fetch admin credentials endpoint to see if any exist
  const { data: credentialsCheck } = useQuery({
    queryKey: ['admin', 'credentials-check'],
    queryFn: async () => {
      const token = tokenStorage.getAccessToken();
      if (!token) return { available: false };

      const response = await fetch('/api/auth/admin/credentials', {
        headers: { Authorization: `Bearer ${token}` }
      });

      // If we get a successful response, credentials are available
      // If we get 404 or error message about "no credentials", they're not available
      if (response.ok) {
        return { available: true };
      } else {
        return { available: false };
      }
    },
    enabled: authStatus?.mode === 'single' && user?.role === 'admin' && isAuthenticated,
    staleTime: 5 * 60 * 1000, // 5 minutes
    retry: false, // Don't retry on error
  });

  const hasGeneratedCredentials = credentialsCheck?.available || false;

  // Login mutation
  const loginMutation = useMutation({
    mutationFn: ({ username, password }: LoginCredentials) => apiLogin(username, password),
    onSuccess: async (data) => {
      // Store tokens using secure token storage
      tokenStorage.storeTokens({
        access_token: data.access_token,
        refresh_token: data.refresh_token,
        expires_in: data.expires_in,
        refresh_expires_in: data.refresh_expires_in,
      });
      // Refetch auth queries with the freshly-stored token and AWAIT completion
      // before the mutation resolves. Cancelling first drops any in-flight
      // unauthenticated fetch so it can't overwrite the authenticated result.
      // Awaiting here is what closes the login race: callers (e.g. the OIDC
      // callback page) only navigate once `user` reflects the new session, so
      // AuthGuard never sees a stale unauthenticated state and bounces to /login.
      await queryClient.cancelQueries({ queryKey: queryKeys.auth.all });
      await queryClient.invalidateQueries({ queryKey: queryKeys.auth.all });
    },
    onError: (error) => {
      console.error('Login failed:', error);
      // Clear any existing tokens on login failure
      void tokenStorage.clearTokens();
    },
  });

  const oidcLoginMutation = useMutation({
    mutationFn: (sessionCode: string) => apiCompleteOidcLogin(sessionCode),
    onSuccess: async (data) => {
      tokenStorage.storeTokens({
        access_token: data.access_token,
        refresh_token: data.refresh_token,
        expires_in: data.expires_in,
        refresh_expires_in: data.refresh_expires_in,
      });
      // See loginMutation above: await the authenticated refetch so the OIDC
      // callback only redirects to the app after `user` is hydrated. Without
      // this await the PocketID flow runs twice (AuthGuard bounces to /login
      // before the token lands in the query cache).
      await queryClient.cancelQueries({ queryKey: queryKeys.auth.all });
      await queryClient.invalidateQueries({ queryKey: queryKeys.auth.all });
    },
    onError: (error) => {
      console.error('PocketID login failed:', error);
      tokenStorage.clearTokens().catch((clearError: unknown) => {
        console.error('Failed to clear tokens after PocketID login failure:', clearError);
      });
    },
  });

  // Logout mutation
  const logoutMutation = useMutation({
    mutationFn: apiLogout,
    onSuccess: () => {
      // Clear all tokens securely
      void tokenStorage.clearTokens();
      clearProtectedQueries(queryClient);
    },
    onError: (error) => {
      console.error('Logout failed:', error);
      // Even if logout fails, clear local state
      void tokenStorage.clearTokens();
      clearProtectedQueries(queryClient);
    },
  });

  // Magic link mutation
  const magicLinkMutation = useMutation({
    mutationFn: (request: MagicLinkRequest) => sendMagicLink(request.email, request.redirect_url),
    onSuccess: () => {
      // Magic link sent successfully - no additional action needed
    },
    onError: (error) => {
      console.error('Magic link failed:', error);
    },
  });

  // Destructure mutation functions for stable references
  const { mutateAsync: loginMutateAsync, error: loginError } = loginMutation;
  const { mutateAsync: oidcLoginMutateAsync } = oidcLoginMutation;
  const { mutateAsync: logoutMutateAsync } = logoutMutation;
  const { mutateAsync: magicLinkMutateAsync } = magicLinkMutation;

  // Admin credentials mutation
  const adminCredentialsMutation = useMutation({
    mutationFn: getAdminCredentials,
  });

  // Session restore gate: while a stored session may still be revived (token
  // refresh in flight during initializeTokenStorage), AuthGuard must not
  // treat "no valid user yet" as unauthenticated and bounce to /login.
  const [restoringSession, setRestoringSession] = useState(false);

  // Register refresh callbacks once. Session restoration starts separately
  // after the single shared auth-status query resolves.
  useEffect(() => {
    setRefreshCallbacks({
      onRefreshSuccess: (_tokens: TokenData) => {
        // Token refreshed successfully - invalidate queries to refresh data
        void queryClient.invalidateQueries({ queryKey: queryKeys.auth.user() });
      },
      onRefreshFailure: (error: Error) => {
        console.error('Token refresh failed:', error);
        // Could show notification to user
      },
      onTokenExpired: () => {
        // Token storage already removed the rejected token. Keep the public
        // auth-status result so AuthGuard can route directly to /login.
        clearProtectedQueries(queryClient);
      },
    });

    // Check if we have a valid token and validate it
    const tokenData = tokenStorage.getTokenData();
    if (tokenData && tokenStorage.isAccessTokenValid()) {
      // Token exists and is valid, validate by fetching user data
      void queryClient.invalidateQueries({ queryKey: queryKeys.auth.user() });
    }

    // Cleanup on unmount
    return () => {
      cleanupTokenStorage();
    };
  }, [queryClient]);

  useEffect(() => {
    if (!authStatus) return

    let cancelled = false
    setRestoringSession(true)
    void initializeTokenStorage(authStatus).finally(() => {
      if (!cancelled) setRestoringSession(false)
    })
    return () => {
      cancelled = true
    }
  }, [authStatus])

  const isLoading = statusLoading || userLoading || restoringSession;

  const contextValue: AuthContextType = useMemo(() => ({
    // Current state
    user: user ?? null,
    authStatus: authStatus as AuthStatus | null,
    isLoading,
    isAuthenticated,

    // Authentication actions
    login: loginMutateAsync,
    completeOidcLogin: oidcLoginMutateAsync,
    logout: async () => {
      await logoutMutateAsync();
    },
    sendMagicLink: async (request: MagicLinkRequest) => {
      await magicLinkMutateAsync(request);
    },

    // Admin credential retrieval
    getAdminCredentials: adminCredentialsMutation.mutateAsync,
    hasGeneratedCredentials,

    // Error states
    loginError: loginError,
    userError: userError,
    statusError: statusError,
  }), [
    user,
    authStatus,
    isLoading,
    isAuthenticated,
    loginMutateAsync,
    oidcLoginMutateAsync,
    loginError,
    logoutMutateAsync,
    magicLinkMutateAsync,
    adminCredentialsMutation.mutateAsync,
    hasGeneratedCredentials,
    userError,
    statusError
  ]);

  return (
    <AuthContext.Provider value={contextValue}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

// Helper hook for checking if user has specific role
export function useHasRole(role: User['role']) {
  const { user } = useAuth();
  return user?.role === role;
}

// Helper hook for checking authentication mode
export function useAuthMode() {
  const { authStatus } = useAuth();
  return authStatus?.mode ?? 'none';
}
