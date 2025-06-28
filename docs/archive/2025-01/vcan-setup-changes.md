# vCAN Setup for DevContainer Changes

This document summarizes the changes made to improve vCAN setup in the CoachIQ DevContainer environment.

## Changes Made

1. **Enhanced Colima setup process:**

   - Integrated vcan setup into `.devcontainer/setup-colima.sh` for a streamlined experience
   - Created standalone scripts for flexibility and troubleshooting:
     - `scripts/setup_colima_vcan.sh`: Sets up vcan kernel modules, interfaces and systemd services in the Colima VM
     - `scripts/ensure_vcan_interfaces.sh`: Helper script to verify and create vcan interfaces inside the container
     - `.devcontainer/diagnose-vcan.sh`: Diagnostic script for vcan interface issues

2. **Updated DevContainer configuration:**

   - Added vcan interface setup to container startup script (`.devcontainer/startup.sh`)
   - Set proper file permissions in `devcontainer.json` for vcan scripts
   - Added vcan diagnostics to diagnose toolkit
   - Updated documentation references

3. **Added VS Code tasks for vCAN management:**

   - "System: Setup Colima vcan": Runs the standalone setup script on the host
   - "System: Ensure vcan Interfaces": Verifies interfaces in the container

4. **Updated documentation:**
   - Expanded `devcontainer-vcan-guide.md` with more detailed setup and troubleshooting steps
   - Updated `.devcontainer/README.md` to reference the new scripts

## How It Works

### Automated Setup

1. The user runs `.devcontainer/setup-colima.sh` on their macOS host to configure both Colima and vcan
2. When the devcontainer starts, `ensure_vcan_interfaces.sh` is automatically called by `startup.sh`
3. If any issues occur, the user can run `.devcontainer/diagnose-vcan.sh` to troubleshoot

### Manual Setup (if needed)

1. The user can also run `./scripts/setup_colima_vcan.sh` separately if just the vcan setup is needed
2. Inside the container, the "System: Ensure vcan Interfaces" task can be used to verify/repair the interfaces

### Testing vCAN

1. The user can verify vCAN functionality using the `dev_tools/test_vcan_setup.py` script
2. This script uses python-can to send and receive a test message on vcan0
3. A VS Code task "System: Test vCAN Setup" is available for easy testing

## Testing Procedure

To verify the changes:

1. Stop any running Colima instance: `colima stop`
2. Run `.devcontainer/setup-colima.sh` to configure Colima with vcan support
3. Open the folder in a DevContainer in VSCode
4. Check if vcan interfaces are available in the container: `ip link show vcan0`
5. If issues persist, run the "System: Ensure vcan Interfaces" task in VSCode

## Notes

- These scripts include comprehensive error handling and user feedback
- The setup is designed to be non-destructive, able to run multiple times without issues
- Can-utils is automatically installed for testing if missing
- A systemd service is created in the Colima VM to ensure vcan interfaces persist across VM restarts
