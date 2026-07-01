import { IconFingerprint, IconLoader2, IconMail, IconShield, IconUser } from "@tabler/icons-react"
import { useEffect, useState } from "react"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { useAuth } from "@/contexts"
import { cn } from "@/lib/utils"

interface LoginFormProps extends React.ComponentProps<"div"> {
  onLoginSuccess?: () => void
}

export function LoginForm({
  className,
  onLoginSuccess,
  ...props
}: LoginFormProps) {
  const { login, sendMagicLink, authStatus, isLoading } = useAuth()
  const [formData, setFormData] = useState({
    username: "",
    password: "",
    email: "",
  })
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isSendingMagicLink, setIsSendingMagicLink] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [magicLinkSent, setMagicLinkSent] = useState(false)
  const [loginMode, setLoginMode] = useState<"password" | "magic">("password")

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    if (params.get("oidc_error") || params.get("reason")) {
      setError("SSO unavailable. Use local login.")
    }
  }, [])

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target
    setFormData(prev => ({ ...prev, [name]: value }))
    // Clear error when user starts typing
    if (error) setError(null)
  }

  const handlePasswordLogin = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!formData.username || !formData.password) {
      setError("Please enter both username and password")
      return
    }

    setIsSubmitting(true)
    setError(null)

    try {
      await login({
        username: formData.username,
        password: formData.password
      })
      onLoginSuccess?.()
    } catch (err: unknown) {
      // Handle account lockout specifically
      if (err && typeof err === 'object' && 'response' in err) {
        const error = err as { response?: { status?: number; data?: { detail?: { error?: string; lockout_until?: string; attempts_remaining?: number } } } }
        if (error?.response?.status === 423) {
          const lockoutData = error.response.data?.detail
          if (lockoutData?.error === "account_locked" && lockoutData.lockout_until) {
            const lockoutUntil = new Date(lockoutData.lockout_until).toLocaleString()
            const failedAttempts = lockoutData.attempts_remaining || 0
            setError(
              `Account locked due to ${failedAttempts} failed attempts. ` +
              `Try again after ${lockoutUntil}.`
            )
          } else {
            setError("Account is temporarily locked. Please try again later.")
          }
        } else {
          setError("Account is temporarily locked. Please try again later.")
        }
      } else {
        setError(err instanceof Error ? err.message : "Login failed")
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  const handleMagicLinkRequest = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!formData.email) {
      setError("Please enter your email address")
      return
    }

    setIsSendingMagicLink(true)
    setError(null)

    try {
      await sendMagicLink({ email: formData.email })
      setMagicLinkSent(true)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to send magic link")
    } finally {
      setIsSendingMagicLink(false)
    }
  }

  const handlePocketIdLogin = () => {
    window.location.assign("/api/v1/auth/oidc/login")
  }

  // Show loading state while auth status is being determined
  if (isLoading || !authStatus) {
    return (
      <div className={cn("flex flex-col gap-6", className)} {...props}>
        <Card>
          <CardContent className="flex items-center justify-center p-6">
            <div className="flex items-center gap-2 text-muted-foreground">
              <IconLoader2 className="h-4 w-4 animate-spin" />
              <span>Loading authentication...</span>
            </div>
          </CardContent>
        </Card>
      </div>
    )
  }

  // Handle different authentication modes
  const isPasswordMode = authStatus.mode === "single" && authStatus.jwt_available
  const isMagicLinkMode = authStatus.mode === "multi" && authStatus.magic_links_enabled
  const isOidcMode = authStatus.oidc_enabled
  const hasLocalLoginMode = isPasswordMode || isMagicLinkMode
  const isNoAuthMode = authStatus.mode === "none"
  let authDescription = "Enter your email for a magic link"
  if (isOidcMode) {
    authDescription = hasLocalLoginMode
      ? "Choose your preferred sign-in method"
      : "Use PocketID to sign in"
  } else if (isPasswordMode && isMagicLinkMode) {
    authDescription = "Choose your preferred sign-in method"
  } else if (isPasswordMode) {
    authDescription = "Enter your username and password"
  }

  if (isNoAuthMode) {
    return (
      <div className={cn("flex flex-col gap-6", className)} {...props}>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <IconShield className="h-5 w-5" />
              No Authentication Required
            </CardTitle>
            <CardDescription>
              Authentication is disabled for this system
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Alert>
              <IconShield className="h-4 w-4" />
              <AlertDescription>
                You have full access to the system without authentication.
              </AlertDescription>
            </Alert>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className={cn("flex flex-col gap-6", className)} {...props}>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <IconUser className="h-5 w-5" />
            Sign in to CoachIQ
          </CardTitle>
          <CardDescription>
            {authDescription}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {error && (
            <Alert className="mb-4" variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {magicLinkSent ? (
            <div className="space-y-4">
              <Alert>
                <IconMail className="h-4 w-4" />
                <AlertDescription>
                  Magic link sent to {formData.email}. Check your email and click the link to sign in.
                </AlertDescription>
              </Alert>
              <Button
                variant="outline"
                onClick={() => {
                  setMagicLinkSent(false)
                  setFormData(prev => ({ ...prev, email: "" }))
                }}
                className="w-full"
              >
                Send another link
              </Button>
            </div>
          ) : (
            <div className="space-y-4">
              {isOidcMode && (
                <Button
                  type="button"
                  variant="outline"
                  onClick={handlePocketIdLogin}
                  className="w-full"
                  disabled={isSubmitting || isSendingMagicLink}
                >
                  <IconFingerprint className="mr-2 h-4 w-4" />
                  Sign in with PocketID
                </Button>
              )}

              {isOidcMode && hasLocalLoginMode && <Separator />}

              {/* Mode toggle buttons if both modes are available */}
              {isPasswordMode && isMagicLinkMode && (
                <div className="flex gap-2 p-1 bg-muted rounded-md">
                  <Button
                    type="button"
                    variant={loginMode === "password" ? "default" : "ghost"}
                    size="sm"
                    onClick={() => setLoginMode("password")}
                    className="flex-1"
                  >
                    Username & Password
                  </Button>
                  <Button
                    type="button"
                    variant={loginMode === "magic" ? "default" : "ghost"}
                    size="sm"
                    onClick={() => setLoginMode("magic")}
                    className="flex-1"
                  >
                    Magic Link
                  </Button>
                </div>
              )}

              {/* Password login form */}
              {((isPasswordMode && !isMagicLinkMode) || loginMode === "password") && (
                <form onSubmit={(e) => void handlePasswordLogin(e)} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="username">Username</Label>
                    <Input
                      id="username"
                      name="username"
                      type="text"
                      placeholder="Enter your username"
                      value={formData.username}
                      onChange={handleInputChange}
                      required
                      disabled={isSubmitting}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="password">Password</Label>
                    <Input
                      id="password"
                      name="password"
                      type="password"
                      placeholder="Enter your password"
                      value={formData.password}
                      onChange={handleInputChange}
                      required
                      disabled={isSubmitting}
                    />
                  </div>
                  <Button type="submit" className="w-full" disabled={isSubmitting}>
                    {isSubmitting && <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />}
                    Sign in
                  </Button>
                </form>
              )}

              {/* Magic link form */}
              {((isMagicLinkMode && !isPasswordMode) || loginMode === "magic") && (
                <form onSubmit={(e) => void handleMagicLinkRequest(e)} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="email">Email</Label>
                    <Input
                      id="email"
                      name="email"
                      type="email"
                      placeholder="Enter your email"
                      value={formData.email}
                      onChange={handleInputChange}
                      required
                      disabled={isSendingMagicLink}
                    />
                  </div>
                  <Button type="submit" className="w-full" disabled={isSendingMagicLink}>
                    {isSendingMagicLink && <IconLoader2 className="mr-2 h-4 w-4 animate-spin" />}
                    Send Magic Link
                  </Button>
                </form>
              )}

              {/* Separator and mode switch option */}
              {isPasswordMode && isMagicLinkMode && (
                <>
                  <Separator />
                  <div className="text-center text-sm text-muted-foreground">
                    Or{" "}
                    <Button
                      variant="link"
                      size="sm"
                      onClick={() => setLoginMode(loginMode === "password" ? "magic" : "password")}
                      className="p-0 h-auto font-normal"
                    >
                      {loginMode === "password" ? "use magic link instead" : "use password instead"}
                    </Button>
                  </div>
                </>
              )}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
