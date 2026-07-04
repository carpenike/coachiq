/**
 * TRANSITIONAL passthrough — the old per-page AppLayout (sidebar + header +
 * footer) has been replaced by the app-shell layout route
 * (src/components/app-shell.tsx). Old pages still wrap themselves in
 * <AppLayout>, so this renders children only; when the last old page is
 * rewritten, delete this file.
 */

import type * as React from "react"

interface AppLayoutProps {
  children: React.ReactNode
  /** Ignored — the header title now derives from the route registry. */
  pageTitle?: string
  /** Ignored — kept for old call sites. */
  sidebarVariant?: "inset" | "sidebar" | "floating"
}

// eslint-disable-next-line sonarjs/function-return-type -- legitimately returns children (ReactNode union) verbatim, mirrors error-boundary.tsx render()
export function AppLayout({ children }: Readonly<AppLayoutProps>): React.ReactNode {
  return children
}
