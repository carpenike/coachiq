/**
 * PIN Change Dialog Component
 *
 * Secure dialog for changing existing PINs with current PIN verification.
 * Includes PIN strength validation and configuration updates.
 */

import React, { useState } from 'react';
import { Eye, EyeOff, Shield, AlertTriangle, CheckCircle, RotateCcw } from 'lucide-react';
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
import { changePIN, type ChangePINRequest, type PINType } from '@/api/pin-auth';
import { useToast } from '@/hooks/use-toast';

interface PINChangeDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  pinType: PINType;
  onSuccess: () => void;
}

const PIN_TYPE_LABELS: Record<PINType, string> = {
  emergency: 'Emergency PIN',
  override: 'Override PIN',
  maintenance: 'Maintenance PIN'
};

const PIN_STRENGTH_REQUIREMENTS = {
  minLength: 4,
  maxLength: 8,
  requireNumeric: true,
  noSequential: true,
  noRepeated: true
};

export function PINChangeDialog({ open, onOpenChange, pinType, onSuccess }: PINChangeDialogProps) {
  const [formData, setFormData] = useState<Omit<ChangePINRequest, 'pin_type'>>({
    old_pin: '',
    new_pin: '',
    description: undefined,
    expires_after_days: undefined,
    max_uses: undefined
  });

  const [confirmNewPIN, setConfirmNewPIN] = useState('');
  const [showPINs, setShowPINs] = useState(false);
  const [useExpiration, setUseExpiration] = useState(false);
  const [useMaxUses, setUseMaxUses] = useState(false);
  const [isChanging, setIsChanging] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  const { toast } = useToast();

  // Reset form when dialog opens/closes
  React.useEffect(() => {
    if (open) {
      setFormData({
        old_pin: '',
        new_pin: '',
        description: undefined,
        expires_after_days: undefined,
        max_uses: undefined
      });
      setConfirmNewPIN('');
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

    if (!formData.old_pin || formData.old_pin.trim() === '') {
      newErrors.old_pin = 'Current PIN is required';
    }

    if (!formData.new_pin || formData.new_pin.trim() === '') {
      newErrors.new_pin = 'New PIN is required';
    } else {
      const pinIssues = validatePIN(formData.new_pin);
      if (pinIssues.length > 0 && pinIssues[0]) {
        newErrors.new_pin = pinIssues[0]; // Show first issue
      }
    }

    if (formData.old_pin === formData.new_pin) {
      newErrors.new_pin = 'New PIN must be different from current PIN';
    }

    if (!confirmNewPIN) {
      newErrors.confirmNewPIN = 'Please confirm the new PIN';
    } else if (formData.new_pin !== confirmNewPIN) {
      newErrors.confirmNewPIN = 'PINs do not match';
    }

    if (useExpiration && (!formData.expires_after_days || formData.expires_after_days < 1)) {
      newErrors.expires_after_days = 'Expiration must be at least 1 day';
    }

    if (useMaxUses && (!formData.max_uses || formData.max_uses < 1)) {
      newErrors.max_uses = 'Max uses must be at least 1';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  // Handle form submission
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!validateForm()) return;

    setIsChanging(true);
    try {
      const request: ChangePINRequest = {
        pin_type: pinType,
        old_pin: formData.old_pin,
        new_pin: formData.new_pin,
        description: formData.description,
        expires_after_days: useExpiration ? formData.expires_after_days : undefined,
        max_uses: useMaxUses ? formData.max_uses : undefined
      };

      await changePIN(request);
      onSuccess();
    } catch (err) {
      toast({
        title: 'PIN Change Failed',
        description: err instanceof Error ? err.message : 'Failed to change PIN',
        variant: 'destructive'
      });
    } finally {
      setIsChanging(false);
    }
  };

  const newPINStrength = formData.new_pin ? getPINStrength(formData.new_pin) : null;
  const newPINIssues = formData.new_pin ? validatePIN(formData.new_pin) : [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <RotateCcw className="h-5 w-5" />
            Change {PIN_TYPE_LABELS[pinType]}
          </DialogTitle>
          <DialogDescription>
            Update your {pinType} PIN and security settings
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Current PIN */}
          <div className="space-y-2">
            <Label htmlFor="old_pin">Current PIN</Label>
            <div className="relative">
              <Input
                id="old_pin"
                type={showPINs ? 'text' : 'password'}
                value={formData.old_pin}
                onChange={(e) => setFormData({ ...formData, old_pin: e.target.value })}
                placeholder="Enter current PIN"
                className={errors.old_pin ? 'border-destructive' : ''}
                maxLength={8}
                autoFocus
              />
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="absolute right-0 top-0 h-full px-3 py-2 hover:bg-transparent"
                onClick={() => setShowPINs(!showPINs)}
              >
                {showPINs ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </Button>
            </div>
            {errors.old_pin && (
              <p className="text-sm text-destructive">{errors.old_pin}</p>
            )}
          </div>

          <Separator />

          {/* New PIN Entry */}
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="new_pin">New PIN</Label>
              <Input
                id="new_pin"
                type={showPINs ? 'text' : 'password'}
                value={formData.new_pin}
                onChange={(e) => setFormData({ ...formData, new_pin: e.target.value })}
                placeholder="Enter new PIN"
                className={errors.new_pin ? 'border-destructive' : ''}
                maxLength={8}
              />
              {errors.new_pin && (
                <p className="text-sm text-destructive">{errors.new_pin}</p>
              )}

              {/* New PIN Strength Indicator */}
              {formData.new_pin && (
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="text-sm">Strength:</span>
                    <Badge variant={
                      newPINStrength === 'strong' ? 'default' :
                      newPINStrength === 'medium' ? 'secondary' : 'destructive'
                    }>
                      {newPINStrength?.toUpperCase()}
                    </Badge>
                  </div>

                  {newPINIssues.length > 0 && (
                    <Alert variant="destructive" className="py-2">
                      <AlertTriangle className="h-4 w-4" />
                      <AlertDescription className="text-sm">
                        Issues: {newPINIssues.join(', ')}
                      </AlertDescription>
                    </Alert>
                  )}
                </div>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="confirmNewPIN">Confirm New PIN</Label>
              <Input
                id="confirmNewPIN"
                type={showPINs ? 'text' : 'password'}
                value={confirmNewPIN}
                onChange={(e) => setConfirmNewPIN(e.target.value)}
                placeholder="Confirm new PIN"
                className={errors.confirmNewPIN ? 'border-destructive' : ''}
                maxLength={8}
              />
              {errors.confirmNewPIN && (
                <p className="text-sm text-destructive">{errors.confirmNewPIN}</p>
              )}
            </div>
          </div>

          <Separator />

          {/* PIN Configuration Updates */}
          <div className="space-y-4">
            <h4 className="font-medium">Update Configuration</h4>

            <div className="space-y-2">
              <Label htmlFor="description">Description (Optional)</Label>
              <Textarea
                id="description"
                value={formData.description || ''}
                onChange={(e) => setFormData({ ...formData, description: e.target.value || undefined })}
                placeholder="Updated description for this PIN"
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
                <Label htmlFor="useExpiration">Update expiration date</Label>
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
                <Label htmlFor="useMaxUses">Update usage limit</Label>
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

          {/* Security Notice */}
          <Alert>
            <Shield className="h-4 w-4" />
            <AlertDescription className="text-sm">
              <strong>Security Notice:</strong> Changing your PIN will invalidate any active sessions.
              You will need to use the new PIN for future operations.
            </AlertDescription>
          </Alert>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={isChanging}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={
                isChanging ||
                newPINIssues.length > 0 ||
                !formData.old_pin ||
                !formData.new_pin ||
                !confirmNewPIN
              }
            >
              {isChanging ? (
                <>
                  <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-white mr-2" />
                  Changing...
                </>
              ) : (
                <>
                  <CheckCircle className="h-4 w-4 mr-2" />
                  Change PIN
                </>
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
