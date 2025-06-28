# API Reference

**Version**: 2.0.0

Modernized backend API for RV-C CANbus monitoring and control

**Base URL**: `http://raspberrypi.local:8080`

## CAN Analyzer

### GET /api/can-analyzer/statistics

**Get Statistics**

Get current analyzer statistics.

**Responses:**

- `200`: Successful Response

---

### GET /api/can-analyzer/report

**Get Protocol Report**

Get detailed protocol analysis report.

**Responses:**

- `200`: Successful Response

---

### GET /api/can-analyzer/messages

**Get Recent Messages**

Get recent analyzed messages with optional filtering.

**Parameters:**

- `limit` (query, optional): No description
- `protocol` (query, optional): No description
- `message_type` (query, optional): No description
- `can_id` (query, optional): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/can-analyzer/patterns

**Get Communication Patterns**

Get detected communication patterns.

**Parameters:**

- `pattern_type` (query, optional): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/can-analyzer/protocols

**Get Detected Protocols**

Get detected protocols by CAN ID.

**Responses:**

- `200`: Successful Response

---

### POST /api/can-analyzer/analyze

**Analyze Message**

Manually analyze a specific CAN message.

**Parameters:**

- `can_id` (query, required): CAN ID in hex format (e.g., 0x18FEEE00)
- `data` (query, required): Message data in hex format
- `interface` (query, optional): CAN interface

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/can-analyzer/live

**Get Live Analysis**

Get live analysis data for the specified duration.

**Parameters:**

- `duration_seconds` (query, optional): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### DELETE /api/can-analyzer/clear

**Clear Analyzer**

Clear analyzer buffers and reset statistics.

**Responses:**

- `200`: Successful Response

---

## CAN Recorder

### GET /api/can-recorder/status

**Get Recorder Status**

Get current recorder status.

**Responses:**

- `200`: Successful Response

---

### POST /api/can-recorder/start

**Start Recording**

Start a new recording session.

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/can-recorder/stop

**Stop Recording**

Stop the current recording session.

**Responses:**

- `200`: Successful Response

---

### POST /api/can-recorder/pause

**Pause Recording**

Pause the current recording.

**Responses:**

- `200`: Successful Response

---

### POST /api/can-recorder/resume

**Resume Recording**

Resume a paused recording.

**Responses:**

- `200`: Successful Response

---

### GET /api/can-recorder/list

**List Recordings**

List all available recordings.

**Responses:**

- `200`: Successful Response

---

### DELETE /api/can-recorder/{filename}

**Delete Recording**

Delete a recording file.

**Parameters:**

- `filename` (path, required): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/can-recorder/replay/start

**Start Replay**

Start replaying a recorded session.

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/can-recorder/replay/stop

**Stop Replay**

Stop the current replay.

**Responses:**

- `200`: Successful Response

---

### GET /api/can-recorder/download/{filename}

**Download Recording**

Download a recording file.

**Parameters:**

- `filename` (path, required): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

## CAN Tools

### GET /api/can-tools/status

**Get Injector Status**

Get CAN message injector status and statistics.

**Responses:**

- `200`: Successful Response

---

### POST /api/can-tools/inject

**Inject Message**

Inject CAN message(s) for testing and diagnostics.

Safety levels:
- STRICT: Blocks dangerous messages
- MODERATE: Warns on dangerous messages (default)
- PERMISSIVE: Allows all messages (use with caution)

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/can-tools/inject/j1939

**Inject J1939 Message**

Inject J1939 message with automatic CAN ID generation.

This endpoint simplifies J1939 message injection by automatically
constructing the proper 29-bit CAN identifier from PGN and addresses.

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### DELETE /api/can-tools/inject/stop

**Stop Injection**

Stop active periodic message injections.

**Parameters:**

- `pattern` (query, optional): Pattern to match injections

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### PUT /api/can-tools/safety

**Update Safety Config**

Update safety configuration for message injection.

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/can-tools/pgn-info/{pgn}

**Get Pgn Info**

Get information about a specific PGN.

**Parameters:**

- `pgn` (path, required): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/can-tools/templates

**Get Message Templates**

Get example message templates for testing.

**Responses:**

- `200`: Successful Response

---

## admin

### GET /api/database/status

**Get Database Status**

Get current database schema status.

**Responses:**

- `200`: Successful Response

---

### POST /api/database/migrate

**Start Migration**

Start database migration process.

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/database/migrate/{job_id}/status

**Get Migration Progress**

Get migration job progress.

**Parameters:**

- `job_id` (path, required): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/database/history

**Get Migration History**

Get migration history.

**Parameters:**

- `limit` (query, optional): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/database/safety-check

**Check Migration Safety**

Get detailed safety check for migration.

**Responses:**

- `200`: Successful Response

---

## analytics_dashboard

### GET /api/analytics/trends

**Get performance trends**

Retrieve performance trends and analysis for specified metrics and time window.

**Parameters:**

- `time_window_hours` (query, optional): Time window in hours
- `metrics` (query, optional): Comma-separated list of metrics
- `resolution` (query, optional): Data resolution

**Responses:**

- `200`: Performance trend data with analysis and insights
- `422`: Validation Error

---

### GET /api/analytics/insights

**Get system insights**

Retrieve intelligent system insights and recommendations based on analytics data.

**Parameters:**

- `categories` (query, optional): Comma-separated list of categories
- `min_severity` (query, optional): Minimum severity level
- `limit` (query, optional): Maximum number of insights

**Responses:**

- `200`: System insights with actionable recommendations
- `422`: Validation Error

---

### GET /api/analytics/historical

**Get historical analysis**

Perform historical data analysis including pattern detection and anomaly analysis.

**Parameters:**

- `analysis_type` (query, optional): No description
- `time_window_hours` (query, optional): Time window in hours
- `include_predictions` (query, optional): Include predictive analysis

**Responses:**

- `200`: Historical analysis results with patterns and predictions
- `422`: Validation Error

---

### GET /api/analytics/aggregation

**Get metrics aggregation**

Get comprehensive metrics aggregation and reporting across multiple time windows.

**Parameters:**

- `aggregation_windows` (query, optional): Comma-separated aggregation windows
- `metric_groups` (query, optional): Comma-separated metric groups

**Responses:**

- `200`: Aggregated metrics with KPIs and benchmarks
- `422`: Validation Error

---

### POST /api/analytics/metrics

**Record custom metric**

Record a custom metric for analytics tracking and analysis.

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Success status of metric recording
- `422`: Validation Error

---

### GET /api/analytics/status

**Get analytics dashboard status**

Get the current status and configuration of the analytics dashboard.

**Responses:**

- `200`: Analytics dashboard status and configuration

---

### GET /api/analytics/health

**Analytics health check**

Health check endpoint for analytics dashboard service.

**Responses:**

- `200`: Health status of analytics components

---

## authentication

### POST /api/auth/login

**Login For Access Token**

Authenticate user with username and password (single-user mode).

Args:
    form_data: OAuth2 form data with username and password
    auth_manager: Authentication manager instance

Returns:
    TokenPair: JWT access token, refresh token and metadata

Raises:
    HTTPException: If authentication fails or not in single-user mode

**Request Body:**

Content-Type: `application/x-www-form-urlencoded`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/auth/login-step

**Login Step With Mfa Check**

First step of login - checks credentials and MFA requirement.

Args:
    form_data: OAuth2 form data with username and password
    auth_manager: Authentication manager instance

Returns:
    LoginStepResponse: Either tokens (if no MFA) or MFA challenge

Raises:
    HTTPException: If authentication fails or not in single-user mode

**Request Body:**

Content-Type: `application/x-www-form-urlencoded`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/auth/login-mfa

**Complete Login With Mfa**

Complete login after MFA verification.

Args:
    mfa_verification: MFA verification request with TOTP or backup code
    current_user: Current authenticated user (from step 1)
    auth_manager: Authentication manager instance

Returns:
    TokenPair: Final JWT access and refresh tokens

Raises:
    HTTPException: If MFA verification fails

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/auth/refresh

**Refresh Access Token**

Refresh access token using a valid refresh token.

Args:
    request: FastAPI request object
    refresh_request: Refresh token request data
    auth_manager: Authentication manager instance

Returns:
    TokenPair: New access token and refresh token

Raises:
    HTTPException: If refresh token is invalid or refresh is disabled

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/auth/revoke

**Revoke Refresh Token**

Revoke a refresh token.

Args:
    request: FastAPI request object
    refresh_request: Refresh token to revoke
    auth_manager: Authentication manager instance

Raises:
    HTTPException: If refresh tokens are disabled

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `204`: Successful Response
- `422`: Validation Error

---

### POST /api/auth/magic-link

**Send Magic Link**

Send magic link for passwordless authentication (multi-user mode).

Args:
    request: Magic link request with email and optional redirect URL
    auth_manager: Authentication manager instance

Returns:
    MagicLinkResponse: Confirmation message and metadata

Raises:
    HTTPException: If magic links are not enabled or email sending fails

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/auth/magic

**Verify Magic Link**

Verify magic link token and return access token.

Args:
    token: Magic link token from URL parameter
    auth_manager: Authentication manager instance

Returns:
    Token: JWT access token for authenticated user

Raises:
    HTTPException: If magic link token is invalid or expired

**Parameters:**

- `token` (query, required): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/auth/me

**Get User Profile**

Get current user profile information.

Args:
    current_user: Current authenticated user

Returns:
    UserInfo: Current user profile data

**Responses:**

- `200`: Successful Response

---

### GET /api/auth/status

**Get Auth Status**

Get authentication system status and configuration.

Args:
    auth_manager: Authentication manager instance

Returns:
    AuthStatus: Authentication system status

**Responses:**

- `200`: Successful Response

---

### POST /api/auth/logout

**Logout**

Logout current user and revoke all refresh tokens.

Args:
    current_user: Current authenticated user
    auth_manager: Authentication manager instance

Returns:
    dict[str, str]: Logout confirmation message

**Responses:**

- `200`: Successful Response

---

### POST /api/auth/invitation/send

**Send User Invitation**

Send a user invitation (admin only).

Args:
    request: Invitation request details
    current_admin: Current admin user
    invitation_service: User invitation service instance

Returns:
    UserInvitationResponse: Created invitation details

Raises:
    HTTPException: If invitation creation fails

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/auth/invitation/accept

**Accept User Invitation**

Accept a user invitation and get authentication token.

Args:
    token: Invitation token from URL parameter
    invitation_service: User invitation service instance

Returns:
    Token: JWT access token for the new user

Raises:
    HTTPException: If invitation token is invalid or expired

**Parameters:**

- `token` (query, required): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/auth/admin/users

**List Users**

List all users (admin only).

Returns:
    dict[str, Any]: List of users (placeholder for future implementation)

Note:
    This endpoint is a placeholder for future multi-user functionality
    when database-backed user management is implemented.

**Responses:**

- `200`: Successful Response

---

### GET /api/auth/admin/invitations

**List Invitations**

List user invitations (admin only).

Args:
    include_expired: Include expired invitations
    include_used: Include used invitations
    invitation_service: User invitation service instance

Returns:
    dict[str, Any]: List of invitations and statistics

**Parameters:**

- `include_expired` (query, optional): No description
- `include_used` (query, optional): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### DELETE /api/auth/admin/invitations/{invitation_id}

**Revoke Invitation**

Revoke a user invitation (admin only).

Args:
    invitation_id: ID of invitation to revoke
    invitation_service: User invitation service instance

Returns:
    dict[str, str]: Revocation confirmation

Raises:
    HTTPException: If invitation not found

**Parameters:**

- `invitation_id` (path, required): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/auth/admin/credentials

**Get Admin Credentials**

Get auto-generated admin credentials (one-time display only).

This endpoint returns auto-generated admin credentials only once for security.
After calling this endpoint, the credentials are cleared from memory.

Args:
    auth_manager: Authentication manager instance

Returns:
    AdminCredentials: Auto-generated admin credentials

Raises:
    HTTPException: If no credentials available or not in single-user mode

**Responses:**

- `200`: Successful Response

---

### GET /api/auth/admin/stats

**Get Auth Stats**

Get detailed authentication statistics (admin only).

Args:
    auth_manager: Authentication manager instance
    invitation_service: User invitation service instance

Returns:
    dict[str, Any]: Detailed authentication statistics

**Responses:**

- `200`: Successful Response

---

### GET /api/auth/lockout/status/{username}

**Get User Lockout Status**

Get lockout status for a specific user (admin only).

Args:
    username: Username to check lockout status for
    auth_manager: Authentication manager instance

Returns:
    LockoutStatus: Detailed lockout status for the user

**Parameters:**

- `username` (path, required): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/auth/lockout/status

**Get All Lockout Status**

Get lockout status for all tracked users (admin only).

Args:
    auth_manager: Authentication manager instance

Returns:
    list[LockoutStatus]: List of lockout status for all users

**Responses:**

- `200`: Successful Response

---

### POST /api/auth/lockout/unlock

**Unlock User Account**

Manually unlock a user account (admin only).

Args:
    unlock_request: Account unlock request
    current_admin: Current admin user
    auth_manager: Authentication manager instance

Returns:
    dict[str, str]: Unlock confirmation message

Raises:
    HTTPException: If lockout is disabled or account not locked

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/auth/mfa/setup

**Setup Mfa**

Set up MFA for the current user.

Args:
    current_user: Current authenticated user
    auth_manager: Authentication manager instance

Returns:
    MFASecretResponse: MFA setup information including QR code

Raises:
    HTTPException: If MFA is not available or already enabled

**Responses:**

- `200`: Successful Response

---

### POST /api/auth/mfa/verify-setup

**Verify Mfa Setup**

Verify MFA setup by validating a TOTP code.

Args:
    verification_request: MFA verification request with TOTP code
    current_user: Current authenticated user
    auth_manager: Authentication manager instance

Returns:
    dict[str, str]: Verification confirmation message

Raises:
    HTTPException: If verification fails or MFA not available

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/auth/mfa/verify

**Verify Mfa Code**

Verify an MFA code for authentication.

Args:
    verification_request: MFA verification request with TOTP or backup code
    current_user: Current authenticated user
    auth_manager: Authentication manager instance

Returns:
    dict[str, str]: Verification confirmation message

Raises:
    HTTPException: If verification fails or MFA not available

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/auth/mfa/status

**Get Mfa Status**

Get MFA status for the current user.

Args:
    current_user: Current authenticated user
    auth_manager: Authentication manager instance

Returns:
    MFAStatus: Current MFA status

Raises:
    HTTPException: If MFA is not available

**Responses:**

- `200`: Successful Response

---

### GET /api/auth/mfa/backup-codes

**Get Backup Codes**

Get backup codes for the current user (one-time display).

Args:
    current_user: Current authenticated user
    auth_manager: Authentication manager instance

Returns:
    BackupCodesResponse: Backup codes with warning

Raises:
    HTTPException: If MFA not available or not enabled

**Responses:**

- `200`: Successful Response

---

### POST /api/auth/mfa/regenerate-backup-codes

**Regenerate Backup Codes**

Regenerate backup codes for the current user.

Args:
    current_user: Current authenticated user
    auth_manager: Authentication manager instance

Returns:
    BackupCodesResponse: New backup codes with warning

Raises:
    HTTPException: If MFA not available or not enabled

**Responses:**

- `200`: Successful Response

---

### DELETE /api/auth/mfa/disable

**Disable Mfa**

Disable MFA for the current user.

Args:
    current_user: Current authenticated user
    auth_manager: Authentication manager instance

Returns:
    dict[str, str]: Disable confirmation message

Raises:
    HTTPException: If MFA not available or not enabled

**Responses:**

- `200`: Successful Response

---

### GET /api/auth/admin/mfa/status

**Get All Mfa Status**

Get MFA status for all users (admin only).

Args:
    auth_manager: Authentication manager instance

Returns:
    list[MFAStatus]: MFA status for all users

Raises:
    HTTPException: If MFA is not available

**Responses:**

- `200`: Successful Response

---

### POST /api/auth/admin/mfa/disable

**Admin Disable Mfa**

Disable MFA for a specific user (admin only).

Args:
    disable_request: MFA disable request
    current_admin: Current admin user
    auth_manager: Authentication manager instance

Returns:
    dict[str, str]: Disable confirmation message

Raises:
    HTTPException: If MFA not available or not enabled for user

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/auth/secure/login

**Secure Login**

Secure login with HttpOnly cookie token storage.

Args:
    form_data: Login form data (username and password)
    auth_manager: Authentication manager instance

Returns:
    Login success response with secure cookies set

Raises:
    HTTPException: If authentication fails

**Request Body:**

Content-Type: `application/x-www-form-urlencoded`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/auth/secure/refresh

**Secure Refresh**

Refresh access token using HttpOnly refresh token cookie.

Args:
    request: HTTP request with refresh token cookie
    auth_manager: Authentication manager instance

Returns:
    Refresh success response with new tokens

Raises:
    HTTPException: If refresh token is invalid

**Responses:**

- `200`: Successful Response

---

### POST /api/auth/secure/logout

**Secure Logout**

Secure logout with cookie cleanup and token revocation.

Args:
    request: HTTP request
    auth_manager: Authentication manager instance

Returns:
    Logout confirmation message

**Responses:**

- `200`: Successful Response

---

## can

### GET /api/can/queue/status

**Get CAN queue status**

Return the current status of the CAN transmission queue.

**Responses:**

- `200`: Queue status including length and capacity information

---

### GET /api/can/statistics/enhanced

**Get enhanced CAN statistics with PGN-level data and backend computation**

Enhanced CAN statistics with business logic computed on backend, including PGN analysis

**Responses:**

- `200`: Successful Response

---

### GET /api/can/metrics/computed

**Get backend-computed CAN metrics in frontend-compatible format**

Backend-computed CAN metrics with exact field mapping for frontend consumption

**Responses:**

- `200`: Successful Response

---

### GET /api/can/interfaces

**Get CAN interfaces**

Return a list of active CAN interfaces.

**Responses:**

- `200`: List of interface names

---

### GET /api/can/interfaces/details

**Get detailed interface information**

Return detailed information about all CAN interfaces.

**Responses:**

- `200`: Dictionary mapping interface names to their details

---

### POST /api/can/send

**Send raw CAN message**

Send a raw CAN message to the specified interface.

**Parameters:**

- `arbitration_id` (query, required): No description
- `data` (query, required): No description
- `interface` (query, required): No description

**Responses:**

- `200`: Send operation result
- `422`: Validation Error

---

### GET /api/can/recent

**Get recent CAN messages**

Return recent CAN messages captured on the bus.

**Parameters:**

- `limit` (query, optional): No description

**Responses:**

- `200`: List of recent CAN messages with metadata
- `422`: Validation Error

---

### GET /api/can/statistics

**Get CAN bus statistics**

Return statistics for all CAN bus interfaces.

**Responses:**

- `200`: Dictionary containing bus statistics and metrics

---

### GET /api/can/status

**Get Can Status**

Retrieves detailed status for all CAN interfaces the service is listening on.
Combines pyroute2 stats (if available) with the actual set of active interfaces.
On non-Linux platforms, returns a platform-specific message.

**Responses:**

- `200`: Successful Response

---

### GET /api/can/health

**Get Can Health**

Get basic health status of the CAN subsystem.

Returns a simple health check suitable for monitoring systems.
Includes overall health status, safety status, and emergency stop state.

**Responses:**

- `200`: Successful Response

---

### GET /api/can/health/comprehensive

**Get Can Comprehensive Health**

Get comprehensive health status including all subsystems.

Returns detailed health information including:
- Facade safety status and emergency stop state
- Individual service health statuses
- Performance metrics
- Queue depths and resource utilization

This endpoint is useful for detailed diagnostics and debugging.

**Responses:**

- `200`: Successful Response

---

### POST /api/can/emergency-stop

**Trigger Emergency Stop**

Trigger an emergency stop across all CAN services.

This is a safety-critical operation that will:
- Stop all CAN message transmission
- Halt all recording operations
- Disable message injection
- Put the system in a safe state

The system must be manually reset after an emergency stop.

**Parameters:**

- `reason` (query, required): Reason for emergency stop

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

## can-filter

### GET /api/can-filter/status

**Get Filter Status**

Get message filter status.

**Responses:**

- `200`: Successful Response

---

### GET /api/can-filter/rules

**List Filter Rules**

List all filter rules.

**Parameters:**

- `enabled_only` (query, optional): Only return enabled rules

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/can-filter/rules

**Create Filter Rule**

Create a new filter rule.

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/can-filter/rules/{rule_id}

**Get Filter Rule**

Get a specific filter rule.

**Parameters:**

- `rule_id` (path, required): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### PUT /api/can-filter/rules/{rule_id}

**Update Filter Rule**

Update an existing filter rule.

**Parameters:**

- `rule_id` (path, required): No description

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### DELETE /api/can-filter/rules/{rule_id}

**Delete Filter Rule**

Delete a filter rule.

**Parameters:**

- `rule_id` (path, required): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/can-filter/statistics

**Get Filter Statistics**

Get filter statistics.

**Responses:**

- `200`: Successful Response

---

### POST /api/can-filter/statistics/reset

**Reset Filter Statistics**

Reset filter statistics.

**Responses:**

- `200`: Successful Response

---

### GET /api/can-filter/capture

**Get Captured Messages**

Get captured messages.

**Parameters:**

- `limit` (query, optional): No description
- `since_timestamp` (query, optional): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### DELETE /api/can-filter/capture

**Clear Capture Buffer**

Clear the capture buffer.

**Responses:**

- `200`: Successful Response

---

### GET /api/can-filter/export

**Export Filter Rules**

Export filter rules as JSON.

**Responses:**

- `200`: Successful Response

---

### POST /api/can-filter/import

**Import Filter Rules**

Import filter rules from JSON.

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

## config

### GET /api/config/device_mapping

**Get device mapping configuration**

Returns the current device mapping configuration file content.

**Responses:**

- `200`: Successful Response

---

### GET /api/config/spec

**Get RV-C specification configuration**

Returns the current RV-C specification file content.

**Responses:**

- `200`: Successful Response

---

### GET /api/status/server

**Get server status**

Returns basic server status information including uptime and version.

**Responses:**

- `200`: Successful Response

---

### GET /api/status/application

**Get application status**

Returns application-specific status information including configuration and entity counts.

**Responses:**

- `200`: Successful Response

---

### GET /api/status/latest_release

**Get latest GitHub release**

Returns the latest GitHub release version and metadata.

**Responses:**

- `200`: Successful Response

---

### POST /api/status/force_update_check

**Force GitHub update check**

Forces an immediate GitHub update check and returns the new status.

**Responses:**

- `200`: Successful Response

---

### GET /api/status/features

**Get feature status**

Returns the current status of all services in the system.

**Responses:**

- `200`: Dictionary containing service states and metadata

---

### GET /api/config/settings

**Get Settings Overview**

Get current application settings with source information.

Returns configuration values showing which come from environment
variables vs defaults, without exposing sensitive information.

**Responses:**

- `200`: Successful Response

---

### GET /api/config/features

**Get Enhanced Feature Status**

Get current service status and availability.

**Responses:**

- `200`: Successful Response

---

### GET /api/config/can/interfaces

**Get Can Interface Mappings**

Get current CAN interface mappings.

**Responses:**

- `200`: Successful Response

---

### PUT /api/config/can/interfaces/{logical_name}

**Update Can Interface Mapping**

Update a CAN interface mapping (runtime only).

**Parameters:**

- `logical_name` (path, required): No description

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/config/can/interfaces/validate

**Validate Interface Mappings**

Validate a set of interface mappings.

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/config/database

**Get Database Configuration**

Get current database configuration.

Returns database settings with sensitive information redacted.

**Responses:**

- `200`: Successful Response

---

### GET /api/config/coach/interface-requirements

**Get Coach Interface Requirements**

Get coach interface requirements and compatibility validation.

**Responses:**

- `200`: Successful Response

---

### GET /api/config/coach/metadata

**Get Coach Mapping Metadata**

Get complete coach mapping metadata including interface analysis.

**Responses:**

- `200`: Successful Response

---

## dashboard

### GET /api/dashboard/summary

**Get dashboard summary**

Get complete aggregated dashboard data in a single optimized request.

**Responses:**

- `200`: Complete dashboard data including entities, system metrics, and activity feed

---

### GET /api/dashboard/entities

**Get entity statistics**

Get aggregated entity statistics and health information.

**Responses:**

- `200`: Entity summary with counts, health scores, and device type breakdown

---

### GET /api/dashboard/system

**Get system metrics**

Get system performance metrics and health indicators.

**Responses:**

- `200`: System metrics including uptime, performance, and resource usage

---

### GET /api/dashboard/can-bus

**Get CAN bus summary**

Get CAN bus status and performance summary.

**Responses:**

- `200`: CAN bus summary with interface count, message rates, and health status

---

### GET /api/dashboard/activity

**Get activity feed**

Get recent system activity and event feed.

**Parameters:**

- `limit` (query, optional): Maximum number of activities to return
- `since` (query, optional): Return activities since this timestamp

**Responses:**

- `200`: Activity feed with recent events, entity changes, and system notifications
- `422`: Validation Error

---

### POST /api/dashboard/bulk-control

**Bulk entity control**

Perform control operations on multiple entities in a single request.

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Results of bulk control operation with individual entity status
- `422`: Validation Error

---

### GET /api/dashboard/analytics

**Get system analytics**

Get system analytics, alerts, and performance monitoring data.

**Responses:**

- `200`: System analytics with active alerts, trends, and recommendations

---

### POST /api/dashboard/alerts/{alert_id}/acknowledge

**Acknowledge alert**

Acknowledge an active system alert.

**Parameters:**

- `alert_id` (path, required): No description

**Responses:**

- `200`: Acknowledgment status and confirmation
- `422`: Validation Error

---

## database

### GET /api/database/status

**Get Database Status**

Get current database schema status.

**Responses:**

- `200`: Successful Response

---

### POST /api/database/migrate

**Start Migration**

Start database migration process.

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/database/migrate/{job_id}/status

**Get Migration Progress**

Get migration job progress.

**Parameters:**

- `job_id` (path, required): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/database/history

**Get Migration History**

Get migration history.

**Parameters:**

- `limit` (query, optional): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/database/safety-check

**Check Migration Safety**

Get detailed safety check for migration.

**Responses:**

- `200`: Successful Response

---

## dbc

### POST /api/dbc/upload

**Upload Dbc**

Upload and load a DBC file.

Args:
    file: DBC file to upload
    name: Optional name for the DBC (defaults to filename)

Returns:
    Upload response with DBC statistics

**Parameters:**

- `name` (query, optional): No description

**Request Body:**

Content-Type: `multipart/form-data`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/dbc/list

**List Dbcs**

List all loaded DBC files.

Returns:
    List of loaded DBCs and active DBC

**Responses:**

- `200`: Successful Response

---

### POST /api/dbc/active/{name}

**Set Active Dbc**

Set the active DBC for decoding.

Args:
    name: Name of DBC to make active

Returns:
    Success message

**Parameters:**

- `name` (path, required): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/dbc/messages/{name}

**Get Dbc Messages**

Get all messages from a specific DBC.

Args:
    name: Name of the DBC

Returns:
    List of messages with signals

**Parameters:**

- `name` (path, required): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/dbc/export/{name}

**Export Dbc**

Export a loaded DBC to file.

Args:
    name: Name of the DBC to export

Returns:
    DBC file download

**Parameters:**

- `name` (path, required): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/dbc/convert/rvc-to-dbc

**Convert Rvc To Dbc**

Convert current RV-C configuration to DBC format.

Returns:
    DBC file download

**Responses:**

- `200`: Successful Response

---

### POST /api/dbc/convert/dbc-to-rvc

**Convert Dbc To Rvc**

Convert uploaded DBC file to RV-C JSON format.

Args:
    file: DBC file to convert

Returns:
    RV-C configuration JSON

**Request Body:**

Content-Type: `multipart/form-data`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/dbc/search/{signal_name}

**Search Signal**

Search for a signal across all loaded DBCs.

Args:
    signal_name: Name of signal to search for

Returns:
    List of matches with DBC and message info

**Parameters:**

- `signal_name` (path, required): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

## device_discovery

### GET /api/discovery/topology

**Get network topology**

Return the current network topology with discovered devices and their status.

**Responses:**

- `200`: Network topology information including devices, protocols, and health metrics

---

### GET /api/discovery/availability

**Get device availability**

Return device availability statistics and status information.

**Responses:**

- `200`: Device availability metrics including online/offline counts and protocol distribution

---

### POST /api/discovery/discover

**Discover devices**

Perform active device discovery for a specific protocol.

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Discovery results with found devices and their information
- `422`: Validation Error

---

### POST /api/discovery/poll

**Poll device**

Send a polling request to a specific device for status information.

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Polling request status and information
- `422`: Validation Error

---

### GET /api/discovery/status

**Get discovery service status**

Return the current status and configuration of the device discovery service.

**Responses:**

- `200`: Service status including configuration and runtime information

---

### GET /api/discovery/protocols

**Get supported protocols**

Return information about supported protocols for device discovery.

**Responses:**

- `200`: List of supported protocols and their configuration

---

### POST /api/discovery/wizard/auto-discover

**Start auto-discovery wizard**

Begin an intelligent auto-discovery process with step-by-step guidance.

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Auto-discovery wizard results with discovered devices and setup recommendations
- `422`: Validation Error

---

### POST /api/discovery/wizard/setup-device

**Setup discovered device**

Configure a discovered device with guided setup wizard.

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Device setup results and configuration status
- `422`: Validation Error

---

### GET /api/discovery/wizard/device-profile/{device_address}

**Get device profile**

Get detailed device profile with capabilities and configuration options.

**Parameters:**

- `device_address` (path, required): No description
- `protocol` (query, optional): Protocol to use for device profiling

**Responses:**

- `200`: Comprehensive device profile with setup recommendations
- `422`: Validation Error

---

### GET /api/discovery/wizard/setup-recommendations

**Get setup recommendations**

Get intelligent setup recommendations based on discovered devices.

**Parameters:**

- `include_configured` (query, optional): Include already configured devices

**Responses:**

- `200`: Setup recommendations and configuration suggestions
- `422`: Validation Error

---

### GET /api/discovery/network-map

**Get enhanced network map**

Get comprehensive network topology map with device relationships.

**Parameters:**

- `include_offline` (query, optional): Include offline devices
- `group_by_protocol` (query, optional): Group devices by protocol

**Responses:**

- `200`: Enhanced network topology with device relationships and health metrics
- `422`: Validation Error

---

## diagnostics

### GET /api/diagnostics/health

**Get System Health**

Get comprehensive system health status.

Args:
    system_type: Optional specific system to query, or None for all systems

Returns:
    System health response with scores and recommendations

**Parameters:**

- `system_type` (query, optional): Specific system to query

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

## diagnostics-v2

### GET /api/v2/diagnostics/health

**Health Check**

Health check endpoint for diagnostics domain API

**Responses:**

- `200`: Successful Response

---

### GET /api/v2/diagnostics/schemas

**Get Schemas**

Export schemas for diagnostics domain

**Responses:**

- `200`: Successful Response

---

### GET /api/v2/diagnostics/metrics

**Get System Metrics**

Get real-time system performance metrics

**Responses:**

- `200`: Successful Response

---

### GET /api/v2/diagnostics/faults

**Get Fault Summary**

Get fault summary with domain-specific aggregations

**Parameters:**

- `system_type` (query, optional): Filter by system type
- `severity` (query, optional): Filter by severity

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/v2/diagnostics/system-status

**Get System Status**

Get overall system health status

**Responses:**

- `200`: Successful Response

---

### GET /api/v2/diagnostics/dtcs

**Get Dtcs**

Get diagnostic trouble codes

**Parameters:**

- `system_type` (query, optional): Filter by system type
- `severity` (query, optional): Filter by severity
- `protocol` (query, optional): Filter by protocol

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/v2/diagnostics/dtcs/resolve

**Resolve Dtc**

Resolve a diagnostic trouble code

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/v2/diagnostics/statistics

**Get Statistics**

Get diagnostic statistics

**Responses:**

- `200`: Successful Response

---

### GET /api/v2/diagnostics/correlations

**Get Correlations**

Get fault correlations

**Parameters:**

- `time_window_seconds` (query, optional): Time window for correlation analysis

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/v2/diagnostics/predictions

**Get Predictions**

Get maintenance predictions

**Parameters:**

- `time_horizon_days` (query, optional): Time horizon for predictions in days

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

## documentation

### GET /api/docs/status

**Get documentation search status**

Returns the status of the vector search service and its configuration.

**Responses:**

- `200`: Successful Response

---

### GET /api/docs/search

**Search RV-C documentation**

Search the RV-C documentation using vector-based semantic search.

**Parameters:**

- `query` (query, required): Search query string
- `k` (query, optional): Number of results to return

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/docs/openapi

**Get OpenAPI schema**

Returns the complete OpenAPI schema for the API.

**Responses:**

- `200`: Successful Response

---

## entities-v2

### GET /api/v2/entities/health

**Health Check**

Comprehensive health check for Pi RV deployment debugging

**Responses:**

- `200`: Successful Response

---

### GET /api/v2/entities/schemas

**Get Schemas**

Export Pydantic schemas as JSON Schema for frontend validation

**Responses:**

- `200`: Successful Response

---

### GET /api/v2/entities/debug/system-info

**Get Debug Info**

Comprehensive debug information for RV Pi troubleshooting

**Responses:**

- `200`: Successful Response

---

### GET /api/v2/entities

**Get Entities**

Get entities with filtering and pagination (v2) - optimized for Pi deployment

**Parameters:**

- `device_type` (query, optional): Filter by device type
- `area` (query, optional): Filter by area
- `protocol` (query, optional): Filter by protocol
- `page` (query, optional): Page number
- `page_size` (query, optional): Items per page

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/v2/entities/safety-status

**Get Safety Status**

Get current safety system status

**Responses:**

- `200`: Successful Response

---

### GET /api/v2/entities/metadata

**Get Entity Metadata**

Get metadata about entity types, areas, and capabilities

**Responses:**

- `200`: Successful Response

---

### GET /api/v2/entities/protocol-summary

**Get Protocol Summary**

Get summary of entity distribution across protocols

**Responses:**

- `200`: Successful Response

---

### GET /api/v2/entities/debug/unmapped

**Get Unmapped Entries**

Get unmapped DGN/instance pairs observed on CAN bus

**Responses:**

- `200`: Successful Response

---

### GET /api/v2/entities/debug/unknown-pgns

**Get Unknown Pgns**

Get unknown PGNs observed on CAN bus

**Responses:**

- `200`: Successful Response

---

### GET /api/v2/entities/debug/missing-dgns

**Get Missing Dgns**

Get DGNs encountered but not in specification

**Responses:**

- `200`: Successful Response

---

### POST /api/v2/entities/mappings

**Create Entity Mapping**

Create new entity mapping from unmapped entry

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/v2/entities/{entity_id}

**Get Entity**

Get a specific entity by ID (v2)

**Parameters:**

- `entity_id` (path, required): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/v2/entities/{entity_id}/control

**Control Entity**

Control a single entity with safety validation (v2) - Pi optimized

**Parameters:**

- `entity_id` (path, required): No description

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/v2/entities/bulk-control

**Bulk Control Entities**

Execute bulk control operations with safety validation (v2) - Pi optimized

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/v2/entities/emergency-stop

**Emergency Stop**

Emergency stop - immediately halt all entity operations (Admin Only)

**Responses:**

- `200`: Successful Response

---

### POST /api/v2/entities/clear-emergency-stop

**Clear Emergency Stop**

Clear emergency stop condition (Admin Only)

**Responses:**

- `200`: Successful Response

---

### POST /api/v2/entities/reconcile-state

**Reconcile State With Rvc Bus**

Reconcile application state with RV-C bus state

**Responses:**

- `200`: Successful Response

---

### GET /api/v2/entities/{entity_id}/history

**Get Entity History**

Get entity state change history

**Parameters:**

- `entity_id` (path, required): No description
- `limit` (query, optional): Maximum number of history entries
- `since` (query, optional): Unix timestamp filter

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

## health

### GET /api/health

**Comprehensive health check**

Returns detailed health status including ServiceRegistry information

**Parameters:**

- `include_registry` (query, optional): Include ServiceRegistry details
- `include_metrics` (query, optional): Include startup metrics
- `include_components` (query, optional): Include component health details

**Responses:**

- `200`: Successful Response
- `503`: Service unavailable
- `500`: Internal server error
- `422`: Validation Error

---

### GET /api/health/services

**Individual service health status**

Returns health status for all registered services

**Parameters:**

- `service_name` (query, optional): Filter by service name
- `status` (query, optional): Filter by status

**Responses:**

- `200`: Successful Response
- `503`: Service unavailable
- `500`: Internal server error
- `422`: Validation Error

---

### GET /api/health/ready

**Readiness check with ServiceRegistry**

Lightweight readiness check based on ServiceRegistry status

**Parameters:**

- `min_healthy_services` (query, optional): Minimum number of healthy services required

**Responses:**

- `200`: Successful Response
- `503`: Service unavailable
- `500`: Internal server error
- `422`: Validation Error

---

### GET /api/health/startup

**Startup metrics and timing**

Returns detailed startup performance metrics from ServiceRegistry

**Responses:**

- `200`: Successful Response
- `503`: Service unavailable
- `500`: Internal server error

---

## logs

### GET /api/logs/history

**Get historical logs**

Query historical logs from journald. Supports filtering by time, level, module, and pagination via cursor.

    Only available on systems with systemd/journald.

**Parameters:**

- `since` (query, optional): No description
- `until` (query, optional): No description
- `level` (query, optional): No description
- `module` (query, optional): No description
- `cursor` (query, optional): No description
- `limit` (query, optional): Max number of log entries to return

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

## monitoring

### GET /api/health

**Comprehensive health check**

Returns detailed health status including ServiceRegistry information

**Parameters:**

- `include_registry` (query, optional): Include ServiceRegistry details
- `include_metrics` (query, optional): Include startup metrics
- `include_components` (query, optional): Include component health details

**Responses:**

- `200`: Successful Response
- `503`: Service unavailable
- `500`: Internal server error
- `422`: Validation Error

---

### GET /api/health/services

**Individual service health status**

Returns health status for all registered services

**Parameters:**

- `service_name` (query, optional): Filter by service name
- `status` (query, optional): Filter by status

**Responses:**

- `200`: Successful Response
- `503`: Service unavailable
- `500`: Internal server error
- `422`: Validation Error

---

### GET /api/health/ready

**Readiness check with ServiceRegistry**

Lightweight readiness check based on ServiceRegistry status

**Parameters:**

- `min_healthy_services` (query, optional): Minimum number of healthy services required

**Responses:**

- `200`: Successful Response
- `503`: Service unavailable
- `500`: Internal server error
- `422`: Validation Error

---

### GET /api/health/startup

**Startup metrics and timing**

Returns detailed startup performance metrics from ServiceRegistry

**Responses:**

- `200`: Successful Response
- `503`: Service unavailable
- `500`: Internal server error

---

## multi-network

### GET /api/multi-network/status

**Get Multi Network Status**

Get the status of multi-network CAN management.

Returns:
    Multi-network status information including network health and statistics

**Responses:**

- `200`: Successful Response

---

### GET /api/multi-network/bridge-status

**Get Bridge Status**

Get the status of protocol bridges between different CAN networks.

Returns:
    Bridge status information including translation statistics and health

**Responses:**

- `200`: Successful Response

---

### GET /api/multi-network/networks

**Get Networks**

Get information about all registered CAN networks.

Returns:
    Network information including health status and configuration

**Responses:**

- `200`: Successful Response

---

### GET /api/multi-network/health

**Get Multi Network Health**

Get comprehensive health status of the multi-network system.

Returns:
    Health status including service status, network health, and diagnostics

**Responses:**

- `200`: Successful Response

---

## networks-v2

### GET /api/v2/networks/health

**Health Check**

Health check endpoint for networks domain API

**Responses:**

- `200`: Successful Response

---

### GET /api/v2/networks/schemas

**Get Schemas**

Export schemas for networks domain

**Responses:**

- `200`: Successful Response

---

### GET /api/v2/networks/status

**Get Network Status**

Get overall network status and statistics

**Responses:**

- `200`: Successful Response

---

### GET /api/v2/networks/interfaces

**Get Network Interfaces**

Get detailed information about network interfaces

**Responses:**

- `200`: Successful Response

---

## notification-analytics

### GET /api/notification-analytics/metrics

**Get Metrics**

Get aggregated notification metrics.

Returns time-series data for the specified metric type and period.

**Parameters:**

- `metric_type` (query, required): Type of metric
- `start_date` (query, required): Start date
- `aggregation_period` (query, optional): Aggregation period
- `end_date` (query, optional): End date
- `channel` (query, optional): Filter by channel
- `notification_type` (query, optional): Filter by type

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/notification-analytics/channels

**Get Channel Metrics**

Get performance metrics for notification channels.

Returns detailed metrics for each channel including success rates,
delivery times, and error breakdowns.

**Parameters:**

- `start_date` (query, optional): Start date
- `end_date` (query, optional): End date
- `channel` (query, optional): Specific channel

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/notification-analytics/errors

**Analyze Errors**

Analyze notification delivery errors.

Returns error patterns, frequencies, and recommendations for
improving delivery success rates.

**Parameters:**

- `start_date` (query, optional): Start date
- `end_date` (query, optional): End date
- `min_occurrences` (query, optional): Minimum occurrences

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/notification-analytics/queue/health

**Get Queue Health**

Get current notification queue health status.

Returns real-time metrics about queue performance and health indicators.

**Responses:**

- `200`: Successful Response

---

### POST /api/notification-analytics/reports/generate

**Generate Report**

Generate a notification analytics report.

Creates a report using the specified template and returns the report ID
for downloading.

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/notification-analytics/reports/{report_id}

**Get Report**

Get report metadata by ID.

Returns information about a generated report including its status
and download URL.

**Parameters:**

- `report_id` (path, required): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/notification-analytics/reports/{report_id}/download

**Download Report**

Download a generated report.

Returns the report file in the format it was generated.

**Parameters:**

- `report_id` (path, required): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/notification-analytics/reports

**List Reports**

List generated reports.

Returns a list of reports with optional filtering.

**Parameters:**

- `report_type` (query, optional): Filter by report type
- `start_date` (query, optional): Filter by generation date start
- `end_date` (query, optional): Filter by generation date end
- `limit` (query, optional): Maximum results

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/notification-analytics/reports/schedule

**Schedule Report**

Schedule a recurring report.

Creates a scheduled report that will be generated automatically
based on the specified schedule.

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### DELETE /api/notification-analytics/reports/schedule/{schedule_id}

**Unschedule Report**

Remove a scheduled report.

Cancels a scheduled report by ID.

**Parameters:**

- `schedule_id` (path, required): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/notification-analytics/dashboard

**Get Dashboard Metrics**

Get dashboard metrics for real-time monitoring.

Returns a comprehensive set of metrics suitable for dashboard display.

**Responses:**

- `200`: Successful Response

---

### POST /api/notification-analytics/engagement/{notification_id}

**Track Engagement**

Track user engagement with a notification.

Records when a notification is opened, clicked, or dismissed.

**Parameters:**

- `notification_id` (path, required): No description
- `action` (query, required): Action type: opened, clicked, dismissed

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

## notification-dashboard

### GET /api/notifications/dashboard/health

**Get System Health**

Get comprehensive notification system health status.

Returns overall system health including component status, performance
indicators, and active alerts/warnings.

**Responses:**

- `200`: Successful Response

---

### GET /api/notifications/dashboard/metrics

**Get System Metrics**

Get comprehensive notification system metrics over specified time range.

Args:
    hours: Time range for metrics (1-168 hours)

Returns:
    Detailed system metrics including volume, performance, and trends

**Parameters:**

- `hours` (query, optional): Time range in hours

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/notifications/dashboard/queue-stats

**Get Queue Statistics**

Get detailed notification queue statistics and health information.

Returns comprehensive queue status including pending counts, processing
times, throughput, and capacity utilization.

**Responses:**

- `200`: Successful Response

---

### GET /api/notifications/dashboard/rate-limiting

**Get Rate Limiting Status**

Get rate limiting system status and statistics.

Returns token bucket status, request statistics, debouncing effectiveness,
and per-channel rate limiting information.

**Responses:**

- `200`: Successful Response

---

### GET /api/notifications/dashboard/channels/health

**Get Channel Health**

Get health status for all notification channels.

Returns detailed health information for each configured notification
channel including connectivity, recent success rates, and error information.

**Responses:**

- `200`: Successful Response

---

### POST /api/notifications/dashboard/test

**Trigger Test Notifications**

Trigger test notifications for monitoring and verification.

Args:
    channels: Optional list of specific channels to test

Returns:
    Test results for each channel

**Parameters:**

- `channels` (query, optional): Specific channels to test

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/notifications/dashboard/alerts/config

**Get Alert Configuration**

Get current alert configuration thresholds.

Returns the configuration for dashboard alerts including queue depth,
success rate, processing time, and age thresholds.

**Responses:**

- `200`: Successful Response

---

### PUT /api/notifications/dashboard/alerts/config

**Update Alert Configuration**

Update alert configuration thresholds.

Args:
    config: New alert configuration

Returns:
    Updated alert configuration

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/notifications/dashboard/export/metrics

**Export Metrics**

Export notification system metrics in various formats.

Args:
    format: Export format (json, csv, prometheus)
    hours: Time range for metrics

Returns:
    Metrics data in requested format

**Parameters:**

- `format` (query, optional): No description
- `hours` (query, optional): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

## pattern-analysis

### GET /api/pattern-analysis/summary

**Get Pattern Summary**

Get summary of all pattern analysis results.

Returns:
    Summary statistics for all tracked messages

**Responses:**

- `200`: Successful Response

---

### GET /api/pattern-analysis/message/{arbitration_id}

**Get Message Analysis**

Get detailed pattern analysis for a specific message ID.

Args:
    arbitration_id: CAN message arbitration ID (decimal)

Returns:
    Detailed analysis results for the message

**Parameters:**

- `arbitration_id` (path, required): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/pattern-analysis/message-hex/{arbitration_id_hex}

**Get Message Analysis Hex**

Get detailed pattern analysis for a specific message ID (hex format).

Args:
    arbitration_id_hex: CAN message arbitration ID in hex format (e.g., "1FFFFFFF")

Returns:
    Detailed analysis results for the message

**Parameters:**

- `arbitration_id_hex` (path, required): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/pattern-analysis/messages

**List Analyzed Messages**

List all messages with pattern analysis data.

Args:
    classification: Filter by message classification (periodic, event, mixed)
    min_count: Minimum number of message observations
    limit: Maximum number of results to return

Returns:
    List of messages with basic analysis info

**Parameters:**

- `classification` (query, optional): Filter by classification
- `min_count` (query, optional): Minimum message count
- `limit` (query, optional): Maximum number of results

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/pattern-analysis/correlations/{arbitration_id}

**Get Message Correlations**

Get messages correlated with the specified message ID.

Args:
    arbitration_id: Target message arbitration ID
    min_correlation: Minimum correlation score (0.0-1.0)

Returns:
    List of correlated messages with correlation scores

**Parameters:**

- `arbitration_id` (path, required): No description
- `min_correlation` (query, optional): Minimum correlation threshold

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/pattern-analysis/export/provisional-dbc

**Export Provisional Dbc**

Export discovered message patterns as a provisional DBC file.

Returns:
    DBC file content for download

**Responses:**

- `200`: Successful Response

---

### GET /api/pattern-analysis/bit-analysis/{arbitration_id}

**Get Bit Analysis**

Get detailed bit-level analysis for a specific message.

Args:
    arbitration_id: Message arbitration ID
    min_changes: Minimum number of changes to include a bit

Returns:
    Detailed bit change patterns

**Parameters:**

- `arbitration_id` (path, required): No description
- `min_changes` (query, optional): Minimum number of bit changes

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/pattern-analysis/reset

**Reset Pattern Analysis**

Reset all pattern analysis data.

This clears all accumulated pattern data and starts fresh analysis.
Use with caution as this will lose all historical pattern information.

Returns:
    Confirmation message

**Responses:**

- `200`: Successful Response

---

## performance

### GET /api/performance/health-computed

**Get backend-computed health status with UI categorization**

Get comprehensive health status with backend-computed thresholds and UI classification.

This endpoint performs all business logic computation on the backend, removing the need
for frontend threshold calculations. Returns status classification ready for UI display.

**Responses:**

- `200`: Successful Response

---

### GET /api/performance/resources-computed

**Get backend-computed resource utilization with status classification**

Get resource utilization with backend-computed threshold-based status classification.

Eliminates frontend business logic for resource status determination by applying
configurable thresholds on the backend and returning ready-to-display status.

**Responses:**

- `200`: Successful Response

---

### GET /api/performance/api-performance-computed

**Get backend-computed API performance with status classification**

Get API performance metrics with backend-computed status classification.

Applies business logic thresholds on the backend to determine performance status,
eliminating the need for frontend threshold calculations.

**Responses:**

- `200`: Successful Response

---

### GET /api/performance/status

**Get Performance Analytics Status**

Get comprehensive performance analytics status.

Returns:
    Detailed status including configuration, statistics, and component health

**Responses:**

- `200`: Successful Response

---

### POST /api/performance/telemetry/protocol

**Record Protocol Telemetry**

Record protocol message processing performance data.

Args:
    telemetry_request: Protocol telemetry data

Returns:
    Success status

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/performance/telemetry/api

**Record Api Performance**

Record API request performance data.

Args:
    api_request: API performance data

Returns:
    Success status

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/performance/telemetry/websocket

**Record Websocket Latency**

Record WebSocket latency data.

Args:
    websocket_request: WebSocket latency data

Returns:
    Success status

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/performance/telemetry/can-interface

**Record Can Interface Load**

Record CAN interface load and performance data.

Args:
    can_request: CAN interface performance data

Returns:
    Success status

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/performance/metrics

**Get Performance Metrics**

Get current performance metrics with optional filtering.

Args:
    metric_type: Specific metric type to retrieve
    time_window_seconds: Time window for metrics

Returns:
    List of performance metrics

**Parameters:**

- `metric_type` (query, optional): Specific metric type to retrieve
- `time_window_seconds` (query, optional): Time window for metrics

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/performance/resource-utilization

**Get Resource Utilization**

Get current system resource utilization.

Returns:
    Resource utilization data for CPU, memory, network, and CAN interfaces

**Responses:**

- `200`: Successful Response

---

### GET /api/performance/trends

**Get Performance Trends**

Get performance trend analysis.

Args:
    metric_type: Specific metric type or None for all trends

Returns:
    Performance trend analysis data

**Parameters:**

- `metric_type` (query, optional): Specific metric type for trends

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/performance/baseline-deviations

**Get Baseline Deviations**

Get performance baseline deviations.

Args:
    time_window_seconds: Time window for deviation analysis

Returns:
    List of baseline deviation alerts

**Parameters:**

- `time_window_seconds` (query, optional): Time window for deviations

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/performance/optimization-recommendations

**Get Optimization Recommendations**

Get automated optimization recommendations.

Returns:
    List of optimization recommendations with implementation details

**Responses:**

- `200`: Successful Response

---

### POST /api/performance/report

**Generate Performance Report**

Generate comprehensive performance analysis report.

Args:
    report_request: Report generation parameters

Returns:
    Comprehensive performance report including metrics, trends, and recommendations

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/performance/protocol-throughput

**Get Protocol Throughput**

Get current protocol throughput metrics.

Returns:
    Dictionary of protocol names to messages per second

**Responses:**

- `200`: Successful Response

---

### GET /api/performance/statistics

**Get Analytics Statistics**

Get comprehensive performance analytics statistics.

Returns:
    Statistics from all analytics components including telemetry, benchmarking, trends, and optimization

**Responses:**

- `200`: Successful Response

---

### DELETE /api/performance/reset-baselines

**Reset Performance Baselines**

Reset all performance baselines (admin operation).

Returns:
    Success status

**Responses:**

- `200`: Successful Response

---

## pin-authentication

### POST /api/pin-auth/validate

**Validate Pin**

Validate a PIN and create authorization session.

Creates a time-limited session that can be used to authorize
safety-critical operations. Sessions are single-use for emergency
operations and multi-use for maintenance operations.

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/pin-auth/authorize

**Authorize Operation**

Authorize an operation using PIN session.

Consumes a PIN session to authorize a specific safety-critical operation.
Some sessions are single-use (emergency) while others allow multiple
operations (maintenance).

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### DELETE /api/pin-auth/sessions/{session_id}

**Revoke Session**

Revoke a specific PIN session.

Users can revoke their own sessions. Admins can revoke any session.

**Parameters:**

- `session_id` (path, required): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### DELETE /api/pin-auth/sessions

**Revoke All User Sessions**

Revoke all PIN sessions for the current user.

Useful for security cleanup or when leaving the RV.

**Responses:**

- `200`: Successful Response

---

### GET /api/pin-auth/status

**Get Pin Status**

Get PIN status for the current user.

Shows lockout status, active sessions, and PIN availability.

**Responses:**

- `200`: Successful Response

---

### GET /api/pin-auth/admin/system-status

**Get System Status**

Get overall PIN system status (Admin only).

Provides system-wide statistics and health information.

**Responses:**

- `200`: Successful Response

---

### POST /api/pin-auth/admin/rotate-pins

**Rotate Pins**

Generate new PINs for all types (Admin only).

This is a security operation that revokes all existing sessions
and generates new PINs. Use with caution.

**Responses:**

- `200`: Successful Response

---

### GET /api/pin-auth/admin/user-status/{user_id}

**Get User Pin Status**

Get PIN status for a specific user (Admin only).

Provides detailed information about user's PIN authentication status.

**Parameters:**

- `user_id` (path, required): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/pin-auth/admin/unlock-user/{user_id}

**Unlock User**

Unlock a user from PIN lockout (Admin only).

Clears PIN attempt failures and removes lockout for the specified user.

**Parameters:**

- `user_id` (path, required): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/pin-auth/security-status

**Get Security Status Compat**

Get security status (compatibility endpoint for frontend).

Maps to the system status endpoint for consistency.

**Responses:**

- `200`: Successful Response

---

### GET /api/pin-auth/pins

**Get User Pins**

Get configured PINs for the current user.

Returns information about available PIN types without revealing actual PINs.

**Responses:**

- `200`: Successful Response

---

## predictive-maintenance

### GET /api/predictive-maintenance/maintenance/history

**Get maintenance history**

Get maintenance history for components.

**Parameters:**

- `component_id` (query, optional): Filter by component
- `maintenance_type` (query, optional): Filter by maintenance type
- `days` (query, optional): Number of days to retrieve

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

## safety

### GET /api/safety/status

**Get Safety Status**

Get comprehensive safety system status.

Returns current state of all safety systems including:
- Safe state status
- Emergency stop status
- Watchdog timer status
- Safety interlock states
- System state information
- Audit log entry count

**Responses:**

- `200`: Successful Response

---

### POST /api/safety/update-state

**Update System State**

Update system state information used by safety interlocks.

This endpoint allows updating vehicle state information that
safety interlocks use to determine if operations are safe.

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/safety/interlocks

**Get Interlock Status**

Get status of all safety interlocks.

Returns detailed information about each safety interlock including:
- Engagement status
- Protected feature
- Required conditions
- Engagement time and reason

**Responses:**

- `200`: Successful Response

---

### POST /api/safety/interlocks/check

**Check Interlocks**

Manually trigger safety interlock checks.

Forces an immediate check of all safety interlocks and returns
the results. Interlocks will be engaged/disengaged as needed.

**Responses:**

- `200`: Successful Response

---

### POST /api/safety/emergency-stop

**Trigger Emergency Stop**

Trigger emergency stop for all position-critical features.

This will:
- Stop all position-critical features
- Engage all safety interlocks
- Enter system-wide safe state
- Log the event to audit trail

WARNING: This is a safety-critical operation that requires
manual reset with authorization.

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/safety/emergency-stop/reset

**Reset Emergency Stop**

Reset emergency stop with authorization.

Requires valid authorization code. After reset, individual
features and interlocks must be manually re-enabled.

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/safety/audit-log

**Get Audit Log**

Get safety audit log entries.

Returns recent safety-critical events including:
- Interlock engagements/disengagements
- Emergency stops
- Safe state entries
- System errors

Args:
    max_entries: Maximum number of entries to return (default: 100)

**Parameters:**

- `max_entries` (query, optional): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/safety/health

**Get Safety Health**

Get safety service health status.

Returns information about the safety monitoring system itself:
- Monitoring task status
- Watchdog timer health
- Last check timestamps

**Responses:**

- `200`: Successful Response

---

### POST /api/safety/pin/emergency-stop

**Pin Emergency Stop**

Trigger emergency stop using PIN authorization (Admin Only).

Requires valid PIN session for emergency operations.
Provides enhanced security for safety-critical operations.

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/safety/pin/emergency-stop/reset

**Pin Emergency Reset**

Reset emergency stop using PIN authorization (Admin Only).

Requires valid PIN session for reset operations.
Provides enhanced security for safety-critical operations.

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/safety/pin/interlocks/override

**Pin Override Interlock**

Override a safety interlock using PIN authorization (Admin Only).

Allows temporary override of safety interlocks for maintenance or
diagnostic operations. Requires valid PIN session with override permissions.
Override will automatically expire after the specified duration.

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/safety/interlocks/clear-override

**Clear Interlock Override**

Clear an active interlock override (Admin Only).

Immediately removes any active override on the specified interlock,
returning it to normal operation.

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/safety/interlocks/overrides

**Get Active Overrides**

Get all active interlock overrides (Admin Only).

Returns information about currently active interlock overrides including
who authorized them, when they expire, and the reason for override.

**Responses:**

- `200`: Successful Response

---

### POST /api/safety/pin/maintenance-mode/enter

**Pin Enter Maintenance Mode**

Enter maintenance mode using PIN authorization (Admin Only).

In maintenance mode:
- Safety interlocks can be temporarily overridden
- Certain safety checks may be relaxed for service operations
- All actions are fully audited
- Mode automatically expires after the specified duration

Requires valid PIN session with maintenance permissions.

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/safety/pin/maintenance-mode/exit

**Pin Exit Maintenance Mode**

Exit maintenance mode using PIN authorization (Admin Only).

Returns system to normal operational mode:
- All safety interlocks return to normal operation
- Any active overrides are cleared
- Full safety validation resumes

Requires valid PIN session.

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/safety/operational-mode

**Get Operational Mode**

Get current operational mode and session details.

Returns information about the current operational mode including:
- Current mode (normal, maintenance, diagnostic)
- Who activated the mode
- When it was activated and when it expires
- Active overrides count

**Responses:**

- `200`: Successful Response

---

### POST /api/safety/pin/diagnostic-mode/enter

**Pin Enter Diagnostic Mode**

Enter diagnostic mode using PIN authorization (Admin Only).

In diagnostic mode:
- System diagnostics and testing can be performed
- Test procedures may temporarily modify safety constraints
- All actions are fully audited
- Mode automatically expires after the specified duration

WARNING: Diagnostic mode is intended for troubleshooting only.
Safety constraints may be modified during diagnostics.

Requires valid PIN session with diagnostic permissions.

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/safety/pin/diagnostic-mode/exit

**Pin Exit Diagnostic Mode**

Exit diagnostic mode using PIN authorization (Admin Only).

Returns system to normal operational mode:
- All safety constraints return to normal operation
- Any diagnostic overrides are cleared
- Full safety validation resumes

Requires valid PIN session.

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

## schemas

### GET /api/schemas/

**Get all available schemas**

Export all Zod-compatible schemas for frontend validation.

Provides comprehensive schema definitions for Domain API v2 with
safety-critical validation requirements.

**Responses:**

- `200`: Successful Response

---

### GET /api/schemas/list

**Get list of available schema names**

Get list of available schema names with metadata

**Responses:**

- `200`: Successful Response

---

### GET /api/schemas/{schema_name}

**Get specific schema by name**

Get a specific schema by name for targeted validation.

Args:
    schema_name: Name of the schema to retrieve (Entity, ControlCommand, etc.)

**Parameters:**

- `schema_name` (path, required): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/schemas/validate/integrity

**Validate schema integrity**

Validate that all schemas can be properly exported.

Used for system health checks and debugging schema issues.
Requires authentication as it's an administrative endpoint.

**Responses:**

- `200`: Successful Response

---

### GET /api/schemas/docs/openapi

**Get OpenAPI-compatible schema definitions**

Get OpenAPI-compatible schema definitions for documentation generation.

This endpoint provides schemas in OpenAPI format for integration with
API documentation tools and code generators.

**Parameters:**

- `include_examples` (query, optional): Include schema examples

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

## security

### GET /api/security/status

**Get Security Status**

Get overall security monitoring status.

Returns:
    Comprehensive security status including statistics and alert summary

**Responses:**

- `200`: Successful Response

---

### GET /api/security/alerts

**Get Security Alerts**

Get security alerts with optional filtering.

Args:
    since: Timestamp to filter alerts from
    severity: Filter by severity (low, medium, high, critical)
    anomaly_type: Filter by anomaly type
    limit: Maximum number of alerts to return

Returns:
    List of security alerts matching criteria

**Parameters:**

- `since` (query, optional): Timestamp to filter from
- `severity` (query, optional): Filter by severity level
- `anomaly_type` (query, optional): Filter by anomaly type
- `limit` (query, optional): Maximum number of alerts to return

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/security/alerts/summary

**Get Alerts Summary**

Get summary of recent security alerts.

Returns:
    Summary statistics for alerts in different time windows

**Responses:**

- `200`: Successful Response

---

### GET /api/security/storm-status

**Get Storm Status**

Get broadcast storm detection status.

Returns:
    Current storm detector status and statistics

**Responses:**

- `200`: Successful Response

---

### POST /api/security/acl/source

**Add Source To Acl**

Add or update a source in the Access Control List.

Args:
    entry: ACL entry configuration

Returns:
    Success message

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### DELETE /api/security/acl/source/{source_address}

**Remove Source From Acl**

Remove a source from the Access Control List.

Args:
    source_address: Source address to remove (decimal)

Returns:
    Success message

**Parameters:**

- `source_address` (path, required): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/security/acl/sources

**List Acl Sources**

List all sources in the Access Control List.

Returns:
    Dictionary of ACL entries by source address

**Responses:**

- `200`: Successful Response

---

### POST /api/security/acl/policy

**Set Acl Policy**

Set the default ACL policy.

Args:
    policy_request: Policy configuration ("allow" or "deny")

Returns:
    Success message

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/security/rate-limiting

**Get Rate Limiting Status**

Get rate limiting status and statistics.

Returns:
    Rate limiting configuration and current token bucket status

**Responses:**

- `200`: Successful Response

---

### POST /api/security/reset

**Reset Security Monitoring**

Reset all security monitoring data.

This clears all alerts, statistics, and tracking data.
Use with caution as this will lose all security history.

Returns:
    Confirmation message

**Responses:**

- `200`: Successful Response

---

### GET /api/security/test/simulate-attack

**Simulate Attack For Testing**

Simulate various types of attacks for testing (development/demo only).

Args:
    attack_type: Type of attack (flood, scan, storm)
    source_address: Source address to use for simulation
    duration: How long to run the simulation

Returns:
    Simulation results

**Parameters:**

- `attack_type` (query, required): Type of attack to simulate
- `source_address` (query, optional): Source address for simulation
- `duration` (query, optional): Duration in seconds

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

## security-configuration

### GET /api/security/config/

**Get Security Config**

Get complete security configuration (Admin only).

Returns the full security configuration including all policies
and current settings.

**Responses:**

- `200`: Successful Response

---

### PUT /api/security/config/

**Update Security Config**

Update complete security configuration (Admin only).

Replaces the entire security configuration with the provided data.
Use with caution as this affects all security policies.

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/security/config/summary

**Get Security Summary**

Get security configuration summary (Admin only).

Returns a condensed view of security settings and validation status.

**Responses:**

- `200`: Successful Response

---

### POST /api/security/config/mode

**Update Security Mode**

Update security mode (Admin only).

Changes the overall security mode which affects multiple policies.
Available modes: minimal, standard, strict, paranoid.

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/security/config/policies/{policy_type}

**Update Policy**

Update a specific security policy (Admin only).

Updates individual policies without affecting the entire configuration.
Supported policy types: pin, rate_limiting, authentication, audit, network.

**Parameters:**

- `policy_type` (path, required): No description

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/security/config/validate

**Validate Config**

Validate current security configuration (Admin only).

Checks the current configuration for issues and provides recommendations.

**Responses:**

- `200`: Successful Response

---

### POST /api/security/config/reload

**Reload Config**

Reload security configuration from disk (Admin only).

Forces a reload of the configuration file, useful after manual edits.

**Responses:**

- `200`: Successful Response

---

### GET /api/security/config/policies/pin

**Get Pin Policy**

Get PIN security policy configuration (Admin only).

**Responses:**

- `200`: Successful Response

---

### GET /api/security/config/policies/rate-limiting

**Get Rate Limiting Policy**

Get rate limiting policy configuration (Admin only).

**Responses:**

- `200`: Successful Response

---

### GET /api/security/config/policies/authentication

**Get Authentication Policy**

Get authentication policy configuration (Admin only).

**Responses:**

- `200`: Successful Response

---

### GET /api/security/config/caddy/rate-limits

**Get Caddy Rate Limits**

Get Caddy-compatible rate limit configuration (Admin only).

Returns the IP-based rate limits that should be configured in Caddy.
This is separate from the user-aware rate limits handled in FastAPI.

**Responses:**

- `200`: Successful Response

---

## security-dashboard

### GET /api/security/dashboard/data

**Get Dashboard Data**

Get complete security dashboard data.

Returns:
    Complete dashboard data including stats, events, and health

**Parameters:**

- `limit` (query, optional): Number of recent events to include

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/security/dashboard/stats

**Get Security Stats**

Get security statistics summary.

Returns:
    Security statistics and metrics

**Responses:**

- `200`: Successful Response

---

### GET /api/security/dashboard/events/recent

**Get Recent Events**

Get recent security events.

Args:
    limit: Maximum number of events to return
    severity: Optional severity filter

Returns:
    Recent security events with metadata

**Parameters:**

- `limit` (query, optional): Number of events to return
- `severity` (query, optional): Filter by severity

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/security/dashboard/health

**Get System Health**

Get comprehensive system health status.

Returns:
    System health information for all security components

**Responses:**

- `200`: Successful Response

---

### POST /api/security/dashboard/test/event

**Create Test Event**

Create a test security event for dashboard testing.

Args:
    event_type: Type of security event to create
    severity: Severity level (info, low, medium, high, critical)
    title: Event title

Returns:
    Information about the created test event

**Parameters:**

- `event_type` (query, optional): No description
- `severity` (query, optional): No description
- `title` (query, optional): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/security/dashboard/websocket/info

**Get Websocket Info**

Get WebSocket connection information.

Returns:
    Information about WebSocket connections and status

**Responses:**

- `200`: Successful Response

---

## startup_monitoring

### GET /api/startup/health

**Get startup health status**

Get overall startup health validation status and basic metrics.

**Responses:**

- `200`: Successful Response

---

### GET /api/startup/metrics

**Get startup performance metrics**

Get comprehensive startup performance metrics and analysis.

**Responses:**

- `200`: Successful Response

---

### GET /api/startup/services

**Get service startup timings**

Get detailed timing information for all services.

**Responses:**

- `200`: Successful Response

---

### GET /api/startup/report

**Get startup monitoring report**

Get the complete startup monitoring report if available.

**Responses:**

- `200`: Successful Response

---

### GET /api/startup/baseline-comparison

**Get performance baseline comparison**

Get comprehensive performance baseline comparison analysis.

**Responses:**

- `200`: Successful Response

---

## status

### GET /api/config/device_mapping

**Get device mapping configuration**

Returns the current device mapping configuration file content.

**Responses:**

- `200`: Successful Response

---

### GET /api/config/spec

**Get RV-C specification configuration**

Returns the current RV-C specification file content.

**Responses:**

- `200`: Successful Response

---

### GET /api/status/server

**Get server status**

Returns basic server status information including uptime and version.

**Responses:**

- `200`: Successful Response

---

### GET /api/status/application

**Get application status**

Returns application-specific status information including configuration and entity counts.

**Responses:**

- `200`: Successful Response

---

### GET /api/status/latest_release

**Get latest GitHub release**

Returns the latest GitHub release version and metadata.

**Responses:**

- `200`: Successful Response

---

### POST /api/status/force_update_check

**Force GitHub update check**

Forces an immediate GitHub update check and returns the new status.

**Responses:**

- `200`: Successful Response

---

### GET /api/status/features

**Get feature status**

Returns the current status of all services in the system.

**Responses:**

- `200`: Dictionary containing service states and metadata

---

### GET /api/config/settings

**Get Settings Overview**

Get current application settings with source information.

Returns configuration values showing which come from environment
variables vs defaults, without exposing sensitive information.

**Responses:**

- `200`: Successful Response

---

### GET /api/config/features

**Get Enhanced Feature Status**

Get current service status and availability.

**Responses:**

- `200`: Successful Response

---

### GET /api/config/can/interfaces

**Get Can Interface Mappings**

Get current CAN interface mappings.

**Responses:**

- `200`: Successful Response

---

### PUT /api/config/can/interfaces/{logical_name}

**Update Can Interface Mapping**

Update a CAN interface mapping (runtime only).

**Parameters:**

- `logical_name` (path, required): No description

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### POST /api/config/can/interfaces/validate

**Validate Interface Mappings**

Validate a set of interface mappings.

**Request Body:**

Content-Type: `application/json`

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/config/database

**Get Database Configuration**

Get current database configuration.

Returns database settings with sensitive information redacted.

**Responses:**

- `200`: Successful Response

---

### GET /api/config/coach/interface-requirements

**Get Coach Interface Requirements**

Get coach interface requirements and compatibility validation.

**Responses:**

- `200`: Successful Response

---

### GET /api/config/coach/metadata

**Get Coach Mapping Metadata**

Get complete coach mapping metadata including interface analysis.

**Responses:**

- `200`: Successful Response

---

## system-v2

### GET /api/v2/system/health

**Health Check**

Health check endpoint for system domain API

**Responses:**

- `200`: Successful Response

---

### GET /api/v2/system/schemas

**Get Schemas**

Export schemas for system domain

**Responses:**

- `200`: Successful Response

---

### GET /api/v2/system/info

**Get System Info**

Get system information

**Responses:**

- `200`: Successful Response

---

### GET /api/v2/system/status

**Get System Status**

Get overall system status with enhanced metadata

Supports multiple formats:
- default: Standard SystemStatus response
- ietf: IETF health+json compliant format

**Parameters:**

- `format` (query, optional): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

### GET /api/v2/system/services

**Get Services**

Get detailed service information

**Responses:**

- `200`: Successful Response

---

### GET /api/v2/system/components/health

**Get Component Health**

Get detailed health status for all system components

Returns health information for individual system components,
organized by category (core, network, storage, external).

**Responses:**

- `200`: Successful Response

---

### GET /api/v2/system/events

**Get Event Logs**

Get system event logs with filtering

Returns recent system events that can be filtered by:
- Log level (debug, info, warning, error, critical)
- Component name
- Time range

**Parameters:**

- `limit` (query, optional): No description
- `level` (query, optional): No description
- `component` (query, optional): No description
- `start_time` (query, optional): No description
- `end_time` (query, optional): No description

**Responses:**

- `200`: Successful Response
- `422`: Validation Error

---

## WebSocket API

CoachIQ provides real-time updates via WebSocket connection.

**Endpoint**: `ws://raspberrypi.local:8080/ws`

### Connection
```javascript
const ws = new WebSocket('ws://raspberrypi.local:8080/ws');
```

### Message Types

**Entity Updates**
```json
{
  "type": "entity_update",
  "data": {
    "id": "light_1",
    "state": true,
    "brightness": 75
  }
}
```

**Status Messages**
```json
{
  "type": "status",
  "message": "Connected to CAN bus"
}
```

### Client Commands

**Subscribe to Updates**
```json
{
  "type": "subscribe",
  "entities": ["light_1", "hvac_1"]
}
```

**Control Entity**
```json
{
  "type": "control",
  "entity_id": "light_1",
  "command": {
    "state": false
  }
}
```
