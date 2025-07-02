# Nix in Devcontainer Performance Guide

This document explains how Nix is set up in the devcontainer and provides guidance on performance optimization.

## Overview of Nix Setup

The devcontainer is configured to use Nix in an optimized way:

1. **Named Volume for Nix Store**: Instead of a bind mount, the Nix store uses a Docker named volume (`rvc2api-nix-store`) for better performance and to avoid permission issues.

2. **Optimized Nix Configuration**: Custom configuration in `~/.config/nix/nix.conf` improves caching and performance.

3. **Error Handling**: Wrapper scripts automatically handle common Nix errors like "File exists" issues.

## Common Commands

### Using Nix

- **Enter Nix Shell**: `nix-develop` (aliased wrapper for error handling)
- **Standard Command**: `nix develop` (without error handling)

### Fixing Issues

If you encounter Nix-related issues:

1. **Manual Fix for "File exists" Error**:

   ```bash
   sudo /workspace/.devcontainer/scripts/fix-nix-errors.sh
   ```

2. **Reset Nix Configuration**:

   ```bash
   /workspace/.devcontainer/scripts/setup-nix-config.sh
   ```

3. **VS Code Task**: Use the "Dev: Enter Nix Shell" VS Code task, which uses the optimized wrapper

## Performance Tips

1. **Keep Nix Store Volume**: Don't delete the Docker volume named `rvc2api-nix-store` between container rebuilds to maintain your cache.

2. **Use Flakes**: Nix Flakes provide better caching and reproducibility.

3. **Consider GC**: Run `nix-collect-garbage` periodically to clean up unused storage.

## Troubleshooting

If you encounter slow performance or errors:

1. **Check Logs**: Review `/workspace/nix_develop.log` and `/workspace/nix_fix.log` for issues.

2. **Update Configuration**: Ensure `/workspace/.devcontainer/nix.conf` has appropriate settings.

3. **Restart Container**: Sometimes a container restart will resolve permission issues.
