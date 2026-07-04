/**
 * Settings — user preferences for this device and account security.
 *
 * Tabs:
 *  - Appearance: theme (light/dark/system) via the existing ThemeProvider.
 *  - Security:   multi-factor authentication (real /api/auth/mfa/* endpoints;
 *                the card reports honestly when MFA is unavailable).
 *
 * Deliberately omitted (no real backend support — see docs/frontend-redesign.md):
 *  - Change password: no password-change endpoint exists.
 *  - PIN management: /api/pin-auth/change-pin and PIN creation are not
 *    implemented backend-side (404/405).
 *  - Notifications: no user notification-preference endpoint exists.
 */

import { IconDeviceDesktop, IconMoon, IconPalette, IconShield, IconSun } from "@tabler/icons-react"

import { MFASetup } from "@/components/mfa"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Label } from "@/components/ui/label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import type { Theme } from "@/contexts/theme-context"
import { useTheme } from "@/hooks/use-theme"

const THEME_OPTIONS: { value: Theme; label: string; icon: typeof IconSun }[] = [
  { value: "light", label: "Light", icon: IconSun },
  { value: "dark", label: "Dark", icon: IconMoon },
  { value: "system", label: "System", icon: IconDeviceDesktop },
]

function AppearanceTab() {
  const { theme, setTheme, systemTheme } = useTheme()

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconPalette className="size-5" />
          Theme
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

export default function SettingsPage() {
  return (
    <div className="flex-1 space-y-6 p-4 pt-6 lg:px-6">
      <Tabs defaultValue="appearance" className="space-y-6">
        <TabsList>
          <TabsTrigger value="appearance" className="flex items-center gap-2">
            <IconPalette className="size-4" />
            Appearance
          </TabsTrigger>
          <TabsTrigger value="security" className="flex items-center gap-2">
            <IconShield className="size-4" />
            Security
          </TabsTrigger>
        </TabsList>

        <TabsContent value="appearance" className="space-y-6">
          <AppearanceTab />
        </TabsContent>

        <TabsContent value="security" className="space-y-6">
          <MFASetup />
        </TabsContent>
      </Tabs>
    </div>
  )
}
