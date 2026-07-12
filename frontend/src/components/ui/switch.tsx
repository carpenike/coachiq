import * as SwitchPrimitives from "@radix-ui/react-switch"
import * as React from "react"

import { cn } from "@/lib/utils"

const Switch = React.forwardRef<
  React.ComponentRef<typeof SwitchPrimitives.Root>,
  React.ComponentPropsWithoutRef<typeof SwitchPrimitives.Root>
>(({ className, ...props }, ref) => (
  <SwitchPrimitives.Root
    className={cn(
      "peer group relative inline-flex h-11 w-11 shrink-0 cursor-pointer items-center rounded-full before:absolute before:inset-x-0 before:top-2.5 before:h-6 before:rounded-full before:border-2 before:border-transparent before:transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background active:scale-[0.97] motion-reduce:transform-none disabled:cursor-not-allowed disabled:opacity-50 data-[state=checked]:before:bg-primary data-[state=unchecked]:before:bg-input",
      className
    )}
    {...props}
    ref={ref}
  >
    <SwitchPrimitives.Thumb
      className={cn(
        // The thumb stretches toward the pressed direction (like iOS): it widens on
        // press, and when checked the extra width grows leftward so the trailing
        // edge stays anchored.
        "pointer-events-none absolute left-0 top-3 block h-5 w-5 rounded-full bg-background shadow-lg ring-0 transition-[translate,width] data-[state=checked]:translate-x-5 data-[state=unchecked]:translate-x-0 group-active:w-6 group-active:data-[state=checked]:translate-x-4"
      )}
    />
  </SwitchPrimitives.Root>
))
Switch.displayName = SwitchPrimitives.Root.displayName

export { Switch }
