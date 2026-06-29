/**
 * Create Group Dialog Component
 *
 * Dialog for creating device groups from selected devices.
 * Includes validation and exemption configuration.
 */

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Checkbox } from "@/components/ui/checkbox"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Textarea } from "@/components/ui/textarea"
import { useDeviceGroups, type DeviceGroupRequest } from "@/hooks/useBulkOperations"
import { useEntities } from "@/hooks/useEntities"
import { getEntityDisplayName } from "@/utils/entity-display"
import { IconDevices, IconUsers } from "@tabler/icons-react"
import { useState } from "react"
import { toast } from "sonner"

interface CreateGroupDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  selectedDevices: string[]
  onGroupCreated?: () => void
}

export function CreateGroupDialog({
  open,
  onOpenChange,
  selectedDevices,
  onGroupCreated
}: CreateGroupDialogProps) {
  const [name, setName] = useState("")
  const [description, setDescription] = useState("")
  const [exemptFromAllOff, setExemptFromAllOff] = useState<Set<string>>(new Set())

  const { data: entities } = useEntities()
  const { createGroup } = useDeviceGroups()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!name.trim()) {
      toast.error("Group name is required")
      return
    }

    if (selectedDevices.length === 0) {
      toast.error("No devices selected")
      return
    }

    try {
      // Build exemptions configuration
      const exemptions: Record<string, string | number | boolean | string[]> = {}
      if (exemptFromAllOff.size > 0) {
        exemptions.all_off = Array.from(exemptFromAllOff)
      }

      const groupRequest: DeviceGroupRequest = {
        name: name.trim(),
        device_ids: selectedDevices,
        exemptions,
      };

      if (description.trim()) {
        groupRequest.description = description.trim();
      }

      await createGroup.mutateAsync(groupRequest)

      toast.success(`Device group "${name}" created successfully`)

      // Reset form
      setName("")
      setDescription("")
      setExemptFromAllOff(new Set())

      onGroupCreated?.()
    } catch (error) {
      toast.error("Failed to create device group")
      console.error("Error creating group:", error)
    }
  }

  const toggleAllOffExemption = (deviceId: string) => {
    setExemptFromAllOff(prev => {
      const newSet = new Set(prev)
      if (newSet.has(deviceId)) {
        newSet.delete(deviceId)
      } else {
        newSet.add(deviceId)
      }
      return newSet
    })
  }

  const getDeviceName = (deviceId: string) => {
    if (!entities) return deviceId
    const entity = entities.entities.find((item) => item.entity_id === deviceId)
    return entity ? getEntityDisplayName(entity) : deviceId
  }

  const getDeviceType = (deviceId: string) => {
    if (!entities) return "device"
    const entity = entities.entities.find((item) => item.entity_id === deviceId)
    return entity?.device_type || "device"
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <IconUsers className="h-5 w-5" />
            Create Device Group
          </DialogTitle>
          <DialogDescription>
            Create a reusable group from {selectedDevices.length} selected devices
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={(e) => void handleSubmit(e)} className="space-y-4">
          {/* Group Name */}
          <div className="space-y-2">
            <Label htmlFor="group-name">Group Name *</Label>
            <Input
              id="group-name"
              placeholder="e.g., Living Room Lights, All Exterior"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={100}
              required
            />
          </div>

          {/* Description */}
          <div className="space-y-2">
            <Label htmlFor="group-description">Description</Label>
            <Textarea
              id="group-description"
              placeholder="Optional description for this group"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              maxLength={500}
              rows={2}
            />
          </div>

          {/* Selected Devices Preview */}
          <div className="space-y-2">
            <Label className="flex items-center gap-2">
              <IconDevices className="h-4 w-4" />
              Devices ({selectedDevices.length})
            </Label>
            <div className="max-h-32 overflow-y-auto border rounded-md p-3 space-y-2">
              {selectedDevices.map(deviceId => (
                <div key={deviceId} className="flex items-center justify-between text-sm">
                  <div className="flex items-center gap-2 min-w-0">
                    <Badge variant="outline" className="text-xs">
                      {getDeviceType(deviceId)}
                    </Badge>
                    <span className="truncate">{getDeviceName(deviceId)}</span>
                  </div>

                  {/* All Off Exemption */}
                  <div className="flex items-center gap-2">
                    <Checkbox
                      id={`exempt-${deviceId}`}
                      checked={exemptFromAllOff.has(deviceId)}
                      onCheckedChange={() => toggleAllOffExemption(deviceId)}
                    />
                    <Label
                      htmlFor={`exempt-${deviceId}`}
                      className="text-xs text-muted-foreground cursor-pointer"
                    >
                      Exempt from "All Off"
                    </Label>
                  </div>
                </div>
              ))}
            </div>
            {exemptFromAllOff.size > 0 && (
              <p className="text-xs text-muted-foreground">
                {exemptFromAllOff.size} device(s) will be excluded from "All Off" operations
              </p>
            )}
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              disabled={createGroup.isPending || !name.trim()}
            >
              {createGroup.isPending ? "Creating..." : "Create Group"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
