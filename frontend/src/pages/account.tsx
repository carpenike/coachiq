/**
 * Account — who you are, how CoachIQ looks, and account security.
 *
 * Merges the former Settings and Profile pages; each had too little real
 * content to justify a nav slot (docs/frontend-redesign.md).
 *
 * Deliberately omitted (no real backend support):
 *  - Change password / profile editing: no endpoints exist.
 *  - PIN management: creation/change endpoints are not implemented.
 *  - Notifications: no user notification-preference endpoint exists.
 */

import {
  IconDeviceDesktop,
  IconMoon,
  IconPalette,
  IconSun,
  IconUser,
} from "@tabler/icons-react"

import { MFASetup } from "@/components/mfa"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { useAuth } from "@/contexts"
import type { Theme } from "@/contexts/theme-context"
import { useTheme } from "@/hooks/use-theme"

const THEME_OPTIONS: { value: Theme; label: string; icon: typeof IconSun }[] = [
  { value: "light", label: "Light", icon: IconSun },
  { value: "dark", label: "Dark", icon: IconMoon },
  { value: "system", label: "System", icon: IconDeviceDesktop },
]

const AUTH_MODE_LABEL = new Map<string, string>([
  ["none", "Disabled"],
  ["single", "Single User"],
  ["multi", "Multi User"],
])

function InfoRow({ label, value }: Readonly<{ label: string; value: React.ReactNode }>) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-sm font-medium">{value}</span>
    </div>
  )
}

function AccountInfoCard() {
  const { user, authStatus } = useAuth()
  const mode = authStatus?.mode

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconUser className="size-5" />
          Account
        </CardTitle>
        <CardDescription>Your identity and authentication status.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {user ? (
          <>
            <InfoRow label="Username" value={user.username?.trim() ? user.username : "—"} />
            <InfoRow label="Email" value={user.email?.trim() ? user.email : "—"} />
            <InfoRow
              label="Role"
              value={
                <Badge variant={user.role === "admin" ? "default" : "secondary"}>
                  {user.role}
                </Badge>
              }
            />
            <InfoRow
              label="Authentication"
              value={
                <Badge variant="outline">
                  {(mode && AUTH_MODE_LABEL.get(mode)) ?? "Unknown"}
                </Badge>
              }
            />
          </>
        ) : (
          <p className="text-sm text-muted-foreground">
            {mode === "none"
              ? "Authentication is disabled — all access runs as the admin user."
              : "Not signed in."}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

function AppearanceCard() {
  const { theme, setTheme, systemTheme } = useTheme()

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconPalette className="size-5" />
          Appearance
        </CardTitle>
        <CardDescription>
          Choose how CoachIQ looks on this device. The preference is stored locally.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex max-w-sm flex-col gap-2">
          <Label htmlFor="theme-select">Color scheme</Label>
          <Select value={theme} onValueChange={(value) => setTheme(value as Theme)}>
            <SelectTrigger id="theme-select">
              <SelectValue placeholder="Select theme" />
            </SelectTrigger>
            <SelectContent>
              {THEME_OPTIONS.map((option) => (
                <SelectItem key={option.value} value={option.value}>
                  <span className="flex items-center gap-2">
                    <option.icon className="size-4" />
                    {option.label}
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          {theme === "system" && (
            <p className="text-sm text-muted-foreground">
              Currently following your device setting ({systemTheme}).
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

export default function AccountPage() {
  return (
    <div className="flex-1 space-y-6 p-4 pt-6 lg:px-6">
      <div className="grid max-w-3xl gap-6">
        <AccountInfoCard />
        <AppearanceCard />
        <MFASetup />
      </div>
    </div>
  )
}
