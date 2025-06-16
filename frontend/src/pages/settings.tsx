import { AppLayout } from '@/components/app-layout';
import { MFAManagement, MFASetup } from '@/components/mfa';
import { PINManagementCard, SecurityStatusCard } from '@/components/pin-management';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useQuery } from '@tanstack/react-query';
import { Bell, Lock, Settings, Shield, User } from 'lucide-react';
import React from 'react';

interface UserInfo {
  user_id: string;
  username?: string;
  email?: string;
  role: string;
  mode: string;
  authenticated: boolean;
}

const SettingsPage: React.FC = () => {
  // Get current user info
  const { data: userInfo } = useQuery<UserInfo>({
    queryKey: ['user-info'],
    queryFn: async () => {
      const response = await fetch('/api/auth/me', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
        },
      });
      if (!response.ok) {
        throw new Error('Failed to fetch user info');
      }
      return response.json();
    },
  });

  const isAdmin = userInfo?.role === 'admin';

  return (
    <AppLayout pageTitle="Settings">
      <div className="flex-1 space-y-6 p-4 pt-6">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
            <p className="text-muted-foreground">
              Manage your account and application preferences
            </p>
          </div>
        </div>

        <Tabs defaultValue="profile" className="space-y-6">
        <TabsList className="grid grid-cols-4 lg:grid-cols-5 w-full lg:w-auto">
          <TabsTrigger value="profile" className="flex items-center gap-2">
            <User className="h-4 w-4" />
            Profile
          </TabsTrigger>
          <TabsTrigger value="security" className="flex items-center gap-2">
            <Shield className="h-4 w-4" />
            Security
          </TabsTrigger>
          <TabsTrigger value="pins" className="flex items-center gap-2">
            <Lock className="h-4 w-4" />
            PIN Security
          </TabsTrigger>
          <TabsTrigger value="notifications" className="flex items-center gap-2">
            <Bell className="h-4 w-4" />
            Notifications
          </TabsTrigger>
          {isAdmin && (
            <TabsTrigger value="admin" className="flex items-center gap-2">
              <Settings className="h-4 w-4" />
              Admin
            </TabsTrigger>
          )}
        </TabsList>

        <TabsContent value="profile" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <User className="h-5 w-5" />
                Profile Information
              </CardTitle>
              <CardDescription>
                Your account information and preferences
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              {userInfo && (
                <div className="space-y-4">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div>
                      <div className="text-sm font-medium text-muted-foreground">User ID</div>
                      <div className="mt-1 font-mono text-sm">{userInfo.user_id}</div>
                    </div>
                    {userInfo.username && (
                      <div>
                        <div className="text-sm font-medium text-muted-foreground">Username</div>
                        <div className="mt-1">{userInfo.username}</div>
                      </div>
                    )}
                    {userInfo.email && (
                      <div>
                        <div className="text-sm font-medium text-muted-foreground">Email</div>
                        <div className="mt-1">{userInfo.email}</div>
                      </div>
                    )}
                    <div>
                      <div className="text-sm font-medium text-muted-foreground">Role</div>
                      <div className="mt-1">
                        <Badge variant={userInfo.role === 'admin' ? 'default' : 'secondary'}>
                          {userInfo.role}
                        </Badge>
                      </div>
                    </div>
                    <div>
                      <div className="text-sm font-medium text-muted-foreground">Authentication Mode</div>
                      <div className="mt-1">
                        <Badge variant="outline">{userInfo.mode}</Badge>
                      </div>
                    </div>
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="security" className="space-y-6">
          <MFASetup />

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Lock className="h-5 w-5" />
                Password & Authentication
              </CardTitle>
              <CardDescription>
                Manage your password and authentication settings
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="font-medium">Password</div>
                    <div className="text-sm text-muted-foreground">
                      {userInfo?.mode === 'single-user'
                        ? 'Contact your administrator to change your password'
                        : 'Your password is managed through magic links'
                      }
                    </div>
                  </div>
                </div>

                <Separator />

                <div className="space-y-2">
                  <div className="font-medium">Session Information</div>
                  <div className="text-sm text-muted-foreground space-y-1">
                    <div>Authentication Mode: {userInfo?.mode}</div>
                    <div>Status: {userInfo?.authenticated ? 'Authenticated' : 'Not Authenticated'}</div>
                  </div>
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="pins" className="space-y-6">
          <div className="grid gap-6">
            {/* Security Status for User */}
            <SecurityStatusCard
              autoRefresh
              refreshInterval={30000}
              isAdminView={false}
            />

            {/* PIN Management for Current User */}
            <PINManagementCard
              isAdminView={false}
              onPINAction={(action, pinType) => {
                console.log(`User PIN action: ${action} on ${pinType}`);
              }}
            />
          </div>
        </TabsContent>

        <TabsContent value="notifications" className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Bell className="h-5 w-5" />
                Notification Preferences
              </CardTitle>
              <CardDescription>
                Configure how you receive notifications
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                <div className="text-sm text-muted-foreground">
                  Notification settings will be available in a future update.
                </div>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {isAdmin && (
          <TabsContent value="admin" className="space-y-6">
            <MFAManagement />

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Lock className="h-5 w-5" />
                  System Administration
                </CardTitle>
                <CardDescription>
                  Administrative functions and system management
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-4">
                  <div className="text-sm text-muted-foreground">
                    Additional administrative features will be available in future updates.
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        )}
        </Tabs>
      </div>
    </AppLayout>
  );
};

export default SettingsPage;
