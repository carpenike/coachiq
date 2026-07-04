/**
 * Friendly 404 page, registered as path="*".
 */

import { IconHome, IconMapQuestion } from "@tabler/icons-react"
import { Link } from "react-router-dom"

import { Button } from "@/components/ui/button"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export default function NotFoundPage() {
  return (
    <div className="flex flex-1 items-center justify-center p-6">
      <Card className="w-full max-w-md text-center">
        <CardHeader>
          <IconMapQuestion className="mx-auto size-10 text-muted-foreground" />
          <CardTitle>Page not found</CardTitle>
          <CardDescription>
            There is nothing at this address. It may have moved during the redesign.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild className="gap-1">
            <Link to="/">
              <IconHome className="size-4" />
              Back to Home
            </Link>
          </Button>
        </CardContent>
      </Card>
    </div>
  )
}
