// import { useState } from "react" // Reserved for future form state management
import { AppLayout } from "@/components/app-layout"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { Switch } from "@/components/ui/switch"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { useAuth } from "@/contexts"
import { PINManagementCard, SecurityStatusCard } from "@/components/pin-management"
import { DatabaseManagementTab } from "@/components/admin/DatabaseManagementTab"
import {
    IconAlertTriangle,
    IconDatabase,
    IconKey,
    IconLock,
    IconSettings,
    IconShield,
    IconUsers
} from "@tabler/icons-react"

export default function AdminSettingsPage() {
  const { user, authStatus } = useAuth()
  // const [isSubmitting, setIsSubmitting] = useState(false) // Reserved for future form handling

  // Redirect if not admin
  if (!user || user.role !== 'admin') {
    return (
      <AppLayout pageTitle="Admin Settings">
        <div className="flex items-center justify-center min-h-[50vh]">
          <div className="text-center space-y-3">
            <IconShield className="h-12 w-12 mx-auto text-muted-foreground" />
            <h2 className="text-xl font-semibold">Admin Access Required</h2>
            <p className="text-muted-foreground">
              You need administrator privileges to access this page.
            </p>
          </div>
        </div>
      </AppLayout>
    )
  }

  return (
    <AppLayout pageTitle="Admin Settings">
      <div className="flex-1 space-y-6 p-4 pt-6">
        {/* Page Header */}
        <div className="flex items-center justify-end">
          <Badge variant="default">
            <IconShield className="mr-1 h-3 w-3" />
            Administrator
          </Badge>
        </div>

        <Tabs defaultValue="users" className="space-y-6">
        <TabsList>
          <TabsTrigger value="users" className="flex items-center gap-2">
            <IconUsers className="h-4 w-4" />
            User Management
          </TabsTrigger>
          <TabsTrigger value="auth" className="flex items-center gap-2">
            <IconLock className="h-4 w-4" />
            Authentication
          </TabsTrigger>
          <TabsTrigger value="security" className="flex items-center gap-2">
            <IconShield className="h-4 w-4" />
            PIN Security
          </TabsTrigger>
          <TabsTrigger value="system" className="flex items-center gap-2">
            <IconSettings className="h-4 w-4" />
            System Settings
          </TabsTrigger>
          <TabsTrigger value="database" className="flex items-center gap-2">
            <IconDatabase className="h-4 w-4" />
            Database
          </TabsTrigger>
        </TabsList>

        {/* User Management Tab */}
        <TabsContent value="users" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <IconUsers className="h-5 w-5" />
                User Management
              </CardTitle>
              <CardDescription>
                Manage user accounts and permissions
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="font-medium">Current Authentication Mode</p>
                  <p className="text-sm text-muted-foreground">
                    {authStatus?.mode === 'single' && 'Single User Mode - Only admin account is active'}
                    {authStatus?.mode === 'multi' && 'Multi User Mode - Multiple user accounts supported'}
                    {authStatus?.mode === 'none' && 'Authentication Disabled - No login required'}
                  </p>
                </div>
                <Badge variant="outline">
                  {authStatus?.mode === 'single' && 'Single User'}
                  {authStatus?.mode === 'multi' && 'Multi User'}
                  {authStatus?.mode === 'none' && 'Disabled'}
                </Badge>
              </div>

              {authStatus?.mode === 'single' && (
                <>
                  <Separator />
                  <div className="space-y-3">
                    <h4 className="font-medium">Admin Account</h4>
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <Label>Username</Label>
                        <Input value={user.username || ''} disabled />
                      </div>
                      <div>
                        <Label>Role</Label>
                        <Input value="Administrator" disabled />
                      </div>
                    </div>
                  </div>
                </>
              )}

              {authStatus?.mode === 'multi' && (
                <div className="space-y-3">
                  <Button disabled>
                    <IconUsers className="mr-2 h-4 w-4" />
                    Manage Users (Coming Soon)
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Authentication Tab */}
        <TabsContent value="auth" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <IconLock className="h-5 w-5" />
                Authentication Settings
              </CardTitle>
              <CardDescription>
                Configure authentication and security options
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <div className="text-base">Magic Link Authentication</div>
                    <div className="text-sm text-muted-foreground">
                      Allow users to login via email magic links
                    </div>
                  </div>
                  <Switch disabled defaultChecked={false} />
                </div>

                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <div className="text-base">Multi-Factor Authentication</div>
                    <div className="text-sm text-muted-foreground">
                      Require additional verification for login
                    </div>
                  </div>
                  <Switch disabled defaultChecked={false} />
                </div>

                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <div className="text-base">Account Lockout Protection</div>
                    <div className="text-sm text-muted-foreground">
                      Lock accounts after failed login attempts
                    </div>
                  </div>
                  <Switch disabled defaultChecked />
                </div>
              </div>

              <Separator />

              <div className="space-y-3">
                <h4 className="font-medium flex items-center gap-2">
                  <IconKey className="h-4 w-4" />
                  Password Requirements
                </h4>
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label>Minimum Length</Label>
                    <Input type="number" value="8" disabled />
                  </div>
                  <div>
                    <Label>Session Timeout (minutes)</Label>
                    <Input type="number" value="15" disabled />
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* PIN Security Tab */}
        <TabsContent value="security" className="space-y-6">
          <div className="grid gap-6">
            {/* Security Status Overview */}
            <SecurityStatusCard
              autoRefresh
              refreshInterval={30000}
              isAdminView
              onSessionAction={(action, sessionId) => {
                console.log(`Admin session action: ${action} on ${sessionId}`);
              }}
            />

            {/* PIN Management for Current Admin */}
            <PINManagementCard
              userId={user?.user_id}
              isAdminView
              onPINAction={(action, pinType) => {
                console.log(`Admin PIN action: ${action} on ${pinType}`);
              }}
            />
          </div>
        </TabsContent>

        {/* System Settings Tab */}
        <TabsContent value="system" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <IconSettings className="h-5 w-5" />
                System Configuration
              </CardTitle>
              <CardDescription>
                General system settings and preferences
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <div className="text-base">Debug Mode</div>
                    <div className="text-sm text-muted-foreground">
                      Enable detailed logging and debug information
                    </div>
                  </div>
                  <Switch disabled defaultChecked />
                </div>

                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <div className="text-base">API Documentation</div>
                    <div className="text-sm text-muted-foreground">
                      Make API docs publicly accessible
                    </div>
                  </div>
                  <Switch disabled defaultChecked />
                </div>

                <div className="flex items-center justify-between">
                  <div className="space-y-0.5">
                    <div className="text-base">Performance Metrics</div>
                    <div className="text-sm text-muted-foreground">
                      Collect and display performance data
                    </div>
                  </div>
                  <Switch disabled defaultChecked />
                </div>
              </div>

              <Separator />

              <div className="space-y-3">
                <h4 className="font-medium flex items-center gap-2">
                  <IconDatabase className="h-4 w-4" />
                  Data Management
                </h4>
                <div className="flex gap-3">
                  <Button variant="outline" disabled>
                    <IconDatabase className="mr-2 h-4 w-4" />
                    Export Configuration
                  </Button>
                  <Button variant="outline" disabled>
                    <IconDatabase className="mr-2 h-4 w-4" />
                    Import Configuration
                  </Button>
                </div>
              </div>

              <Separator />

              <div className="space-y-3">
                <h4 className="font-medium flex items-center gap-2 text-destructive">
                  <IconAlertTriangle className="h-4 w-4" />
                  Danger Zone
                </h4>
                <div className="border border-destructive/20 rounded-lg p-4 space-y-3">
                  <div className="space-y-2">
                    <p className="text-sm font-medium">Reset System Configuration</p>
                    <p className="text-sm text-muted-foreground">
                      This will reset all settings to default values. This action cannot be undone.
                    </p>
                  </div>
                  <Button variant="destructive" disabled size="sm">
                    Reset Configuration
                  </Button>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Database Management Tab */}
        <TabsContent value="database" className="space-y-6">
          <DatabaseManagementTab />
        </TabsContent>
        </Tabs>
      </div>
    </AppLayout>
  )
}
