import type { ExternalToast } from "sonner"
import { toast as sonnerToast } from "sonner"

interface IToastOptions {
  title?: React.ReactNode
  description?: React.ReactNode
  variant?: "default" | "destructive"
  duration?: number
}

interface IToastHandle {
  id: string | number
  dismiss: () => void
}

function toast({ title, description, variant = "default", duration }: IToastOptions): IToastHandle {
  const options: ExternalToast = {}
  if (description !== undefined) options.description = description
  if (duration !== undefined) options.duration = duration

  const message = title ?? description ?? "CoachIQ notification"
  const id = variant === "destructive"
    ? sonnerToast.error(message, options)
    : sonnerToast(message, options)

  return {
    id,
    dismiss: () => sonnerToast.dismiss(id)
  }
}

function useToast() {
  return {
    toast,
    dismiss: (toastId?: string | number) => sonnerToast.dismiss(toastId)
  }
}

export { toast, useToast }
