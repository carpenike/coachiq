/**
 * Account — who you are, how CoachIQ looks, and account security.
 *
 * Merges the former Settings and Profile pages; each had too little real
 * content to justify a nav slot (docs/archive/2026-07/frontend-redesign.md).
 *
 * Deliberately omitted (no real backend support):
 *  - Change password / profile editing: no endpoints exist.
 *  - PIN management: creation/change endpoints are not implemented.
 *  - Notifications: no user notification-preference endpoint exists.
 */

import {
  IconArrowsMaximize,
  IconArrowsMinimize,
  IconDeviceDesktop,
  IconMoon,
  IconPalette,
  IconPresentation,
  IconSun,
  IconUser,
} from "@tabler/icons-react"

import { MFASetup } from "@/components/mfa"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { useAuth } from "@/contexts"
import type { Theme } from "@/contexts/theme-context"
import { useTheme } from "@/hooks/use-theme"
import { setWallPanelEnabled, usePreferences } from "@/hooks/usePreferences"
import { useWallPanel } from "@/hooks/useWallPanel"

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

function WallPanelCard() {
  const preferences = usePreferences()
  const wallPanel = useWallPanel()

  const statusLabel = (() => {
    if (!preferences.wallPanelEnabled) return "Disabled"
    if (wallPanel.wakeLockStatus === "active") return "Display kept awake"
    if (wallPanel.wakeLockStatus === "unsupported") return "Wake lock unsupported"
    if (wallPanel.wakeLockStatus === "error") return "Wake lock unavailable"
    return "Requesting wake lock"
  })()

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconPresentation className="size-5" />
          Wall panel
        </CardTitle>
        <CardDescription>
          Keep this device awake for a mounted coach display. This preference is local to the
          current browser.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between gap-4">
          <div>
            <Label htmlFor="wall-panel-mode">Wall-panel mode</Label>
            <p className="text-sm text-muted-foreground">{statusLabel}</p>
          </div>
          <Switch
            id="wall-panel-mode"
            checked={preferences.wallPanelEnabled}
            onCheckedChange={setWallPanelEnabled}
            aria-label="Enable wall-panel mode"
          />
        </div>
        {wallPanel.wakeLockError && (
          <p className="text-sm text-destructive">{wallPanel.wakeLockError}</p>
        )}
        <Button
          variant="outline"
          disabled={!wallPanel.fullscreenSupported}
          onClick={() => void wallPanel.toggleFullscreen()}
        >
          {wallPanel.isFullscreen ? (
            <IconArrowsMinimize className="size-4" />
          ) : (
            <IconArrowsMaximize className="size-4" />
          )}
          {wallPanel.isFullscreen ? "Exit fullscreen" : "Enter fullscreen"}
        </Button>
        {!wallPanel.fullscreenSupported && (
          <p className="text-xs text-muted-foreground">
            Fullscreen is not available in this browser. Installed PWA windows already use a
            standalone display.
          </p>
        )}
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
        <WallPanelCard />
        <MFASetup />
      </div>
    </div>
  )
}
