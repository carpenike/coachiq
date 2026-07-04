import {
    IconDotsVertical,
    IconKey,
    IconLogin,
    IconLogout,
    IconShield,
    IconUserCircle,
} from "@tabler/icons-react"
import { useState } from "react"
import { useNavigate } from "react-router-dom"

import { AdminCredentialsModal } from "@/components/admin-credentials-modal"
import {
    Avatar,
    AvatarFallback,
} from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
    DropdownMenu,
    DropdownMenuContent,
    DropdownMenuGroup,
    DropdownMenuItem,
    DropdownMenuLabel,
    DropdownMenuSeparator,
    DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
    SidebarMenu,
    SidebarMenuButton,
    SidebarMenuItem,
    useSidebar,
} from "@/components/ui/sidebar"
import { Skeleton } from "@/components/ui/skeleton"
import { useAuth } from "@/contexts"

export function NavUser() {
  const { isMobile } = useSidebar()
  const navigate = useNavigate()
  const {
    user,
    authStatus,
    isLoading,
    isAuthenticated,
    logout,
    hasGeneratedCredentials,
  } = useAuth()
  const [showCredentialsModal, setShowCredentialsModal] = useState(false)

  const handleLogout = async () => {
    try {
      await logout()
    } catch (error) {
      console.error('Logout failed:', error)
      // Even if logout fails, user will be logged out locally
    }
  }

  const handleGetCredentials = () => {
    setShowCredentialsModal(true)
  }

  const handleProfileClick = () => {
    navigate("/account")
  }

  const handleAdminSettingsClick = () => {
    navigate("/admin")
  }

  // Loading state
  if (isLoading) {
    return (
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton size="lg" disabled>
            <Skeleton className="h-8 w-8 rounded-lg" />
            <div className="grid flex-1 text-left text-sm leading-tight">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="h-3 w-32" />
            </div>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    )
  }

  // No authentication mode
  if (authStatus?.mode === 'none') {
    return (
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton size="lg" disabled>
            <Avatar className="h-8 w-8 rounded-lg">
              <AvatarFallback className="rounded-lg">NA</AvatarFallback>
            </Avatar>
            <div className="grid flex-1 text-left text-sm leading-tight">
              <span className="truncate font-medium">No Auth</span>
              <span className="text-muted-foreground truncate text-xs">
                Authentication disabled
              </span>
            </div>
            <Badge variant="secondary" className="text-xs">
              None
            </Badge>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    )
  }

  // Not authenticated - show login button
  if (!isAuthenticated || !user) {
    return (
      <SidebarMenu>
        <SidebarMenuItem>
          <Button variant="outline" size="sm" className="w-full justify-start">
            <IconLogin className="mr-2 h-4 w-4" />
            Login Required
          </Button>
        </SidebarMenuItem>
      </SidebarMenu>
    )
  }

  // Authenticated user
  const displayName = user.username || user.email || user.user_id
  const displayEmail = user.email || `${user.user_id}@${authStatus?.mode || 'local'}`
  const avatarFallback = displayName?.substring(0, 2).toUpperCase() || 'U'

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <SidebarMenuButton
              size="lg"
              className="data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground"
            >
              <Avatar className="h-8 w-8 rounded-lg">
                <AvatarFallback className="rounded-lg">{avatarFallback}</AvatarFallback>
              </Avatar>
              <div className="grid flex-1 text-left text-sm leading-tight">
                <span className="truncate font-medium">{displayName}</span>
                <span className="text-muted-foreground truncate text-xs">
                  {displayEmail}
                </span>
              </div>
              <div className="flex items-center gap-1">
                <Badge variant={user.role === 'admin' ? 'default' : 'secondary'} className="text-xs">
                  {user.role}
                </Badge>
                <IconDotsVertical className="h-4 w-4" />
              </div>
            </SidebarMenuButton>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            className="w-[--radix-dropdown-menu-trigger-width] min-w-56 rounded-lg"
            side={isMobile ? "bottom" : "right"}
            align="end"
            sideOffset={4}
          >
            <DropdownMenuLabel className="p-0 font-normal">
              <div className="flex items-center gap-2 px-1 py-1.5 text-left text-sm">
                <Avatar className="h-8 w-8 rounded-lg">
                  <AvatarFallback className="rounded-lg">{avatarFallback}</AvatarFallback>
                </Avatar>
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <span className="truncate font-medium">{displayName}</span>
                  <span className="text-muted-foreground truncate text-xs">
                    {displayEmail}
                  </span>
                </div>
                <Badge variant={user.role === 'admin' ? 'default' : 'secondary'} className="text-xs">
                  {user.role}
                </Badge>
              </div>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuGroup>
              <DropdownMenuItem onClick={handleProfileClick}>
                <IconUserCircle className="mr-2 h-4 w-4" />
                Account
              </DropdownMenuItem>
              {user.role === 'admin' && (
                <DropdownMenuItem onClick={handleAdminSettingsClick}>
                  <IconShield className="mr-2 h-4 w-4" />
                  Admin Settings
                </DropdownMenuItem>
              )}
              {hasGeneratedCredentials && (
                <DropdownMenuItem onClick={handleGetCredentials}>
                  <IconKey className="mr-2 h-4 w-4" />
                  View Generated Password
                </DropdownMenuItem>
              )}
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => void handleLogout()}>
              <IconLogout className="mr-2 h-4 w-4" />
              Log out
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>

      {/* Admin credentials modal */}
      <AdminCredentialsModal
        open={showCredentialsModal}
        onOpenChange={setShowCredentialsModal}
      />
    </SidebarMenu>
  )
}
