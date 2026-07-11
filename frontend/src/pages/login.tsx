import { useEffect } from "react"
import { useLocation, useNavigate } from "react-router-dom"

import { LoginForm } from "@/components/login-form"
import { useAuth } from "@/contexts"

export default function LoginPage() {
  const navigate = useNavigate()
  const location = useLocation()
  const { isAuthenticated, authStatus } = useAuth()

  // Get the path to redirect to after login
  const from = (location.state as { from?: string } | null)?.from ?? "/"

  // Redirect if already authenticated or auth is disabled
  useEffect(() => {
    if (authStatus?.mode === "none" || isAuthenticated) {
      navigate(from, { replace: true })
    }
  }, [authStatus, isAuthenticated, navigate, from])

  const handleLoginSuccess = () => {
    navigate(from)
  }

  // Don't render login page if auth is disabled or already authenticated
  if ((authStatus && authStatus.mode === "none") || isAuthenticated) {
    return null
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <div className="w-full max-w-md">
        <LoginForm onLoginSuccess={handleLoginSuccess} />
      </div>
    </div>
  )
}
