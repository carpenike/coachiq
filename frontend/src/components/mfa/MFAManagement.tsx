import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { AlertTriangle, CheckCircle, Shield, Users, UserX, XCircle } from 'lucide-react';
import React, { useState } from 'react';
import { toast } from 'sonner';

interface MFAStatus {
  user_id: string;
  mfa_enabled: boolean;
  setup_initiated: boolean;
  created_at?: string;
  last_used?: string;
  backup_codes_remaining: number;
  backup_codes_total: number;
  available: boolean;
}

const MFAManagement: React.FC = () => {
  const [selectedUser, setSelectedUser] = useState<string | null>(null);
  const [showDisableDialog, setShowDisableDialog] = useState(false);
  const queryClient = useQueryClient();

  // Query all MFA status
  const { data: allMfaStatus, isLoading } = useQuery<MFAStatus[]>({
    queryKey: ['admin-mfa-status'],
    queryFn: async () => {
      const response = await fetch('/api/auth/admin/mfa/status', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
        },
      });
      if (!response.ok) {
        throw new Error('Failed to fetch MFA status');
      }
      return response.json();
    },
  });

  // Disable MFA mutation
  const disableMfaMutation = useMutation({
    mutationFn: async (userId: string) => {
      const response = await fetch('/api/auth/admin/mfa/disable', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ user_id: userId }),
      });
      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Failed to disable MFA');
      }
      return response.json();
    },
    onSuccess: (_data, userId) => {
      toast.success(`MFA disabled for user ${userId}`);
      void queryClient.invalidateQueries({ queryKey: ['admin-mfa-status'] });
      setShowDisableDialog(false);
      setSelectedUser(null);
    },
    onError: (error: Error) => {
      toast.error(error.message);
    },
  });

  const handleDisableMfa = (userId: string) => {
    setSelectedUser(userId);
    setShowDisableDialog(true);
  };

  const confirmDisableMfa = () => {
    if (selectedUser) {
      disableMfaMutation.mutate(selectedUser);
    }
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return 'Never';
    return new Date(dateString).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getStatusBadge = (status: MFAStatus) => {
    if (status.mfa_enabled) {
      return (
        <Badge variant="default" className="flex items-center gap-1">
          <CheckCircle className="h-3 w-3" />
          Enabled
        </Badge>
      );
    } else if (status.setup_initiated) {
      return (
        <Badge variant="secondary" className="flex items-center gap-1">
          <AlertTriangle className="h-3 w-3" />
          Setup Pending
        </Badge>
      );
    } else {
      return (
        <Badge variant="outline" className="flex items-center gap-1">
          <XCircle className="h-3 w-3" />
          Disabled
        </Badge>
      );
    }
  };

  const enabledCount = allMfaStatus?.filter(status => status.mfa_enabled).length || 0;
  const totalUsers = allMfaStatus?.length || 0;

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            MFA Management
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-center py-8">Loading MFA status...</div>
        </CardContent>
      </Card>
    );
  }

  if (!allMfaStatus || allMfaStatus.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            MFA Management
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Alert>
            <Users className="h-4 w-4" />
            <AlertDescription>
              No users found or MFA is not available on this system.
            </AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            MFA Management
          </CardTitle>
          <CardDescription>
            Manage multi-factor authentication for all users
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* Summary Stats */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 border rounded-lg">
              <div className="text-2xl font-bold tracking-tight text-green-600">{enabledCount}</div>
              <div className="text-sm text-muted-foreground">Users with MFA Enabled</div>
            </div>
            <div className="p-4 border rounded-lg">
              <div className="text-2xl font-bold tracking-tight text-blue-600">{totalUsers - enabledCount}</div>
              <div className="text-sm text-muted-foreground">Users without MFA</div>
            </div>
            <div className="p-4 border rounded-lg">
              <div className="text-2xl font-bold tracking-tight text-purple-600">
                {totalUsers > 0 ? Math.round((enabledCount / totalUsers) * 100) : 0}%
              </div>
              <div className="text-sm text-muted-foreground">MFA Adoption Rate</div>
            </div>
          </div>

          {/* Users Table */}
          <div className="border rounded-lg">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>User ID</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Setup Date</TableHead>
                  <TableHead>Last Used</TableHead>
                  <TableHead>Backup Codes</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {allMfaStatus.map((status) => (
                  <TableRow key={status.user_id}>
                    <TableCell className="font-medium">{status.user_id}</TableCell>
                    <TableCell>{getStatusBadge(status)}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {formatDate(status.created_at)}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {formatDate(status.last_used)}
                    </TableCell>
                    <TableCell>
                      {status.mfa_enabled ? (
                        <span className="text-sm">
                          {status.backup_codes_remaining}/{status.backup_codes_total}
                        </span>
                      ) : (
                        <span className="text-sm text-muted-foreground">-</span>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      {status.mfa_enabled && (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleDisableMfa(status.user_id)}
                          disabled={disableMfaMutation.isPending}
                        >
                          <UserX className="h-4 w-4 mr-2" />
                          Disable
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          {enabledCount === 0 && (
            <Alert>
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>
                No users have MFA enabled. Consider encouraging users to enable two-factor authentication for better security.
              </AlertDescription>
            </Alert>
          )}
        </CardContent>
      </Card>

      {/* Disable MFA Confirmation Dialog */}
      <Dialog open={showDisableDialog} onOpenChange={setShowDisableDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Disable MFA</DialogTitle>
            <DialogDescription>
              Are you sure you want to disable multi-factor authentication for user "{selectedUser}"?
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <Alert>
              <AlertTriangle className="h-4 w-4" />
              <AlertDescription>
                This action will remove the user's MFA setup and backup codes. The user will need to set up MFA again if they want to re-enable it.
              </AlertDescription>
            </Alert>
            <div className="flex justify-end gap-2">
              <Button
                variant="outline"
                onClick={() => setShowDisableDialog(false)}
                disabled={disableMfaMutation.isPending}
              >
                Cancel
              </Button>
              <Button
                variant="destructive"
                onClick={confirmDisableMfa}
                disabled={disableMfaMutation.isPending}
              >
                {disableMfaMutation.isPending ? 'Disabling...' : 'Disable MFA'}
              </Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
};

export default MFAManagement;
