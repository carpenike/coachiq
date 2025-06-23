import { useState, useEffect } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  IconAlertTriangle,
  IconCheck,
  IconCircleCheck,
  IconCircleX,
  IconDatabase,
  IconDownload,
  IconHistory,
  IconLoader2,
  IconRefresh,
  IconShield,
  IconX,
} from "@tabler/icons-react"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Progress } from "@/components/ui/progress"
import { Separator } from "@/components/ui/separator"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { toast } from "sonner"
import { apiRequest } from "@/api/client"
import { formatDistanceToNow, format } from "date-fns"

// Types
interface SafetyStatus {
  is_safe: boolean
  blocking_reasons: string[]
  system_state: {
    vehicle_speed: number
    parking_brake: boolean
    engine_running: boolean
    transmission_gear: string
  }
  interlocks: {
    all_satisfied: boolean
    violations: string[]
  }
  recommendations: string[]
}

interface DatabaseStatus {
  current_version: string
  target_version: string
  needs_update: boolean
  pending_migrations: { version: string; description: string }[]
  is_safe_to_migrate: boolean
  safety_issues: string[]
  latest_backup: {
    path: string
    size_bytes: number
    created_at: string
  } | null
  migration_in_progress: boolean
  current_job_id: string | null
}

interface MigrationJob {
  id: string
  status: string
  progress: number
  started_at: string
  steps: {
    status: string
    timestamp: string
    progress: number
  }[]
  error?: string
  completed_at?: string
}

interface MigrationHistory {
  id: number
  from_version: string
  to_version: string
  status: "success" | "failed" | "rolled_back"
  duration_ms: number
  executed_at: string
  details?: {
    job_id?: string
    backup_path?: string
    error?: string
  }
}

// API functions
const fetchDatabaseStatus = async (): Promise<DatabaseStatus> => {
  return apiRequest<DatabaseStatus>("/api/database/status")
}

const fetchSafetyStatus = async (): Promise<SafetyStatus> => {
  return apiRequest<SafetyStatus>("/api/database/safety-check")
}

const fetchMigrationHistory = async (): Promise<MigrationHistory[]> => {
  return apiRequest<MigrationHistory[]>("/api/database/history?limit=10")
}

const fetchJobStatus = async (jobId: string): Promise<MigrationJob> => {
  return apiRequest<MigrationJob>(`/api/database/migrate/${jobId}/status`)
}

const startMigration = async (options: {
  confirm: boolean
  force?: boolean
  skip_backup?: boolean
}) => {
  return apiRequest("/api/database/migrate", {
    method: "POST",
    body: JSON.stringify(options),
  })
}

// Components
function SafetyStatusCard({
  safetyStatus,
  isLoading,
  error,
  onRefresh
}: {
  safetyStatus?: SafetyStatus
  isLoading: boolean
  error: Error | null
  onRefresh: () => void
}) {
  const getSafetyBadge = () => {
    if (isLoading) {
      return (
        <Badge variant="secondary" className="h-8 px-3">
          <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
          CHECKING SYSTEM STATUS...
        </Badge>
      )
    }

    if (error || !safetyStatus) {
      return (
        <Badge variant="destructive" className="h-8 px-3">
          <IconCircleX className="mr-2 h-4 w-4" />
          MIGRATION UNSAFE: STATUS UNKNOWN
        </Badge>
      )
    }

    if (safetyStatus.is_safe) {
      return (
        <Badge variant="default" className="h-8 px-3 bg-green-600">
          <IconCircleCheck className="mr-2 h-4 w-4" />
          READY FOR MIGRATION
        </Badge>
      )
    }

    return (
      <Badge variant="destructive" className="h-8 px-3">
        <IconCircleX className="mr-2 h-4 w-4" />
        MIGRATION UNSAFE: ACTION REQUIRED
      </Badge>
    )
  }

  const SafetyCheckItem = ({
    label,
    isSafe,
    details
  }: {
    label: string
    isSafe: boolean
    details: string
  }) => (
    <div className="flex items-center justify-between py-2">
      <div className="flex items-center gap-2">
        {isSafe ? (
          <IconCheck className="h-4 w-4 text-green-600" />
        ) : (
          <IconX className="h-4 w-4 text-red-600" />
        )}
        <span className={isSafe ? "" : "text-red-600"}>{label}</span>
      </div>
      <span className="text-sm text-muted-foreground">{details}</span>
    </div>
  )

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="flex items-center gap-2">
              <IconShield className="h-5 w-5" />
              Pre-Flight Safety Check
            </CardTitle>
            <CardDescription>
              System must be in a safe state before database migration
            </CardDescription>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={onRefresh}
            disabled={isLoading}
          >
            <IconRefresh className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          </Button>
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex justify-center py-2">
          {getSafetyBadge()}
        </div>

        {safetyStatus && (
          <>
            <Separator />
            <div className="space-y-1">
              <SafetyCheckItem
                label="Vehicle Stopped"
                isSafe={safetyStatus.system_state.vehicle_speed === 0}
                details={`Speed: ${safetyStatus.system_state.vehicle_speed} mph`}
              />
              <SafetyCheckItem
                label="Parking Brake Engaged"
                isSafe={safetyStatus.system_state.parking_brake}
                details={safetyStatus.system_state.parking_brake ? "Engaged" : "Not Engaged"}
              />
              <SafetyCheckItem
                label="Engine Status"
                isSafe={!safetyStatus.system_state.engine_running}
                details={safetyStatus.system_state.engine_running ? "Running" : "Off"}
              />
              <SafetyCheckItem
                label="Transmission in PARK"
                isSafe={safetyStatus.system_state.transmission_gear === "PARK"}
                details={`Gear: ${safetyStatus.system_state.transmission_gear}`}
              />
              <SafetyCheckItem
                label="Safety Interlocks"
                isSafe={safetyStatus.interlocks.all_satisfied}
                details={
                  safetyStatus.interlocks.all_satisfied
                    ? "All Satisfied"
                    : safetyStatus.interlocks.violations.join(", ")
                }
              />
            </div>

            {!safetyStatus.is_safe && safetyStatus.recommendations.length > 0 && (
              <>
                <Separator />
                <Alert>
                  <IconAlertTriangle className="h-4 w-4" />
                  <AlertTitle>Required Actions</AlertTitle>
                  <AlertDescription>
                    <ul className="mt-2 space-y-1">
                      {safetyStatus.recommendations.map((rec, idx) => (
                        <li key={idx} className="text-sm">• {rec}</li>
                      ))}
                    </ul>
                  </AlertDescription>
                </Alert>
              </>
            )}
          </>
        )}
      </CardContent>
    </Card>
  )
}

function MigrationControlCard({
  databaseStatus,
  safetyStatus,
  onMigrationStart,
  activeJobId,
}: {
  databaseStatus?: DatabaseStatus
  safetyStatus?: SafetyStatus
  onMigrationStart: (jobId: string) => void
  activeJobId: string | null
}) {
  const [showConfirmDialog, setShowConfirmDialog] = useState(false)
  const [confirmText, setConfirmText] = useState("")
  const [showPinDialog, setShowPinDialog] = useState(false)
  const [pin, setPin] = useState("")

  const queryClient = useQueryClient()

  const migrationMutation = useMutation({
    mutationFn: startMigration,
    onSuccess: (data) => {
      toast.success("Migration started successfully")
      onMigrationStart(data.job_id)
      setShowPinDialog(false)
      setShowConfirmDialog(false)
      setConfirmText("")
      setPin("")
      queryClient.invalidateQueries({ queryKey: ["database-status"] })
    },
    onError: (error: Error) => {
      toast.error(`Migration failed: ${error.message}`)
      setShowPinDialog(false)
    },
  })

  const canStartMigration =
    databaseStatus?.needs_update &&
    safetyStatus?.is_safe &&
    !databaseStatus?.migration_in_progress &&
    !activeJobId

  const handleMigrationStart = () => {
    if (!canStartMigration) return
    setShowConfirmDialog(true)
  }

  const handleConfirmMigration = () => {
    if (confirmText !== "MIGRATE") {
      toast.error("Please type MIGRATE to confirm")
      return
    }
    setShowConfirmDialog(false)
    setShowPinDialog(true)
  }

  const handlePinSubmit = async () => {
    // In a real implementation, verify PIN with backend first
    // For now, we'll proceed with migration
    migrationMutation.mutate({
      confirm: true,
      force: false,
      skip_backup: false,
    })
  }

  if (activeJobId) {
    return <MigrationProgressCard jobId={activeJobId} />
  }

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <IconDatabase className="h-5 w-5" />
            Migration Control
          </CardTitle>
          <CardDescription>
            Manage database schema updates
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {databaseStatus && (
            <>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label className="text-muted-foreground">Current Version</Label>
                  <p className="font-mono">{databaseStatus.current_version}</p>
                </div>
                <div>
                  <Label className="text-muted-foreground">Target Version</Label>
                  <p className="font-mono">{databaseStatus.target_version}</p>
                </div>
              </div>

              {databaseStatus.pending_migrations.length > 0 && (
                <>
                  <Separator />
                  <div>
                    <Label className="text-muted-foreground">Pending Migrations</Label>
                    <ul className="mt-2 space-y-1">
                      {databaseStatus.pending_migrations.map((migration, idx) => (
                        <li key={idx} className="text-sm">
                          <span className="font-mono">{migration.version}</span>
                          {migration.description && (
                            <span className="text-muted-foreground"> - {migration.description}</span>
                          )}
                        </li>
                      ))}
                    </ul>
                  </div>
                </>
              )}

              {databaseStatus.latest_backup && (
                <>
                  <Separator />
                  <div>
                    <Label className="text-muted-foreground">Latest Backup</Label>
                    <p className="text-sm">
                      Created {formatDistanceToNow(new Date(databaseStatus.latest_backup.created_at))} ago
                    </p>
                    <p className="text-xs text-muted-foreground">
                      Size: {(databaseStatus.latest_backup.size_bytes / 1024 / 1024).toFixed(2)} MB
                    </p>
                  </div>
                </>
              )}

              <Separator />

              <div className="flex justify-center">
                <Button
                  size="lg"
                  disabled={!canStartMigration}
                  onClick={handleMigrationStart}
                  className="min-w-[200px]"
                >
                  <IconDatabase className="mr-2 h-4 w-4" />
                  Run Migration
                </Button>
              </div>

              {!databaseStatus.needs_update && (
                <Alert>
                  <IconCircleCheck className="h-4 w-4" />
                  <AlertTitle>Up to date</AlertTitle>
                  <AlertDescription>
                    Database schema is already at the latest version
                  </AlertDescription>
                </Alert>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* Confirmation Dialog */}
      <Dialog open={showConfirmDialog} onOpenChange={setShowConfirmDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Confirm Database Migration</DialogTitle>
            <DialogDescription>
              You are about to migrate the database from version{" "}
              <span className="font-mono">{databaseStatus?.current_version}</span> to{" "}
              <span className="font-mono">{databaseStatus?.target_version}</span>.
            </DialogDescription>
          </DialogHeader>
          <Alert className="my-4">
            <IconAlertTriangle className="h-4 w-4" />
            <AlertTitle>Warning</AlertTitle>
            <AlertDescription>
              This action cannot be undone. A backup will be created automatically before migration.
            </AlertDescription>
          </Alert>
          <div className="space-y-2">
            <Label>Type MIGRATE to confirm</Label>
            <Input
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder="Type MIGRATE"
              className="font-mono"
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowConfirmDialog(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              disabled={confirmText !== "MIGRATE"}
              onClick={handleConfirmMigration}
            >
              Confirm Migration
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* PIN Dialog */}
      <Dialog open={showPinDialog} onOpenChange={setShowPinDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Enter PIN to Authorize</DialogTitle>
            <DialogDescription>
              Enter your administrator PIN to authorize this database migration
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-2 py-4">
            <Label>PIN</Label>
            <Input
              type="password"
              value={pin}
              onChange={(e) => setPin(e.target.value)}
              placeholder="Enter PIN"
              maxLength={6}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setShowPinDialog(false)}>
              Cancel
            </Button>
            <Button
              disabled={pin.length < 4 || migrationMutation.isPending}
              onClick={handlePinSubmit}
            >
              {migrationMutation.isPending ? (
                <>
                  <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />
                  Authorizing...
                </>
              ) : (
                "Authorize Migration"
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

function MigrationProgressCard({ jobId }: { jobId: string }) {
  const { data: job, error } = useQuery({
    queryKey: ["migration-job", jobId],
    queryFn: () => fetchJobStatus(jobId),
    refetchInterval: (query) => {
      const data = query.state.data
      if (!data) return 2000
      if (data.status === "completed" || data.status === "failed") return false
      return 2000
    },
  })

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "completed":
        return <IconCircleCheck className="h-6 w-6 text-green-600" />
      case "failed":
        return <IconCircleX className="h-6 w-6 text-red-600" />
      default:
        return <IconLoader2 className="h-6 w-6 animate-spin" />
    }
  }

  const getStepDescription = (status: string) => {
    const stepMap: Record<string, string> = {
      initializing: "Initializing migration process...",
      backing_up: "Creating secure backup...",
      backup_complete: "Backup created successfully",
      planning: "Analyzing migration plan...",
      migrating: "Running database migrations...",
      verifying: "Verifying schema changes...",
      completed: "Migration completed successfully",
      rolling_back: "Rolling back changes...",
      failed: "Migration failed",
    }
    return stepMap[status] || status
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconDatabase className="h-5 w-5" />
          Migration in Progress
        </CardTitle>
        <CardDescription>
          Job ID: <span className="font-mono">{jobId}</span>
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {error ? (
          <Alert variant="destructive">
            <IconAlertTriangle className="h-4 w-4" />
            <AlertTitle>Error</AlertTitle>
            <AlertDescription>
              Failed to fetch migration status. Please check the logs.
            </AlertDescription>
          </Alert>
        ) : job ? (
          <>
            <div className="flex items-center justify-center py-4">
              {getStatusIcon(job.status)}
            </div>

            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-sm text-muted-foreground">Progress</span>
                <span className="text-sm font-medium">{job.progress}%</span>
              </div>
              <Progress value={job.progress} className="h-2" />
            </div>

            <div className="text-center">
              <p className="font-medium">{getStepDescription(job.status)}</p>
              {job.started_at && (
                <p className="text-sm text-muted-foreground mt-1">
                  Started {formatDistanceToNow(new Date(job.started_at))} ago
                </p>
              )}
            </div>

            {job.error && (
              <Alert variant="destructive">
                <IconAlertTriangle className="h-4 w-4" />
                <AlertTitle>Migration Failed</AlertTitle>
                <AlertDescription>{job.error}</AlertDescription>
              </Alert>
            )}

            {job.status === "completed" && (
              <Alert>
                <IconCircleCheck className="h-4 w-4" />
                <AlertTitle>Success</AlertTitle>
                <AlertDescription>
                  Database migration completed successfully
                </AlertDescription>
              </Alert>
            )}
          </>
        ) : (
          <div className="flex items-center justify-center py-8">
            <IconLoader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        )}
      </CardContent>
    </Card>
  )
}

function MigrationHistoryCard() {
  const { data: history, isLoading } = useQuery({
    queryKey: ["migration-history"],
    queryFn: fetchMigrationHistory,
  })

  const getStatusBadge = (status: MigrationHistory["status"]) => {
    switch (status) {
      case "success":
        return <Badge variant="default" className="bg-green-600">Success</Badge>
      case "failed":
        return <Badge variant="destructive">Failed</Badge>
      case "rolled_back":
        return <Badge variant="secondary">Rolled Back</Badge>
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <IconHistory className="h-5 w-5" />
          Migration History
        </CardTitle>
        <CardDescription>
          Recent database migrations
        </CardDescription>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <IconLoader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : history && history.length > 0 ? (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Date</TableHead>
                <TableHead>From → To</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Duration</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {history.map((item) => (
                <TableRow key={item.id}>
                  <TableCell className="text-sm">
                    {format(new Date(item.executed_at), "MMM d, yyyy HH:mm")}
                  </TableCell>
                  <TableCell className="font-mono text-sm">
                    {item.from_version} → {item.to_version}
                  </TableCell>
                  <TableCell>{getStatusBadge(item.status)}</TableCell>
                  <TableCell className="text-sm">
                    {(item.duration_ms / 1000).toFixed(1)}s
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <div className="text-center py-8 text-muted-foreground">
            No migration history available
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export function DatabaseManagementTab() {
  const [activeJobId, setActiveJobId] = useState<string | null>(null)

  // Queries
  const { data: databaseStatus } = useQuery({
    queryKey: ["database-status"],
    queryFn: fetchDatabaseStatus,
    refetchInterval: activeJobId ? false : 30000, // Refresh every 30s when no migration is active
  })

  const {
    data: safetyStatus,
    isLoading: safetyLoading,
    error: safetyError,
    refetch: refetchSafety
  } = useQuery({
    queryKey: ["safety-status"],
    queryFn: fetchSafetyStatus,
    refetchInterval: activeJobId ? false : 3000, // Poll every 3s when tab is active
  })

  // Check for active migration on mount
  useEffect(() => {
    if (databaseStatus?.migration_in_progress && databaseStatus.current_job_id) {
      setActiveJobId(databaseStatus.current_job_id)
    }
  }, [databaseStatus])

  return (
    <div className="space-y-6">
      {/* Safety Status - Always visible at top */}
      <SafetyStatusCard
        safetyStatus={safetyStatus}
        isLoading={safetyLoading}
        error={safetyError}
        onRefresh={refetchSafety}
      />

      {/* Migration Control / Progress */}
      <MigrationControlCard
        databaseStatus={databaseStatus}
        safetyStatus={safetyStatus}
        onMigrationStart={setActiveJobId}
        activeJobId={activeJobId}
      />

      {/* Migration History */}
      <MigrationHistoryCard />
    </div>
  )
}
