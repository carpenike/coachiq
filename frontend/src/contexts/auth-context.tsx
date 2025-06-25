/**
 * Authentication Context for CoachIQ Frontend
 *
 * Provides authentication state management using React Query and Context API.
 * All business logic remains in the backend - this only manages UI state and API calls.
 */

import {
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
import { queryKeys } from '@/lib/query-client';
import {
  cleanupTokenStorage,
  initializeTokenStorage,
  setRefreshCallbacks,
  tokenStorage,
  type TokenData
} from '@/lib/token-storage';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { createContext, useContext, useEffect, useMemo } from 'react';

interface AuthContextType {
  // Current state
  user: User | null;
  authStatus: AuthStatus | null;
  isLoading: boolean;
  isAuthenticated: boolean;

  // Authentication actions
  login: (credentials: LoginCredentials) => Promise<LoginResponse>;
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
    onSuccess: (data) => {
      // Store tokens using secure token storage
      tokenStorage.storeTokens({
        access_token: data.access_token,
        refresh_token: data.refresh_token,
        expires_in: data.expires_in,
        refresh_expires_in: data.refresh_expires_in,
      });
      // Invalidate auth queries to refetch user data
      void queryClient.invalidateQueries({ queryKey: queryKeys.auth.all });
    },
    onError: (error) => {
      console.error('Login failed:', error);
      // Clear any existing tokens on login failure
      void tokenStorage.clearTokens();
    },
  });

  // Logout mutation
  const logoutMutation = useMutation({
    mutationFn: apiLogout,
    onSuccess: () => {
      // Clear all tokens securely
      void tokenStorage.clearTokens();
      // Clear all cached data
      void queryClient.clear();
    },
    onError: (error) => {
      console.error('Logout failed:', error);
      // Even if logout fails, clear local state
      void tokenStorage.clearTokens();
      void queryClient.clear();
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
  const { mutateAsync: logoutMutateAsync } = logoutMutation;
  const { mutateAsync: magicLinkMutateAsync } = magicLinkMutation;

  // Admin credentials mutation
  const adminCredentialsMutation = useMutation({
    mutationFn: getAdminCredentials,
  });

  // Initialize token storage and set up refresh callbacks on mount
  useEffect(() => {
    // Initialize token storage
    void initializeTokenStorage();

    // Set up refresh callbacks
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
        // Tokens expired, clearing auth state
        void queryClient.clear();
        void tokenStorage.clearTokens();
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

  const isLoading = statusLoading || userLoading;

  const contextValue: AuthContextType = useMemo(() => ({
    // Current state
    user: user ?? null,
    authStatus: authStatus as AuthStatus | null,
    isLoading,
    isAuthenticated,

    // Authentication actions
    login: loginMutateAsync,
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
