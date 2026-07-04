/**
 * TRANSITIONAL passthrough — the old per-page AppLayout (sidebar + header +
 * footer) has been replaced by the app-shell layout route
 * (src/components/app-shell.tsx). Old pages still wrap themselves in
 * <AppLayout>, so this renders children only; when the last old page is
 * rewritten, delete this file.
 */

import * as React from "react"

interface AppLayoutProps {
  children: React.ReactNode
  /** Ignored — the header title now derives from the route registry. */
  pageTitle?: string
  /** Ignored — kept for old call sites. */
  sidebarVariant?: "inset" | "sidebar" | "floating"
}

export function AppLayout({ children }: AppLayoutProps) {
  return <>{children}</>
}
