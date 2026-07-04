/**
 * Admin — administrator-only view of authentication state and system
 * management, bound exclusively to real backend endpoints:
 *
 *  - /api/auth/status       (via AuthProvider) — current auth mode
 *  - /api/auth/me           (via AuthProvider) — admin account info
 *  - /api/auth/admin/stats  — authentication/invitation statistics
 *  - /api/auth/admin/mfa/*  — MFA overview + admin disable (MFAManagement)
 *  - /api/database/*        — schema status/migrations (DatabaseManagementTab)
 *
 * Dropped from the old admin-settings page (no backend implementation):
 * "Manage Users (Coming Soon)" (backend replies "not yet implemented"),
 * the disabled auth/system toggle switches, password-requirement inputs,
 * config export/import, reset-configuration, and the PIN tab (PIN
 * create/change endpoints return 404/405).
 */

import { IconDatabase, IconLock, IconShield, IconUser } from "@tabler/icons-react"
import { useQuery } from "@tanstack/react-query"

import { apiRequest } from "@/api/client"
import { MFAManagement } from "@/components/mfa"
import { DatabaseManagementTab } from "@/components/admin/DatabaseManagementTab"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useAuth } from "@/contexts"

interface AdminStats {
  authentication: {
    auth_mode: string
    jwt_available: boolean
    bcrypt_available: boolean
    secret_key_configured: boolean
    notification_manager_available: boolean
    admin_configured: boolean | null
    has_generated_credentials: boolean
  }
  invitations: {
    total: number
    active: number
    used: number
    expired: number
  } | null
  endpoints: {
    login_enabled: boolean
    magic_links_enabled: boolean
    oidc_enabled: boolean
    invitations_enabled: boolean
  }
}

const AUTH_MODE_LABEL = new Map<string, string>([
  ["none", "Disabled"],
  ["single", "Single User"],
  ["multi", "Multi User"],
])

const AUTH_MODE_DESCRIPTION = new Map<string, string>([
  ["none", "Authentication is disabled — no login required."],
  ["single", "Single user mode — only the admin account is active."],
  ["multi", "Multi user mode — multiple user accounts supported."],
])

function authModeLabel(mode: string | undefined): string {
  if (!mode) return "Unknown"
  return AUTH_MODE_LABEL.get(mode) ?? mode
}

function authModeDescription(mode: string | undefined): string {
  return (mode && AUTH_MODE_DESCRIPTION.get(mode)) || "The backend did not report an auth mode."
}


function BoolBadge({ value, trueLabel = "Enabled", falseLabel = "Disabled" }: Readonly<{
  value: boolean
  trueLabel?: string
  falseLabel?: string
}>) {
  return <Badge variant={value ? "default" : "secondary"}>{value ? trueLabel : falseLabel}</Badge>
}

function AuthModeCard() {
  const { authStatus } = useAuth()
  const mode = authStatus?.mode

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconLock className="size-5" />
          Authentication Mode
        </CardTitle>
        <CardDescription>Current authentication configuration reported by the backend</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {!authStatus ? (
          <Skeleton className="h-16" />
        ) : (
          <>
            <div className="flex items-center justify-between">
              <div>
                <p className="font-medium">{authModeLabel(mode)}</p>
                <p className="text-sm text-muted-foreground">
                  {authModeDescription(mode)}
                </p>
              </div>
              <Badge variant="outline">{mode ?? "unknown"}</Badge>
            </div>
            <div className="grid grid-cols-1 gap-2 pt-2 text-sm sm:grid-cols-3">
              <div className="flex items-center justify-between gap-2 sm:flex-col sm:items-start">
                <span className="text-muted-foreground">Magic links</span>
                <BoolBadge value={authStatus.magic_links_enabled} />
              </div>
              <div className="flex items-center justify-between gap-2 sm:flex-col sm:items-start">
                <span className="text-muted-foreground">OIDC / SSO</span>
                <BoolBadge value={authStatus.oidc_enabled} />
              </div>
              <div className="flex items-center justify-between gap-2 sm:flex-col sm:items-start">
                <span className="text-muted-foreground">JWT</span>
                <BoolBadge value={authStatus.jwt_available} trueLabel="Available" falseLabel="Unavailable" />
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}

function AdminAccountCard() {
  const { user } = useAuth()
  if (!user) return null

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconUser className="size-5" />
          Your Account
        </CardTitle>
        <CardDescription>The account you are signed in with</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">User ID</span>
          <span className="font-mono">{user.user_id}</span>
        </div>
        {user.username && (
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">Username</span>
            <span>{user.username}</span>
          </div>
        )}
        {user.email && (
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground">Email</span>
            <span>{user.email}</span>
          </div>
        )}
        <div className="flex items-center justify-between">
          <span className="text-muted-foreground">Role</span>
          <Badge>{user.role}</Badge>
        </div>
      </CardContent>
    </Card>
  )
}

function AuthStatsCard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["admin", "auth-stats"],
    queryFn: () => apiRequest<AdminStats>("/api/auth/admin/stats"),
    staleTime: 30_000,
  })

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconShield className="size-5" />
          Authentication Details
        </CardTitle>
        <CardDescription>Live statistics from /api/auth/admin/stats</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {isLoading && <Skeleton className="h-24" />}
        {error && (
          <p className="text-sm text-destructive">
            Couldn't load authentication statistics: {error.message}
          </p>
        )}
        {data && (
          <>
            <div className="grid grid-cols-1 gap-2 text-sm sm:grid-cols-2">
              <div className="flex items-center justify-between gap-2">
                <span className="text-muted-foreground">Password login</span>
                <BoolBadge value={data.endpoints.login_enabled} />
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className="text-muted-foreground">Invitations</span>
                <BoolBadge value={data.endpoints.invitations_enabled} />
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className="text-muted-foreground">Secret key configured</span>
                <BoolBadge value={data.authentication.secret_key_configured} trueLabel="Yes" falseLabel="No" />
              </div>
              <div className="flex items-center justify-between gap-2">
                <span className="text-muted-foreground">Generated admin credentials</span>
                <BoolBadge value={data.authentication.has_generated_credentials} trueLabel="Yes" falseLabel="No" />
              </div>
            </div>
            {data.invitations && data.endpoints.invitations_enabled && (
              <div className="space-y-2 border-t pt-3">
                <p className="text-sm font-medium">Invitations</p>
                <div className="grid grid-cols-4 gap-2 text-center text-sm">
                  {(
                    [
                      ["Total", data.invitations.total],
                      ["Active", data.invitations.active],
                      ["Used", data.invitations.used],
                      ["Expired", data.invitations.expired],
                    ] as const
                  ).map(([label, count]) => (
                    <div key={label} className="rounded-md border p-2">
                      <p className="text-lg font-semibold">{count}</p>
                      <p className="text-xs text-muted-foreground">{label}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}

export default function AdminPage() {
  const { user } = useAuth()

  if (!user || user.role !== "admin") {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <div className="space-y-3 text-center">
          <IconShield className="mx-auto size-12 text-muted-foreground" />
          <h2 className="text-xl font-semibold">Admin Access Required</h2>
          <p className="text-muted-foreground">
            You need administrator privileges to access this page.
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 space-y-6 p-4 pt-6 lg:px-6">
      <Tabs defaultValue="overview" className="space-y-6">
        <TabsList>
          <TabsTrigger value="overview" className="flex items-center gap-2">
            <IconLock className="size-4" />
            Overview
          </TabsTrigger>
          <TabsTrigger value="mfa" className="flex items-center gap-2">
            <IconShield className="size-4" />
            MFA
          </TabsTrigger>
          <TabsTrigger value="database" className="flex items-center gap-2">
            <IconDatabase className="size-4" />
            Database
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-6">
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <AuthModeCard />
            <AdminAccountCard />
          </div>
          <AuthStatsCard />
        </TabsContent>

        <TabsContent value="mfa" className="space-y-6">
          <MFAManagement />
        </TabsContent>

        <TabsContent value="database" className="space-y-6">
          <DatabaseManagementTab />
        </TabsContent>
      </Tabs>
    </div>
  )
}
