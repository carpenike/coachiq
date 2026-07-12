import { IconLoader2 } from "@tabler/icons-react"
import { Fragment, createElement, useEffect, useState, type ReactElement, type ReactNode } from "react"
import { useLocation, useNavigate } from "react-router-dom"

import { useAuth } from "@/contexts"
import { Button } from "@/components/ui/button"

interface IAuthGuardProps {
  children: ReactNode
}

/**
 * AuthGuard component that protects routes by checking authentication status.
 * Redirects unauthenticated users to the login page.
 */
export function AuthGuard({ children }: Readonly<IAuthGuardProps>): ReactElement | null {
  const navigate = useNavigate()
  const location = useLocation()
  const { isAuthenticated, authStatus, isLoading, statusError } = useAuth()
  const [loadingSlow, setLoadingSlow] = useState(false)

  useEffect(() => {
    if (!isLoading && authStatus) {
      setLoadingSlow(false)
      return
    }
    const timer = window.setTimeout(() => setLoadingSlow(true), 5_000)
    return () => window.clearTimeout(timer)
  }, [authStatus, isLoading])

  useEffect(() => {
    // Don't redirect while still loading auth status
    if (isLoading || !authStatus) {
      return
    }

    // If auth is disabled (mode: "none"), allow access
    if (authStatus.mode === "none") {
      return
    }

    // If user is not authenticated and auth is required, redirect to login
    if (!isAuthenticated) {
      // Save the current location so we can redirect back after login
      navigate("/login", {
        replace: true,
        state: { from: location.pathname }
      })
    }
  }, [isAuthenticated, authStatus, isLoading, navigate, location.pathname])

  // Show loading while checking authentication
  if (isLoading || !authStatus) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-6">
        <div className="w-full max-w-sm space-y-5 text-center">
          <div className="mx-auto flex size-12 items-center justify-center rounded-xl border bg-card shadow-sm">
            <IconLoader2 className="size-6 animate-spin motion-reduce:hidden" aria-hidden />
            <span className="hidden text-lg font-semibold motion-reduce:inline">CIQ</span>
          </div>
          <div className="space-y-1">
            <h1 className="text-xl font-semibold">Connecting to CoachIQ</h1>
            <p role="status" className="text-sm text-muted-foreground">
              {statusError ? "The coach is not responding." : "Restoring your session and coach data."}
            </p>
          </div>
          {(loadingSlow || statusError) && (
            <div className="space-y-3 rounded-lg border bg-card p-4 text-left shadow-sm">
              <p className="text-sm text-muted-foreground">
                The coach may be restarting or temporarily unavailable. Retry when the network is ready.
              </p>
              <Button className="w-full" onClick={() => window.location.reload()}>
                Retry connection
              </Button>
            </div>
          )}
        </div>
      </div>
    )
  }

  // If auth is disabled, render children immediately
  if (authStatus.mode === "none") {
    return createElement(Fragment, null, children)
  }

  // If authenticated, render children
  if (isAuthenticated) {
    return createElement(Fragment, null, children)
  }

  // If not authenticated, don't render anything (will redirect to login)
  return null
}
