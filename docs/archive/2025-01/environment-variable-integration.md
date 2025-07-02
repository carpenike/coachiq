# Environment Variable Integration for NixOS Module

This document provides a summary of the enhancements made to the `rvc2api` NixOS module to comprehensively support all environment variables and configuration options.

## Added Configuration Options

The following configuration options have been added to the NixOS module:

### Server Configuration

- `host`: Host IP to bind the API server to (default: "0.0.0.0")
- `port`: Port to run the API server on (default: 8000)
- `logLevel`: Logging level (default: "INFO")

### Controller Configuration

- `controllerSourceAddr`: Controller source address in hex (default: "0xF9")

### GitHub Integration

- `githubUpdateRepo`: GitHub repository to check for updates (format: owner/repo)

### Previously Supported Options

- All Pushover notification settings
- UptimeRobot monitoring settings
- CANbus configuration (channels, bustype, bitrate)
- RV-C spec and device mapping paths and model selector
- User coach info path

## Environment Variable Mapping

All environment variables used by the application are now properly mapped in the NixOS module:

| NixOS Configuration             | Environment Variable           |
| ------------------------------- | ------------------------------ |
| `settings.host`                 | `RVC2API_HOST`                 |
| `settings.port`                 | `RVC2API_PORT`                 |
| `settings.logLevel`             | `LOG_LEVEL`                    |
| `settings.controllerSourceAddr` | `CONTROLLER_SOURCE_ADDR`       |
| `settings.githubUpdateRepo`     | `GITHUB_UPDATE_REPO`           |
| `settings.modelSelector`        | `RVC_COACH_MODEL`              |
| `settings.pushover.enable`      | `ENABLE_PUSHOVER`              |
| `settings.pushover.apiToken`    | `PUSHOVER_API_TOKEN`           |
| `settings.pushover.userKey`     | `PUSHOVER_USER_KEY`            |
| `settings.pushover.device`      | `PUSHOVER_DEVICE`              |
| `settings.pushover.priority`    | `PUSHOVER_PRIORITY`            |
| `settings.uptimerobot.enable`   | `ENABLE_UPTIMEROBOT`           |
| `settings.uptimerobot.apiKey`   | `UPTIMEROBOT_API_KEY`          |
| `settings.canbus.channels`      | `CAN_CHANNELS`                 |
| `settings.canbus.bustype`       | `CAN_BUSTYPE`                  |
| `settings.canbus.bitrate`       | `CAN_BITRATE`                  |
| `settings.rvcSpecPath`          | `RVC_SPEC_PATH`                |
| `settings.deviceMappingPath`    | `RVC_COACH_MAPPING_PATH`       |
| `settings.userCoachInfoPath`    | `RVC2API_USER_COACH_INFO_PATH` |

## Documentation Updates

- Created comprehensive documentation in `docs/nixos-module.md`
- Updated `docs/nixos-integration.md` with improved examples
- Included references to the NixOS module in the main `README.md`
- Created a unified `docs/development-environments.md` document explaining all setup options

## Next Steps

Now that the NixOS module has all the configuration options fully integrated:

1. Users can deploy the service with all necessary configuration options
2. Documentation provides clear examples for both basic and advanced configurations
3. All environment variables used by the application are properly mapped
4. Integration with both development and production environments is seamless

The improved module structure follows NixOS best practices and provides a clean, declarative way to configure the service.
