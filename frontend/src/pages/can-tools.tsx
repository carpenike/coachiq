/**
 * CAN Tools Page
 *
 * Advanced CAN bus utilities for testing, diagnostics, and analysis.
 * Currently includes message injection tool with more tools planned.
 */

import { useState } from 'react';
import { AppLayout } from '@/components/app-layout';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Separator } from '@/components/ui/separator';
import { Slider } from '@/components/ui/slider';
import { Switch } from '@/components/ui/switch';
import {
  IconAlertTriangle,
  IconAlertCircle,
  IconBolt,
  IconSend,
  IconPlayerStop,
  IconPlayerRecord,
  IconPlayerPause,
  IconPlayerPlay,
  IconDownload,
  IconUpload,
  IconTrash,
  IconShield,
  IconInfoCircle,
  IconCheck,
  IconFile,
  IconClock,
} from '@tabler/icons-react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiPost, apiGet, apiDelete, apiPut } from '@/api/client';
import { cn } from '@/lib/utils';
import * as canRecorder from '@/api/can-recorder';
import * as canAnalyzer from '@/api/can-analyzer';
import * as canFilter from '@/api/can-filter';

// Types
interface InjectionRequest {
  can_id: number;
  data: string;
  interface: string;
  mode: 'single' | 'burst' | 'periodic';
  count?: number;
  interval?: number;
  duration?: number;
  priority?: number;
  source_address?: number;
  destination_address?: number;
  description?: string;
  reason?: string;
}

interface InjectionResponse {
  success: boolean;
  messages_sent: number;
  messages_failed: number;
  duration: number;
  success_rate: number;
  warnings: string[];
  error?: string;
}

interface InjectorStatus {
  enabled: boolean;
  safety_level: string;
  statistics: {
    total_injected: number;
    total_failed: number;
    dangerous_blocked: number;
    rate_limited: number;
  };
  active_injections: number;
  active_interfaces: string[];
}

interface MessageTemplate {
  name: string;
  pgn: number;
  can_id: number;
  data: string;
  description: string;
}

export default function CANToolsPage() {
  const [selectedTab, setSelectedTab] = useState('injector');
  const queryClient = useQueryClient();

  // Recorder state
  const [recordingName, setRecordingName] = useState('');
  const [recordingDescription, setRecordingDescription] = useState('');
  const [recordingFormat, setRecordingFormat] = useState<'json' | 'csv' | 'binary' | 'candump'>('json');
  const [selectedRecording, setSelectedRecording] = useState<string>('');
  const [replaySpeed, setReplaySpeed] = useState(1.0);
  const [replayLoop, setReplayLoop] = useState(false);

  // Analyzer state
  const [analyzerFilter, setAnalyzerFilter] = useState<string>('');
  const [selectedProtocol, setSelectedProtocol] = useState<string>('');
  const [manualCanId, setManualCanId] = useState('');
  const [manualData, setManualData] = useState('');

  // Filter state
  const [selectedFilterRule, setSelectedFilterRule] = useState<string>('');
  const [filterRuleName, setFilterRuleName] = useState('');
  const [filterConditions, setFilterConditions] = useState<canFilter.FilterCondition[]>([
    {
      field: canFilter.FilterField.CAN_ID,
      operator: canFilter.FilterOperator.EQUALS,
      value: '',
    },
  ]);

  // Form state
  const [canIdInput, setCanIdInput] = useState('');
  const [dataInput, setDataInput] = useState('');
  const [interfaceInput, setInterfaceInput] = useState('can0');
  const [mode, setMode] = useState<InjectionRequest['mode']>('single');
  const [count, setCount] = useState('1');
  const [interval, setInterval] = useState('1.0');
  const [duration, setDuration] = useState('0');
  const [description, setDescription] = useState('');
  const [reason, setReason] = useState('');
  const [j1939Pgn, setJ1939Pgn] = useState('');
  const [j1939Priority, setJ1939Priority] = useState('6');
  const [j1939SourceAddr, setJ1939SourceAddr] = useState('254');
  const [j1939DestAddr, setJ1939DestAddr] = useState('255');

  // Fetch injector status
  const statusQuery = useQuery({
    queryKey: ['can-tools', 'status'],
    queryFn: () => apiGet<InjectorStatus>('/api/can-tools/status'),
    refetchInterval: 5000,
  });

  // Fetch message templates
  const templatesQuery = useQuery({
    queryKey: ['can-tools', 'templates'],
    queryFn: () => apiGet<MessageTemplate[]>('/api/can-tools/templates'),
  });

  // Fetch recorder status
  const recorderStatusQuery = useQuery({
    queryKey: ['can-recorder', 'status'],
    queryFn: canRecorder.getRecorderStatus,
    refetchInterval: 1000,
  });

  // Fetch recordings list
  const recordingsQuery = useQuery({
    queryKey: ['can-recorder', 'list'],
    queryFn: canRecorder.listRecordings,
    refetchInterval: 5000,
  });

  // Analyzer queries
  const analyzerStatsQuery = useQuery({
    queryKey: ['can-analyzer', 'statistics'],
    queryFn: canAnalyzer.getStatistics,
    refetchInterval: 1000,
  });

  const analyzerMessagesQuery = useQuery({
    queryKey: ['can-analyzer', 'messages', analyzerFilter, selectedProtocol],
    queryFn: () => canAnalyzer.getRecentMessages({
      limit: 100,
      ...(selectedProtocol && { protocol: selectedProtocol }),
      ...(analyzerFilter && { can_id: analyzerFilter }),
    }),
    refetchInterval: 1000,
  });

  const analyzerPatternsQuery = useQuery({
    queryKey: ['can-analyzer', 'patterns'],
    queryFn: () => canAnalyzer.getCommunicationPatterns(),
    refetchInterval: 5000,
  });

  const analyzerProtocolsQuery = useQuery({
    queryKey: ['can-analyzer', 'protocols'],
    queryFn: canAnalyzer.getDetectedProtocols,
    refetchInterval: 5000,
  });

  // Filter queries
  const filterStatusQuery = useQuery({
    queryKey: ['can-filter', 'status'],
    queryFn: canFilter.getFilterStatus,
    refetchInterval: 2000,
  });

  const filterRulesQuery = useQuery({
    queryKey: ['can-filter', 'rules'],
    queryFn: () => canFilter.listFilterRules(),
    refetchInterval: 5000,
  });

  const capturedMessagesQuery = useQuery({
    queryKey: ['can-filter', 'captured'],
    queryFn: () => canFilter.getCapturedMessages(100),
    refetchInterval: 1000,
  });

  // Injection mutation
  const injectMutation = useMutation({
    mutationFn: (request: InjectionRequest) =>
      apiPost<InjectionResponse>('/api/can-tools/inject', request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['can-tools', 'status'] });
    },
  });

  // J1939 injection mutation
  const j1939InjectMutation = useMutation({
    mutationFn: (request: {
      pgn: number;
      data: string;
      priority: number;
      source_address: number;
      destination_address: number;
      interface: string;
      mode: InjectionRequest['mode'];
    }) => apiPost<InjectionResponse>('/api/can-tools/inject/j1939', request),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['can-tools', 'status'] });
    },
  });

  // Stop injection mutation
  const stopMutation = useMutation({
    mutationFn: (pattern?: string) => {
      const url = pattern
        ? `/api/can-tools/inject/stop?pattern=${encodeURIComponent(pattern)}`
        : '/api/can-tools/inject/stop';
      return apiDelete<{ success: boolean; stopped_count: number }>(url);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['can-tools', 'status'] });
    },
  });

  // Safety level mutation
  const safetyMutation = useMutation({
    mutationFn: (safety_level: string) =>
      apiPut<{ success: string; message: string }>('/api/can-tools/safety', { safety_level }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['can-tools', 'status'] });
    },
  });

  // Recorder mutations
  const startRecordingMutation = useMutation({
    mutationFn: canRecorder.startRecording,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['can-recorder'] });
      setRecordingName('');
      setRecordingDescription('');
    },
  });

  const stopRecordingMutation = useMutation({
    mutationFn: canRecorder.stopRecording,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['can-recorder'] });
    },
  });

  const pauseRecordingMutation = useMutation({
    mutationFn: canRecorder.pauseRecording,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['can-recorder', 'status'] });
    },
  });

  const resumeRecordingMutation = useMutation({
    mutationFn: canRecorder.resumeRecording,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['can-recorder', 'status'] });
    },
  });

  const deleteRecordingMutation = useMutation({
    mutationFn: canRecorder.deleteRecording,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['can-recorder', 'list'] });
    },
  });

  const startReplayMutation = useMutation({
    mutationFn: canRecorder.startReplay,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['can-recorder', 'status'] });
    },
  });

  const stopReplayMutation = useMutation({
    mutationFn: canRecorder.stopReplay,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['can-recorder', 'status'] });
    },
  });

  // Analyzer mutations
  const analyzeMessageMutation = useMutation({
    mutationFn: canAnalyzer.analyzeMessage,
  });

  const clearAnalyzerMutation = useMutation({
    mutationFn: canAnalyzer.clearAnalyzer,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['can-analyzer'] });
    },
  });

  // Filter mutations
  const createFilterRuleMutation = useMutation({
    mutationFn: canFilter.createFilterRule,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['can-filter'] });
      setFilterRuleName('');
      setFilterConditions([{
        field: canFilter.FilterField.CAN_ID,
        operator: canFilter.FilterOperator.EQUALS,
        value: '',
      }]);
    },
  });

  const deleteFilterRuleMutation = useMutation({
    mutationFn: canFilter.deleteFilterRule,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['can-filter'] });
    },
  });

  const clearCaptureBufferMutation = useMutation({
    mutationFn: canFilter.clearCaptureBuffer,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['can-filter', 'captured'] });
    },
  });

  const handleInject = () => {
    try {
      // Parse CAN ID
      const canId = canIdInput.startsWith('0x')
        ? parseInt(canIdInput, 16)
        : parseInt(canIdInput, 10);

      if (isNaN(canId)) {
        throw new Error('Invalid CAN ID');
      }

      // Validate data
      const cleanData = dataInput.replace(/\s/g, '').toUpperCase();
      if (!/^[0-9A-F]*$/.test(cleanData) || cleanData.length % 2 !== 0) {
        throw new Error('Invalid hex data');
      }

      const request: InjectionRequest = {
        can_id: canId,
        data: cleanData,
        interface: interfaceInput,
        mode,
        description,
        reason,
      };

      // Add mode-specific parameters
      if (mode === 'burst') {
        request.count = parseInt(count);
      } else if (mode === 'periodic') {
        request.interval = parseFloat(interval);
        request.duration = parseFloat(duration);
      }

      injectMutation.mutate(request);
    } catch (error) {
      console.error('Injection error:', error);
    }
  };

  const handleJ1939Inject = () => {
    try {
      const pgn = parseInt(j1939Pgn, 16);
      if (isNaN(pgn)) {
        throw new Error('Invalid PGN');
      }

      const cleanData = dataInput.replace(/\s/g, '').toUpperCase();
      if (!/^[0-9A-F]*$/.test(cleanData) || cleanData.length % 2 !== 0) {
        throw new Error('Invalid hex data');
      }

      j1939InjectMutation.mutate({
        pgn,
        data: cleanData,
        priority: parseInt(j1939Priority),
        source_address: parseInt(j1939SourceAddr),
        destination_address: parseInt(j1939DestAddr),
        interface: interfaceInput,
        mode,
      });
    } catch (error) {
      console.error('J1939 injection error:', error);
    }
  };

  const applyTemplate = (template: MessageTemplate) => {
    setCanIdInput(`0x${template.can_id.toString(16).toUpperCase()}`);
    setDataInput(template.data);
    setDescription(template.description);
  };

  return (
    <AppLayout pageTitle="CAN Tools">
      <div className="flex-1 space-y-4 p-4 md:p-8 pt-6">
        {/* Header */}
        <div className="flex justify-between items-center">
          <div>
            <h2 className="text-3xl font-bold tracking-tight">CAN Tools</h2>
            <p className="text-muted-foreground">
              Advanced CAN bus utilities for testing and diagnostics
            </p>
          </div>
          <div className="flex items-center gap-4">
            {statusQuery.data && (
              <Badge variant={statusQuery.data.enabled ? 'default' : 'secondary'}>
                {statusQuery.data.enabled ? 'Enabled' : 'Disabled'}
              </Badge>
            )}
          </div>
        </div>

        {/* Safety Warning */}
        <Alert>
          <IconAlertTriangle className="h-4 w-4" />
          <AlertTitle>Safety Warning</AlertTitle>
          <AlertDescription>
            CAN message injection can affect vehicle systems. Use with caution and only for
            legitimate testing and diagnostics. Always ensure vehicle is in a safe state.
          </AlertDescription>
        </Alert>

        {/* Status Bar */}
        {statusQuery.data && (
          <Card>
            <CardHeader className="pb-3">
              <div className="flex items-center justify-between">
                <CardTitle className="text-base">Injector Status</CardTitle>
                <div className="flex items-center gap-2">
                  <Label>Safety Level:</Label>
                  <Select
                    value={statusQuery.data.safety_level}
                    onValueChange={(value) => safetyMutation.mutate(value)}
                  >
                    <SelectTrigger className="w-32">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="strict">
                        <div className="flex items-center gap-2">
                          <IconShield className="h-4 w-4" />
                          Strict
                        </div>
                      </SelectItem>
                      <SelectItem value="moderate">
                        <div className="flex items-center gap-2">
                          <IconAlertCircle className="h-4 w-4" />
                          Moderate
                        </div>
                      </SelectItem>
                      <SelectItem value="permissive">
                        <div className="flex items-center gap-2">
                          <IconInfoCircle className="h-4 w-4" />
                          Permissive
                        </div>
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                <div>
                  <p className="text-muted-foreground">Total Injected</p>
                  <p className="font-medium">{statusQuery.data.statistics.total_injected}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Failed</p>
                  <p className="font-medium">{statusQuery.data.statistics.total_failed}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Blocked</p>
                  <p className="font-medium">{statusQuery.data.statistics.dangerous_blocked}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Active</p>
                  <p className="font-medium">{statusQuery.data.active_injections}</p>
                </div>
              </div>
              {statusQuery.data.active_injections > 0 && (
                <div className="mt-4">
                  <Button
                    variant="destructive"
                    size="sm"
                    onClick={() => stopMutation.mutate(undefined)}
                  >
                    <IconPlayerStop className="mr-2 h-4 w-4" />
                    Stop All Injections
                  </Button>
                </div>
              )}
            </CardContent>
          </Card>
        )}

        {/* Main Tabs */}
        <Tabs value={selectedTab} onValueChange={setSelectedTab} className="space-y-4">
          <TabsList>
            <TabsTrigger value="injector">Message Injector</TabsTrigger>
            <TabsTrigger value="recorder">Recorder</TabsTrigger>
            <TabsTrigger value="analyzer">Analyzer</TabsTrigger>
            <TabsTrigger value="filter">Filter</TabsTrigger>
            <TabsTrigger value="j1939">J1939 Helper</TabsTrigger>
            <TabsTrigger value="templates">Templates</TabsTrigger>
          </TabsList>

          <TabsContent value="injector" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>CAN Message Injection</CardTitle>
                <CardDescription>
                  Send custom CAN messages for testing and diagnostics
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="can-id">CAN ID (hex or decimal)</Label>
                    <Input
                      id="can-id"
                      placeholder="0x18FEEE00 or 419360256"
                      value={canIdInput}
                      onChange={(e) => setCanIdInput(e.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="interface">Interface</Label>
                    <Select value={interfaceInput} onValueChange={setInterfaceInput}>
                      <SelectTrigger id="interface">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="can0">can0</SelectItem>
                        <SelectItem value="can1">can1</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="data">Data (hex)</Label>
                  <Input
                    id="data"
                    placeholder="01 02 03 04 05 06 07 08"
                    value={dataInput}
                    onChange={(e) => setDataInput(e.target.value)}
                  />
                  <p className="text-xs text-muted-foreground">
                    Enter up to 8 bytes of hex data (spaces optional)
                  </p>
                </div>

                <Separator />

                <div className="space-y-2">
                  <Label>Injection Mode</Label>
                  <RadioGroup value={mode} onValueChange={(v) => setMode(v as any)}>
                    <div className="flex items-center space-x-2">
                      <RadioGroupItem value="single" id="single" />
                      <Label htmlFor="single">Single - Send one message</Label>
                    </div>
                    <div className="flex items-center space-x-2">
                      <RadioGroupItem value="burst" id="burst" />
                      <Label htmlFor="burst">Burst - Send multiple messages quickly</Label>
                    </div>
                    <div className="flex items-center space-x-2">
                      <RadioGroupItem value="periodic" id="periodic" />
                      <Label htmlFor="periodic">Periodic - Send messages at intervals</Label>
                    </div>
                  </RadioGroup>
                </div>

                {mode === 'burst' && (
                  <div className="space-y-2">
                    <Label htmlFor="count">Message Count</Label>
                    <Input
                      id="count"
                      type="number"
                      min="1"
                      max="1000"
                      value={count}
                      onChange={(e) => setCount(e.target.value)}
                    />
                  </div>
                )}

                {mode === 'periodic' && (
                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-2">
                      <Label htmlFor="interval">Interval (seconds)</Label>
                      <Input
                        id="interval"
                        type="number"
                        min="0.01"
                        step="0.1"
                        value={interval}
                        onChange={(e) => setInterval(e.target.value)}
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="duration">Duration (0=infinite)</Label>
                      <Input
                        id="duration"
                        type="number"
                        min="0"
                        step="1"
                        value={duration}
                        onChange={(e) => setDuration(e.target.value)}
                      />
                    </div>
                  </div>
                )}

                <Separator />

                <div className="space-y-2">
                  <Label htmlFor="description">Description (optional)</Label>
                  <Input
                    id="description"
                    placeholder="What does this message do?"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="reason">Reason (optional)</Label>
                  <Textarea
                    id="reason"
                    placeholder="Why are you sending this message?"
                    value={reason}
                    onChange={(e) => setReason(e.target.value)}
                    rows={2}
                  />
                </div>

                <div className="flex gap-2">
                  <Button
                    onClick={handleInject}
                    disabled={injectMutation.isPending || !canIdInput || !dataInput}
                  >
                    <IconSend className="mr-2 h-4 w-4" />
                    Inject Message
                  </Button>
                </div>

                {/* Results */}
                {injectMutation.data && (
                  <Alert className={injectMutation.data.success ? '' : 'border-destructive'}>
                    <IconCheck className="h-4 w-4" />
                    <AlertTitle>
                      {injectMutation.data.success ? 'Success' : 'Failed'}
                    </AlertTitle>
                    <AlertDescription>
                      <div className="space-y-1">
                        <p>Messages sent: {injectMutation.data.messages_sent}</p>
                        <p>Success rate: {injectMutation.data.success_rate.toFixed(1)}%</p>
                        <p>Duration: {injectMutation.data.duration.toFixed(3)}s</p>
                        {injectMutation.data.warnings.length > 0 && (
                          <div className="mt-2">
                            <p className="font-medium">Warnings:</p>
                            <ul className="list-disc list-inside">
                              {injectMutation.data.warnings.map((w, i) => (
                                <li key={i}>{w}</li>
                              ))}
                            </ul>
                          </div>
                        )}
                        {injectMutation.data.error && (
                          <p className="text-destructive">Error: {injectMutation.data.error}</p>
                        )}
                      </div>
                    </AlertDescription>
                  </Alert>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="recorder" className="space-y-4">
            {/* Recorder Status */}
            {recorderStatusQuery.data && (
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle>Recorder Status</CardTitle>
                    <Badge variant={recorderStatusQuery.data.state === 'idle' ? 'secondary' : 'default'}>
                      {recorderStatusQuery.data.state}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                    <div>
                      <p className="text-muted-foreground">Buffer Usage</p>
                      <p className="font-medium">
                        {recorderStatusQuery.data.buffer_size} / {recorderStatusQuery.data.buffer_capacity}
                      </p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Messages</p>
                      <p className="font-medium">{recorderStatusQuery.data.messages_recorded}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Dropped</p>
                      <p className="font-medium">{recorderStatusQuery.data.messages_dropped}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Size</p>
                      <p className="font-medium">
                        {(recorderStatusQuery.data.bytes_recorded / 1024 / 1024).toFixed(2)} MB
                      </p>
                    </div>
                  </div>

                  {recorderStatusQuery.data.current_session && (
                    <div className="mt-4 p-3 bg-muted rounded-lg">
                      <p className="font-medium">{recorderStatusQuery.data.current_session.name}</p>
                      <p className="text-sm text-muted-foreground">
                        {recorderStatusQuery.data.current_session.description}
                      </p>
                      <div className="flex gap-4 mt-2 text-xs">
                        <span>Started: {new Date(recorderStatusQuery.data.current_session.start_time).toLocaleTimeString()}</span>
                        <span>Messages: {recorderStatusQuery.data.current_session.message_count}</span>
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

            {/* Recording Controls */}
            <Card>
              <CardHeader>
                <CardTitle>Recording Controls</CardTitle>
                <CardDescription>
                  Record CAN bus traffic for later analysis and replay
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {recorderStatusQuery.data?.state === 'idle' ? (
                  <>
                    <div className="space-y-2">
                      <Label htmlFor="recording-name">Recording Name</Label>
                      <Input
                        id="recording-name"
                        placeholder="My Recording"
                        value={recordingName}
                        onChange={(e) => setRecordingName(e.target.value)}
                      />
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="recording-description">Description (optional)</Label>
                      <Textarea
                        id="recording-description"
                        placeholder="What is this recording for?"
                        value={recordingDescription}
                        onChange={(e) => setRecordingDescription(e.target.value)}
                        rows={2}
                      />
                    </div>

                    <div className="space-y-2">
                      <Label htmlFor="recording-format">Format</Label>
                      <Select value={recordingFormat} onValueChange={(v: any) => setRecordingFormat(v)}>
                        <SelectTrigger id="recording-format">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="json">JSON (Human readable)</SelectItem>
                          <SelectItem value="csv">CSV (Spreadsheet)</SelectItem>
                          <SelectItem value="binary">Binary (Compact)</SelectItem>
                          <SelectItem value="candump">Candump (socketcan)</SelectItem>
                        </SelectContent>
                      </Select>
                    </div>

                    <Button
                      onClick={() => startRecordingMutation.mutate({
                        name: recordingName || 'Unnamed Recording',
                        description: recordingDescription,
                        format: recordingFormat,
                      })}
                      disabled={startRecordingMutation.isPending || !recordingName}
                      className="w-full"
                    >
                      <IconPlayerRecord className="mr-2 h-4 w-4" />
                      Start Recording
                    </Button>
                  </>
                ) : recorderStatusQuery.data?.state === 'recording' ? (
                  <div className="flex gap-2">
                    <Button
                      onClick={() => pauseRecordingMutation.mutate()}
                      disabled={pauseRecordingMutation.isPending}
                      variant="outline"
                    >
                      <IconPlayerPause className="mr-2 h-4 w-4" />
                      Pause
                    </Button>
                    <Button
                      onClick={() => stopRecordingMutation.mutate()}
                      disabled={stopRecordingMutation.isPending}
                      variant="destructive"
                    >
                      <IconPlayerStop className="mr-2 h-4 w-4" />
                      Stop Recording
                    </Button>
                  </div>
                ) : recorderStatusQuery.data?.state === 'paused' ? (
                  <div className="flex gap-2">
                    <Button
                      onClick={() => resumeRecordingMutation.mutate()}
                      disabled={resumeRecordingMutation.isPending}
                    >
                      <IconPlayerPlay className="mr-2 h-4 w-4" />
                      Resume
                    </Button>
                    <Button
                      onClick={() => stopRecordingMutation.mutate()}
                      disabled={stopRecordingMutation.isPending}
                      variant="destructive"
                    >
                      <IconPlayerStop className="mr-2 h-4 w-4" />
                      Stop Recording
                    </Button>
                  </div>
                ) : (
                  <Button
                    onClick={() => stopReplayMutation.mutate()}
                    disabled={stopReplayMutation.isPending}
                    variant="destructive"
                    className="w-full"
                  >
                    <IconPlayerStop className="mr-2 h-4 w-4" />
                    Stop Replay
                  </Button>
                )}
              </CardContent>
            </Card>

            {/* Recordings List */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>Recordings</CardTitle>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => recordingsQuery.refetch()}
                  >
                    Refresh
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {recordingsQuery.data?.map((recording) => (
                    <div
                      key={recording.filename}
                      className={cn(
                        "flex items-center justify-between p-3 rounded-lg border",
                        selectedRecording === recording.filename && "bg-accent"
                      )}
                    >
                      <div
                        className="flex-1 cursor-pointer"
                        onClick={() => setSelectedRecording(recording.filename)}
                      >
                        <div className="flex items-center gap-2">
                          <IconFile className="h-4 w-4" />
                          <p className="font-medium">{recording.filename}</p>
                        </div>
                        <div className="flex gap-4 text-xs text-muted-foreground mt-1">
                          <span>{recording.size_mb} MB</span>
                          <span>{recording.format.toUpperCase()}</span>
                          <span>{new Date(recording.modified).toLocaleDateString()}</span>
                        </div>
                      </div>
                      <div className="flex gap-1">
                        <Button
                          size="icon"
                          variant="ghost"
                          asChild
                        >
                          <a
                            href={canRecorder.getDownloadUrl(recording.filename)}
                            download
                          >
                            <IconDownload className="h-4 w-4" />
                          </a>
                        </Button>
                        <Button
                          size="icon"
                          variant="ghost"
                          onClick={() => {
                            if (confirm(`Delete ${recording.filename}?`)) {
                              deleteRecordingMutation.mutate(recording.filename);
                            }
                          }}
                        >
                          <IconTrash className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  ))}

                  {recordingsQuery.data?.length === 0 && (
                    <p className="text-center text-muted-foreground py-4">
                      No recordings found
                    </p>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* Replay Controls */}
            {selectedRecording && recorderStatusQuery.data?.state === 'idle' && (
              <Card>
                <CardHeader>
                  <CardTitle>Replay Options</CardTitle>
                  <CardDescription>
                    Configure replay settings for: {selectedRecording}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-2">
                    <Label>Speed Factor: {replaySpeed}x</Label>
                    <Slider
                      value={[replaySpeed]}
                      onValueChange={([v]) => setReplaySpeed(v || 1.0)}
                      min={0.1}
                      max={10}
                      step={0.1}
                    />
                  </div>

                  <div className="flex items-center space-x-2">
                    <Switch
                      id="replay-loop"
                      checked={replayLoop}
                      onCheckedChange={setReplayLoop}
                    />
                    <Label htmlFor="replay-loop">Loop replay</Label>
                  </div>

                  <Button
                    onClick={() => startReplayMutation.mutate({
                      filename: selectedRecording,
                      options: {
                        speed_factor: replaySpeed,
                        loop: replayLoop,
                      },
                    })}
                    disabled={startReplayMutation.isPending}
                    className="w-full"
                  >
                    <IconPlayerPlay className="mr-2 h-4 w-4" />
                    Start Replay
                  </Button>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          <TabsContent value="analyzer" className="space-y-4">
            {/* Analyzer Statistics */}
            {analyzerStatsQuery.data && (
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle>Protocol Analysis</CardTitle>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => clearAnalyzerMutation.mutate()}
                    >
                      Clear
                    </Button>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
                    <div>
                      <p className="text-muted-foreground">Messages</p>
                      <p className="font-medium">{analyzerStatsQuery.data.total_messages}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Rate</p>
                      <p className="font-medium">{analyzerStatsQuery.data.overall_message_rate.toFixed(1)} msg/s</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Bus Load</p>
                      <p className="font-medium">{analyzerStatsQuery.data.bus_utilization_percent.toFixed(1)}%</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Patterns</p>
                      <p className="font-medium">{analyzerStatsQuery.data.detected_patterns}</p>
                    </div>
                  </div>

                  {/* Protocol breakdown */}
                  <div className="mt-4 space-y-2">
                    <p className="text-sm font-medium">Detected Protocols:</p>
                    {Object.entries(analyzerStatsQuery.data.protocols).map(([protocol, stats]) => (
                      <div key={protocol} className="flex items-center justify-between text-sm">
                        <span className="capitalize">{protocol}</span>
                        <div className="flex items-center gap-4">
                          <Badge variant="secondary">{stats.unique_ids} IDs</Badge>
                          <span className="text-muted-foreground">{stats.percentage.toFixed(1)}%</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Manual Analysis */}
            <Card>
              <CardHeader>
                <CardTitle>Manual Analysis</CardTitle>
                <CardDescription>
                  Analyze a specific CAN message
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="manual-can-id">CAN ID (hex)</Label>
                    <Input
                      id="manual-can-id"
                      placeholder="0x18FEEE00"
                      value={manualCanId}
                      onChange={(e) => setManualCanId(e.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="manual-data">Data (hex)</Label>
                    <Input
                      id="manual-data"
                      placeholder="01 02 03 04 05 06 07 08"
                      value={manualData}
                      onChange={(e) => setManualData(e.target.value)}
                    />
                  </div>
                </div>

                <Button
                  onClick={() => analyzeMessageMutation.mutate({
                    can_id: manualCanId,
                    data: manualData.replace(/\s/g, ''),
                  })}
                  disabled={analyzeMessageMutation.isPending || !manualCanId || !manualData}
                >
                  Analyze Message
                </Button>

                {analyzeMessageMutation.data && (
                  <div className="mt-4 p-3 bg-muted rounded-lg space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-medium">Protocol: {analyzeMessageMutation.data.protocol}</span>
                      <Badge>{analyzeMessageMutation.data.message_type}</Badge>
                    </div>
                    {analyzeMessageMutation.data.description && (
                      <p className="text-sm">{analyzeMessageMutation.data.description}</p>
                    )}
                    {analyzeMessageMutation.data.decoded_fields.length > 0 && (
                      <div className="space-y-1">
                        <p className="text-sm font-medium">Decoded Fields:</p>
                        {analyzeMessageMutation.data.decoded_fields.map((field, i) => (
                          <div key={i} className="text-xs">
                            {field.name}: {field.value} {field.unit}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>

            {/* Recent Messages */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>Recent Messages</CardTitle>
                  <div className="flex gap-2">
                    <Select value={selectedProtocol} onValueChange={setSelectedProtocol}>
                      <SelectTrigger className="w-32">
                        <SelectValue placeholder="Protocol" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="">All</SelectItem>
                        <SelectItem value="rvc">RV-C</SelectItem>
                        <SelectItem value="j1939">J1939</SelectItem>
                        <SelectItem value="canopen">CANopen</SelectItem>
                        <SelectItem value="unknown">Unknown</SelectItem>
                      </SelectContent>
                    </Select>
                    <Input
                      placeholder="Filter by CAN ID"
                      value={analyzerFilter}
                      onChange={(e) => setAnalyzerFilter(e.target.value)}
                      className="w-40"
                    />
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {analyzerMessagesQuery.data?.map((msg, i) => (
                    <div
                      key={i}
                      className="p-2 rounded border text-xs font-mono hover:bg-accent"
                    >
                      <div className="flex items-center justify-between">
                        <span>{new Date(msg.timestamp * 1000).toLocaleTimeString()}</span>
                        <Badge variant="outline" className="text-xs">{msg.protocol}</Badge>
                      </div>
                      <div className="flex items-center gap-4 mt-1">
                        <span className="text-blue-600">{msg.can_id}</span>
                        <span>{msg.data}</span>
                        {msg.pgn && <span className="text-muted-foreground">PGN: {msg.pgn}</span>}
                      </div>
                      {msg.description && (
                        <p className="text-muted-foreground mt-1">{msg.description}</p>
                      )}
                    </div>
                  ))}

                  {analyzerMessagesQuery.data?.length === 0 && (
                    <p className="text-center text-muted-foreground py-4">
                      No messages found
                    </p>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* Communication Patterns */}
            {analyzerPatternsQuery.data && analyzerPatternsQuery.data.length > 0 && (
              <Card>
                <CardHeader>
                  <CardTitle>Communication Patterns</CardTitle>
                  <CardDescription>
                    Detected patterns in CAN communication
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {analyzerPatternsQuery.data.map((pattern, i) => (
                      <div key={i} className="flex items-center justify-between p-2 rounded border">
                        <div>
                          <span className="font-medium capitalize">{pattern.pattern_type}</span>
                          <div className="text-xs text-muted-foreground">
                            Participants: {pattern.participants.join(', ')}
                          </div>
                        </div>
                        <div className="text-right">
                          {pattern.interval_ms && (
                            <div className="text-sm">{pattern.interval_ms.toFixed(1)} ms</div>
                          )}
                          <div className="text-xs text-muted-foreground">
                            {(pattern.confidence * 100).toFixed(0)}% confidence
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}
          </TabsContent>

          <TabsContent value="filter" className="space-y-4">
            {/* Filter Status */}
            {filterStatusQuery.data && (
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle>Message Filtering</CardTitle>
                    <Badge variant={filterStatusQuery.data.enabled ? 'default' : 'secondary'}>
                      {filterStatusQuery.data.active_rules} / {filterStatusQuery.data.total_rules} Active
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent>
                  <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-sm">
                    <div>
                      <p className="text-muted-foreground">Processed</p>
                      <p className="font-medium">{filterStatusQuery.data.statistics.messages_processed}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Passed</p>
                      <p className="font-medium">{filterStatusQuery.data.statistics.messages_passed}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Blocked</p>
                      <p className="font-medium">{filterStatusQuery.data.statistics.messages_blocked}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Captured</p>
                      <p className="font-medium">{filterStatusQuery.data.statistics.messages_captured}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground">Alerts</p>
                      <p className="font-medium">{filterStatusQuery.data.statistics.alerts_sent}</p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Create Filter Rule */}
            <Card>
              <CardHeader>
                <CardTitle>Create Filter Rule</CardTitle>
                <CardDescription>
                  Define conditions to filter or monitor specific CAN messages
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="filter-name">Rule Name</Label>
                  <Input
                    id="filter-name"
                    placeholder="My Filter Rule"
                    value={filterRuleName}
                    onChange={(e) => setFilterRuleName(e.target.value)}
                  />
                </div>

                <div className="space-y-2">
                  <Label>Conditions</Label>
                  {filterConditions.map((condition, index) => (
                    <div key={index} className="flex gap-2">
                      <Select
                        value={condition.field}
                        onValueChange={(value) => {
                          const newConditions = [...filterConditions];
                          if (newConditions[index]) {
                            newConditions[index].field = value as canFilter.FilterField;
                            setFilterConditions(newConditions);
                          }
                        }}
                      >
                        <SelectTrigger className="w-40">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value={canFilter.FilterField.CAN_ID}>CAN ID</SelectItem>
                          <SelectItem value={canFilter.FilterField.PGN}>PGN</SelectItem>
                          <SelectItem value={canFilter.FilterField.SOURCE_ADDRESS}>Source</SelectItem>
                          <SelectItem value={canFilter.FilterField.DATA}>Data</SelectItem>
                          <SelectItem value={canFilter.FilterField.INTERFACE}>Interface</SelectItem>
                          <SelectItem value={canFilter.FilterField.PROTOCOL}>Protocol</SelectItem>
                        </SelectContent>
                      </Select>

                      <Select
                        value={condition.operator}
                        onValueChange={(value) => {
                          const newConditions = [...filterConditions];
                          if (newConditions[index]) {
                            newConditions[index].operator = value as canFilter.FilterOperator;
                            setFilterConditions(newConditions);
                          }
                        }}
                      >
                        <SelectTrigger className="w-32">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value={canFilter.FilterOperator.EQUALS}>Equals</SelectItem>
                          <SelectItem value={canFilter.FilterOperator.NOT_EQUALS}>Not Equals</SelectItem>
                          <SelectItem value={canFilter.FilterOperator.CONTAINS}>Contains</SelectItem>
                          <SelectItem value={canFilter.FilterOperator.WILDCARD}>Wildcard</SelectItem>
                        </SelectContent>
                      </Select>

                      <Input
                        placeholder="Value"
                        value={condition.value}
                        onChange={(e) => {
                          const newConditions = [...filterConditions];
                          if (newConditions[index]) {
                            newConditions[index].value = e.target.value;
                            setFilterConditions(newConditions);
                          }
                        }}
                        className="flex-1"
                      />

                      <Button
                        size="icon"
                        variant="ghost"
                        onClick={() => {
                          setFilterConditions(filterConditions.filter((_, i) => i !== index));
                        }}
                      >
                        <IconTrash className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}

                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => {
                      setFilterConditions([...filterConditions, {
                        field: canFilter.FilterField.CAN_ID,
                        operator: canFilter.FilterOperator.EQUALS,
                        value: '',
                      }]);
                    }}
                  >
                    Add Condition
                  </Button>
                </div>

                <div className="flex gap-2">
                  <Button
                    onClick={() => {
                      createFilterRuleMutation.mutate({
                        name: filterRuleName,
                        description: '',
                        enabled: true,
                        priority: 50,
                        conditions: filterConditions,
                        condition_logic: 'AND',
                        actions: [
                          { action: canFilter.FilterAction.CAPTURE },
                          { action: canFilter.FilterAction.LOG, level: 'info' },
                        ],
                      });
                    }}
                    disabled={!filterRuleName || filterConditions.length === 0 || createFilterRuleMutation.isPending}
                  >
                    Create Rule
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* Filter Rules List */}
            <Card>
              <CardHeader>
                <CardTitle>Filter Rules</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {filterRulesQuery.data?.map((rule) => (
                    <div
                      key={rule.id}
                      className="flex items-center justify-between p-3 rounded-lg border"
                    >
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <p className="font-medium">{rule.name}</p>
                          <Badge variant={rule.enabled ? 'default' : 'secondary'}>
                            {rule.enabled ? 'Enabled' : 'Disabled'}
                          </Badge>
                          <Badge variant="outline">Priority: {rule.priority}</Badge>
                        </div>
                        <div className="flex gap-4 text-xs text-muted-foreground mt-1">
                          <span>{rule.conditions.length} conditions</span>
                          <span>{rule.statistics.matches} matches</span>
                          {rule.statistics.last_match > 0 && (
                            <span>
                              Last: {new Date(rule.statistics.last_match * 1000).toLocaleTimeString()}
                            </span>
                          )}
                        </div>
                      </div>
                      <Button
                        size="icon"
                        variant="ghost"
                        onClick={() => {
                          if (confirm(`Delete filter rule "${rule.name}"?`)) {
                            deleteFilterRuleMutation.mutate(rule.id);
                          }
                        }}
                        disabled={rule.id.startsWith('system_')}
                      >
                        <IconTrash className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}

                  {filterRulesQuery.data?.length === 0 && (
                    <p className="text-center text-muted-foreground py-4">
                      No filter rules defined
                    </p>
                  )}
                </div>
              </CardContent>
            </Card>

            {/* Captured Messages */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>Captured Messages</CardTitle>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => clearCaptureBufferMutation.mutate()}
                  >
                    Clear
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                <div className="space-y-2 max-h-96 overflow-y-auto">
                  {capturedMessagesQuery.data?.map((msg, i) => (
                    <div
                      key={i}
                      className="p-2 rounded border text-xs font-mono"
                    >
                      <div className="flex items-center justify-between">
                        <span>{new Date(msg.timestamp * 1000).toLocaleTimeString()}</span>
                        <span className="text-muted-foreground">{msg.interface}</span>
                      </div>
                      <div className="flex items-center gap-4 mt-1">
                        <span className="text-blue-600">{msg.can_id}</span>
                        <span>{msg.data}</span>
                        {msg.protocol && <Badge variant="outline" className="text-xs">{msg.protocol}</Badge>}
                      </div>
                    </div>
                  ))}

                  {capturedMessagesQuery.data?.length === 0 && (
                    <p className="text-center text-muted-foreground py-4">
                      No captured messages
                    </p>
                  )}
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="j1939" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>J1939 Message Helper</CardTitle>
                <CardDescription>
                  Simplified J1939 message injection with automatic CAN ID generation
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="j1939-pgn">PGN (hex)</Label>
                    <Input
                      id="j1939-pgn"
                      placeholder="FEEE"
                      value={j1939Pgn}
                      onChange={(e) => setJ1939Pgn(e.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="j1939-priority">Priority (0-7)</Label>
                    <Input
                      id="j1939-priority"
                      type="number"
                      min="0"
                      max="7"
                      value={j1939Priority}
                      onChange={(e) => setJ1939Priority(e.target.value)}
                    />
                  </div>
                </div>

                <div className="grid gap-4 md:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="j1939-sa">Source Address</Label>
                    <Input
                      id="j1939-sa"
                      type="number"
                      min="0"
                      max="255"
                      value={j1939SourceAddr}
                      onChange={(e) => setJ1939SourceAddr(e.target.value)}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="j1939-da">Destination Address</Label>
                    <Input
                      id="j1939-da"
                      type="number"
                      min="0"
                      max="255"
                      value={j1939DestAddr}
                      onChange={(e) => setJ1939DestAddr(e.target.value)}
                    />
                  </div>
                </div>

                <div className="flex gap-2">
                  <Button
                    onClick={handleJ1939Inject}
                    disabled={j1939InjectMutation.isPending || !j1939Pgn || !dataInput}
                  >
                    <IconSend className="mr-2 h-4 w-4" />
                    Send J1939 Message
                  </Button>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value="templates" className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle>Message Templates</CardTitle>
                <CardDescription>
                  Common test messages for quick injection
                </CardDescription>
              </CardHeader>
              <CardContent>
                <div className="space-y-2">
                  {templatesQuery.data?.map((template) => (
                    <div
                      key={template.name}
                      className="flex items-center justify-between p-3 rounded-lg border hover:bg-accent cursor-pointer"
                      onClick={() => applyTemplate(template)}
                    >
                      <div className="space-y-1">
                        <p className="font-medium">{template.name}</p>
                        <p className="text-sm text-muted-foreground">{template.description}</p>
                        <div className="flex gap-4 text-xs">
                          <span>PGN: 0x{template.pgn.toString(16).toUpperCase()}</span>
                          <span>Data: {template.data}</span>
                        </div>
                      </div>
                      <Button size="sm" variant="outline">
                        <IconBolt className="h-4 w-4" />
                      </Button>
                    </div>
                  ))}
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </AppLayout>
  );
}
