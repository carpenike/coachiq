/**
 * Route-level error boundary.
 *
 * Catches render errors below it and shows a friendly recovery card with
 * reload + Home actions instead of a white screen. Resets automatically
 * when the route changes so navigating away recovers.
 */

import { IconAlertOctagon, IconHome, IconRefresh } from "@tabler/icons-react"
import { Component, type ErrorInfo, type ReactNode } from "react"
import { useLocation } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

interface IErrorBoundaryProps {
  children: ReactNode
  /** Change this key (e.g. route path) to reset the boundary */
  resetKey?: string
}

interface IErrorBoundaryState {
  error: Error | null
}

export class ErrorBoundary extends Component<IErrorBoundaryProps, IErrorBoundaryState> {
  override state: IErrorBoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): IErrorBoundaryState {
    return { error }
  }

  override componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("Route error boundary caught:", error, errorInfo.componentStack)
  }

  override componentDidUpdate(prevProps: IErrorBoundaryProps) {
    if (this.state.error && prevProps.resetKey !== this.props.resetKey) {
      this.setState({ error: null })
    }
  }

  // eslint-disable-next-line sonarjs/function-return-type -- render() legitimately returns children (ReactNode union) or the fallback element
  override render(): ReactNode {
    if (!this.state.error) {
      return this.props.children
    }

    return (
      <div className="flex flex-1 items-center justify-center p-6">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <IconAlertOctagon className="size-5 text-destructive" />
              Something went wrong
            </CardTitle>
            <CardDescription>
              This page hit an unexpected error. The rest of the app is still running.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="rounded-md bg-muted px-3 py-2 font-mono text-xs text-muted-foreground break-all">
              {this.state.error.message || String(this.state.error)}
            </p>
            <div className="flex gap-2">
              <Button onClick={() => window.location.reload()} className="gap-1">
                <IconRefresh className="size-4" />
                Reload
              </Button>
              <Button variant="outline" asChild className="gap-1">
                <a href="/">
                  <IconHome className="size-4" />
                  Home
                </a>
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }
}

/** ErrorBoundary that resets when the route changes. */
export function RouteErrorBoundary({ children }: Readonly<{ children: ReactNode }>) {
  const location = useLocation()
  return <ErrorBoundary resetKey={location.pathname}>{children}</ErrorBoundary>
}
