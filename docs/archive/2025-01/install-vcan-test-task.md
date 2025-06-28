# Installing the vCAN Test VS Code Task

You can add the vCAN testing task to your VS Code environment using one of these methods:

## Automated Installation

Run the provided script to automatically add the task to your tasks.json file:

```bash
# Bash
./scripts/add_vcan_test_task.sh

# Fish
./scripts/add_vcan_test_task.sh
```

This script will:

1. Backup your current tasks.json
2. Add the new task to the file
3. Notify you when complete

## Manual Installation

If you prefer to add the task manually:

1. Open the `.vscode/tasks.json` file in your project
2. Add the following task configuration to the "tasks" array (before the closing `]`):

```json
{
  "label": "System: Test vCAN Setup",
  "type": "shell",
  "command": "cd ${workspaceFolder} && poetry run python dev_tools/test_vcan_setup.py",
  "group": "none",
  "detail": "Test vCAN setup by sending and receiving a message",
  "presentation": {
    "reveal": "always",
    "panel": "dedicated",
    "clear": true,
    "focus": false
  }
}
```

3. Save the file

## Using the Task

Once installed, access the task by pressing `Cmd+Shift+P` (macOS) or `Ctrl+Shift+P` (Windows/Linux) and typing "Tasks: Run Task", then selecting "System: Test vCAN Setup".
