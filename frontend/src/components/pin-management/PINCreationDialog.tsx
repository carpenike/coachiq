/**
 * PIN Creation Dialog Component
 *
 * Secure dialog for creating new PINs with configuration options.
 * Includes PIN strength validation and security settings.
 */

import React, { useState } from 'react';
import { Eye, EyeOff, Shield, AlertTriangle, CheckCircle, Info } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { createPIN, type CreatePINRequest, type PINType } from '@/api/pin-auth';
import { useToast } from '@/hooks/use-toast';

interface PINCreationDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  pinType: PINType;
  userId?: string | undefined; // Optional - for admin creation
  onSuccess: () => void;
}

const PIN_TYPE_LABELS: Record<PINType, string> = {
  emergency: 'Emergency PIN',
  override: 'Override PIN',
  maintenance: 'Maintenance PIN'
};

const PIN_TYPE_DESCRIPTIONS: Record<PINType, string> = {
  emergency: 'Used for emergency shutdown and critical safety operations',
  override: 'Used to override safety interlocks and automated systems',
  maintenance: 'Used for system maintenance and diagnostic procedures'
};

const PIN_STRENGTH_REQUIREMENTS = {
  minLength: 4,
  maxLength: 8,
  requireNumeric: true,
  noSequential: true,
  noRepeated: true
};

export function PINCreationDialog({ open, onOpenChange, pinType, userId, onSuccess }: PINCreationDialogProps) {
  const [formData, setFormData] = useState<Omit<CreatePINRequest, 'pin_type'>>({
    pin: '',
    description: undefined,
    expires_after_days: undefined,
    max_uses: undefined,
    lockout_after_failures: 5,
    lockout_duration_minutes: 15
  });

  const [confirmPIN, setConfirmPIN] = useState('');
  const [showPIN, setShowPIN] = useState(false);
  const [useExpiration, setUseExpiration] = useState(false);
  const [useMaxUses, setUseMaxUses] = useState(false);
  const [isCreating, setIsCreating] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const { toast } = useToast();

  // Reset form when dialog opens/closes
  React.useEffect(() => {
    if (open) {
      setFormData({
        pin: '',
        description: undefined,
        expires_after_days: undefined,
        max_uses: undefined,
        lockout_after_failures: 5,
        lockout_duration_minutes: 15
      });
      setConfirmPIN('');
      setUseExpiration(false);
      setUseMaxUses(false);
      setErrors({});
    }
  }, [open]);

  // Validate PIN strength
  const validatePIN = (pin: string) => {
    const issues: string[] = [];

    if (pin.length < PIN_STRENGTH_REQUIREMENTS.minLength) {
      issues.push(`At least ${PIN_STRENGTH_REQUIREMENTS.minLength} digits`);
    }

    if (pin.length > PIN_STRENGTH_REQUIREMENTS.maxLength) {
      issues.push(`At most ${PIN_STRENGTH_REQUIREMENTS.maxLength} digits`);
    }

    if (PIN_STRENGTH_REQUIREMENTS.requireNumeric && !/^\d+$/.test(pin)) {
      issues.push('Only numeric digits allowed');
    }

    if (PIN_STRENGTH_REQUIREMENTS.noSequential) {
      const hasSequential = /012|123|234|345|456|567|678|789|987|876|765|654|543|432|321|210/.test(pin);
      if (hasSequential) {
        issues.push('No sequential digits (123, 456, etc.)');
      }
    }

    if (PIN_STRENGTH_REQUIREMENTS.noRepeated) {
      const hasRepeated = /(.)\1{2,}/.test(pin);
      if (hasRepeated) {
        issues.push('No repeated digits (111, 222, etc.)');
      }
    }

    // Check for common weak PINs
    const weakPINs = ['0000', '1111', '2222', '3333', '4444', '5555', '6666', '7777', '8888', '9999', '1234', '4321', '0123'];
    if (weakPINs.includes(pin)) {
      issues.push('PIN is too common/weak');
    }

    return issues;
  };

  // Get PIN strength level
  const getPINStrength = (pin: string) => {
    const issues = validatePIN(pin);
    if (issues.length === 0 && pin.length >= 6) return 'strong';
    if (issues.length <= 1) return 'medium';
    return 'weak';
  };

  // Validate form
  const validateForm = () => {
    const newErrors: Record<string, string> = {};

    if (!formData.pin || formData.pin.trim() === '') {
      newErrors.pin = 'PIN is required';
    } else {
      const pinIssues = validatePIN(formData.pin);
      if (pinIssues.length > 0 && pinIssues[0]) {
        newErrors.pin = pinIssues[0]; // Show first issue
      }
    }

    if (!confirmPIN) {
      newErrors.confirmPIN = 'Please confirm the PIN';
    } else if (formData.pin !== confirmPIN) {
      newErrors.confirmPIN = 'PINs do not match';
    }

    if (useExpiration && (!formData.expires_after_days || formData.expires_after_days < 1)) {
      newErrors.expires_after_days = 'Expiration must be at least 1 day';
    }

    if (useMaxUses && (!formData.max_uses || formData.max_uses < 1)) {
      newErrors.max_uses = 'Max uses must be at least 1';
    }

    if (!formData.lockout_after_failures || formData.lockout_after_failures < 1) {
      newErrors.lockout_after_failures = 'Must be at least 1';
    }

    if (!formData.lockout_duration_minutes || formData.lockout_duration_minutes < 1) {
      newErrors.lockout_duration_minutes = 'Must be at least 1 minute';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  // Handle form submission
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateForm()) return;

    setIsCreating(true);
    try {
      const request: CreatePINRequest = {
        pin_type: pinType,
        pin: formData.pin,
        description: formData.description,
        expires_after_days: useExpiration ? formData.expires_after_days : undefined,
        max_uses: useMaxUses ? formData.max_uses : undefined,
        lockout_after_failures: formData.lockout_after_failures,
        lockout_duration_minutes: formData.lockout_duration_minutes
      };

      await createPIN(request, userId);
      onSuccess();
    } catch (err) {
      toast({
        title: 'PIN Creation Failed',
        description: err instanceof Error ? err.message : 'Failed to create PIN',
        variant: 'destructive'
      });
    } finally {
      setIsCreating(false);
    }
  };

  const pinStrength = formData.pin ? getPINStrength(formData.pin) : null;
  const pinIssues = formData.pin ? validatePIN(formData.pin) : [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Create {PIN_TYPE_LABELS[pinType]}
          </DialogTitle>
          <DialogDescription>
            {PIN_TYPE_DESCRIPTIONS[pinType]}
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* PIN Entry */}
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="pin">PIN</Label>
              <div className="relative">
                <Input
                  id="pin"
                  type={showPIN ? 'text' : 'password'}
                  value={formData.pin}
                  onChange={(e) => setFormData({ ...formData, pin: e.target.value })}
                  placeholder="Enter 4-8 digit PIN"
                  className={errors.pin ? 'border-destructive' : ''}
                  maxLength={8}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="absolute right-0 top-0 h-full px-3 py-2 hover:bg-transparent"
                  onClick={() => setShowPIN(!showPIN)}
                >
                  {showPIN ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </Button>
              </div>
              {errors.pin && (
                <p className="text-sm text-destructive">{errors.pin}</p>
              )}

              {/* PIN Strength Indicator */}
              {formData.pin && (
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="text-sm">Strength:</span>
                    <Badge variant={
                      pinStrength === 'strong' ? 'default' :
                      pinStrength === 'medium' ? 'secondary' : 'destructive'
                    }>
                      {pinStrength?.toUpperCase()}
                    </Badge>
                  </div>

                  {pinIssues.length > 0 && (
                    <Alert variant="destructive" className="py-2">
                      <AlertTriangle className="h-4 w-4" />
                      <AlertDescription className="text-sm">
                        Issues: {pinIssues.join(', ')}
                      </AlertDescription>
                    </Alert>
                  )}
                </div>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="confirmPIN">Confirm PIN</Label>
              <Input
                id="confirmPIN"
                type={showPIN ? 'text' : 'password'}
                value={confirmPIN}
                onChange={(e) => setConfirmPIN(e.target.value)}
                placeholder="Confirm PIN"
                className={errors.confirmPIN ? 'border-destructive' : ''}
                maxLength={8}
              />
              {errors.confirmPIN && (
                <p className="text-sm text-destructive">{errors.confirmPIN}</p>
              )}
            </div>
          </div>

          <Separator />

          {/* PIN Configuration */}
          <div className="space-y-4">
            <h4 className="font-medium">Configuration</h4>

            <div className="space-y-2">
              <Label htmlFor="description">Description (Optional)</Label>
              <Textarea
                id="description"
                value={formData.description || ''}
                onChange={(e) => setFormData({ ...formData, description: e.target.value || undefined })}
                placeholder="Optional description for this PIN"
                rows={2}
              />
            </div>

            {/* Expiration Settings */}
            <div className="space-y-3">
              <div className="flex items-center space-x-2">
                <Switch
                  id="useExpiration"
                  checked={useExpiration}
                  onCheckedChange={setUseExpiration}
                />
                <Label htmlFor="useExpiration">Set expiration date</Label>
              </div>

              {useExpiration && (
                <div className="ml-6 space-y-2">
                  <Label htmlFor="expires_after_days">Expires after (days)</Label>
                  <Input
                    id="expires_after_days"
                    type="number"
                    value={formData.expires_after_days || ''}
                    onChange={(e) => setFormData({
                      ...formData,
                      expires_after_days: e.target.value ? parseInt(e.target.value) : undefined
                    })}
                    placeholder="30"
                    min="1"
                    max="365"
                    className={errors.expires_after_days ? 'border-destructive' : ''}
                  />
                  {errors.expires_after_days && (
                    <p className="text-sm text-destructive">{errors.expires_after_days}</p>
                  )}
                </div>
              )}
            </div>

            {/* Usage Limit Settings */}
            <div className="space-y-3">
              <div className="flex items-center space-x-2">
                <Switch
                  id="useMaxUses"
                  checked={useMaxUses}
                  onCheckedChange={setUseMaxUses}
                />
                <Label htmlFor="useMaxUses">Limit number of uses</Label>
              </div>

              {useMaxUses && (
                <div className="ml-6 space-y-2">
                  <Label htmlFor="max_uses">Maximum uses</Label>
                  <Input
                    id="max_uses"
                    type="number"
                    value={formData.max_uses || ''}
                    onChange={(e) => setFormData({
                      ...formData,
                      max_uses: e.target.value ? parseInt(e.target.value) : undefined
                    })}
                    placeholder="10"
                    min="1"
                    max="1000"
                    className={errors.max_uses ? 'border-destructive' : ''}
                  />
                  {errors.max_uses && (
                    <p className="text-sm text-destructive">{errors.max_uses}</p>
                  )}
                </div>
              )}
            </div>
          </div>

          <Separator />

          {/* Security Settings */}
          <div className="space-y-4">
            <h4 className="font-medium">Security Settings</h4>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="lockout_after_failures">Failed attempts before lockout</Label>
                <Input
                  id="lockout_after_failures"
                  type="number"
                  value={formData.lockout_after_failures}
                  onChange={(e) => setFormData({
                    ...formData,
                    lockout_after_failures: parseInt(e.target.value) || 5
                  })}
                  min="1"
                  max="10"
                  className={errors.lockout_after_failures ? 'border-destructive' : ''}
                />
                {errors.lockout_after_failures && (
                  <p className="text-sm text-destructive">{errors.lockout_after_failures}</p>
                )}
              </div>

              <div className="space-y-2">
                <Label htmlFor="lockout_duration_minutes">Lockout duration (minutes)</Label>
                <Input
                  id="lockout_duration_minutes"
                  type="number"
                  value={formData.lockout_duration_minutes}
                  onChange={(e) => setFormData({
                    ...formData,
                    lockout_duration_minutes: parseInt(e.target.value) || 15
                  })}
                  min="1"
                  max="1440"
                  className={errors.lockout_duration_minutes ? 'border-destructive' : ''}
                />
                {errors.lockout_duration_minutes && (
                  <p className="text-sm text-destructive">{errors.lockout_duration_minutes}</p>
                )}
              </div>
            </div>
          </div>

          {/* Security Notice */}
          <Alert>
            <Info className="h-4 w-4" />
            <AlertDescription className="text-sm">
              <strong>Security Notice:</strong> This PIN will be required for {pinType} operations.
              Store it securely and do not share it with unauthorized personnel.
            </AlertDescription>
          </Alert>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isCreating}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={isCreating || pinIssues.length > 0 || !formData.pin || !confirmPIN}
            >
              {isCreating ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2" />
                  Creating...
                </>
              ) : (
                <>
                  <CheckCircle className="h-4 w-4 mr-2" />
                  Create PIN
                </>
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
