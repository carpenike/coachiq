import { IconLoader2, IconShieldCheck, IconShieldX } from "@tabler/icons-react";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { Alert, AlertDescription } from "@/components/ui/alert";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle
} from "@/components/ui/card";
import { useAuth } from "@/contexts";

export default function OidcCallbackPage() {
  const { completeOidcLogin } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [error, setError] = useState<string | null>(null);
  // The session code is single-use; guard against exchanging it twice (e.g.
  // React StrictMode double-invoking the effect), which would fail the second
  // exchange and clear the tokens the first exchange just stored.
  const exchangedCodeRef = useRef<string | null>(null);

  useEffect(() => {
    const sessionCode = searchParams.get("code");
    if (!sessionCode) {
      setError("PocketID sign-in did not return a session code.");
      return;
    }

    if (exchangedCodeRef.current === sessionCode) {
      return;
    }
    exchangedCodeRef.current = sessionCode;

    let isCancelled = false;
    void completeOidcLogin(sessionCode)
      .then(() => {
        if (!isCancelled) {
          navigate("/dashboard", { replace: true });
        }
      })
      .catch(() => {
        if (!isCancelled) {
          setError("PocketID sign-in could not be completed.");
        }
      });

    return () => {
      isCancelled = true;
    };
  }, [completeOidcLogin, navigate, searchParams]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            {error ? <IconShieldX className="h-5 w-5" /> : <IconShieldCheck className="h-5 w-5" />}
            PocketID Sign-In
          </CardTitle>
          <CardDescription>Completing your CoachIQ session</CardDescription>
        </CardHeader>
        <CardContent>
          {error ? (
            <Alert variant="destructive">
              <IconShieldX className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          ) : (
            <div className="flex items-center gap-2 text-muted-foreground">
              <IconLoader2 className="h-4 w-4 animate-spin" />
              <span>Signing in...</span>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
