import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { AppShell } from "@/components/app-shell";
import { AuthGuard } from "@/components/auth-guard";
import { ErrorBoundary } from "@/components/error-boundary";
import { ThemeProvider } from "@/components/theme-provider";
import { Toaster as SonnerToaster } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";
import { AuthProvider } from "@/contexts/auth-context";
import { CoachConnectionProvider } from "@/contexts/coach-connection";
import { QueryProvider } from "@/contexts/query-provider";
import { WebSocketProvider } from "@/contexts/websocket-provider";
import { appRoutes } from "@/lib/routes";
import LoginPage from "@/pages/login";
import NotFoundPage from "@/pages/not-found";
import OidcCallbackPage from "@/pages/oidc-callback";

import "./global.css";

/** Old URLs → new IA. Everything else that was deleted lands on the 404. */
const legacyRedirects: Record<string, string> = {
  "/dashboard": "/",
  "/entities": "/devices",
  "/system-status": "/system",
  "/logs": "/system",
  "/admin-settings": "/admin",
  "/config": "/account",
  "/settings": "/account",
  "/profile": "/account",
  "/can-sniffer": "/advanced/can-sniffer",
  "/can-tools": "/advanced/can-tools",
  "/network-map": "/advanced/network-map",
  "/unknown-pgns": "/advanced/unknown-pgns",
  "/unmapped-entries": "/advanced/unmapped-entries",
  "/device-mapping": "/advanced/device-mapping",
  "/rvc-spec": "/advanced/rvc-spec",
};

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryProvider>
      <AuthProvider>
        <WebSocketProvider enableEntityUpdates enableSystemStatus enableCANScan={false}>
            <CoachConnectionProvider>
              <ThemeProvider
                attribute="class"
                defaultTheme="system"
                enableSystem
                disableTransitionOnChange
              >
                <TooltipProvider>
                  <Toaster />
                  <SonnerToaster />
                  <ErrorBoundary>
                    <BrowserRouter
                      future={{
                        v7_startTransition: true,
                        v7_relativeSplatPath: true,
                      }}
                    >
                      <Routes>
                        {/* Public routes */}
                        <Route path="/login" element={<LoginPage />} />
                        <Route path="/auth/oidc/callback" element={<OidcCallbackPage />} />

                        {/* Protected routes: one layout route, pages from the registry */}
                        <Route
                          element={
                            <AuthGuard>
                              <AppShell />
                            </AuthGuard>
                          }
                        >
                          {appRoutes.map((route) => (
                            <Route key={route.path} path={route.path} element={route.element} />
                          ))}

                          {/* Legacy URL redirects */}
                          {Object.entries(legacyRedirects).map(([from, to]) => (
                            <Route key={from} path={from} element={<Navigate to={to} replace />} />
                          ))}

                          {/* Friendly 404 inside the shell */}
                          <Route path="*" element={<NotFoundPage />} />
                        </Route>
                      </Routes>
                    </BrowserRouter>
                  </ErrorBoundary>
                </TooltipProvider>
              </ThemeProvider>
            </CoachConnectionProvider>
          </WebSocketProvider>
      </AuthProvider>
    </QueryProvider>
  </StrictMode>
);
