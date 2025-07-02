# Poetry2nix Integration for rvc2api

This document provides recommendations for integrating poetry2nix with your existing flake.nix configuration to improve dependency management between Poetry and Nix.

## Overview

[poetry2nix](https://github.com/nix-community/poetry2nix) is a tool that allows for automatically converting Poetry projects to Nix derivations. It reads your `pyproject.toml` and `poetry.lock` files to create reproducible Nix builds.

## Benefits of Integration

1. **Single Source of Truth**: Manage all dependencies in `pyproject.toml` without duplicating them in Nix
2. **Better Reproducibility**: Ensure Nix builds use exactly the same dependency versions as Poetry
3. **Simplified Maintenance**: Update dependencies with Poetry and have Nix automatically respect those changes
4. **Improved Dev Experience**: Better integration between dev environments and production builds

## Implementation Plan

### 1. Update flake.nix Inputs

```nix
inputs = {
  nixpkgs.url     = "github:NixOS/nixpkgs/nixpkgs-unstable";
  flake-utils.url = "github:numtide/flake-utils";
  poetry2nix.url = "github:nix-community/poetry2nix";  # Add this line
};
```

### 2. Update the Outputs Section

```nix
outputs = { self, nixpkgs, flake-utils, poetry2nix, ... }:
  flake-utils.lib.eachDefaultSystem (system:
    let
      pkgs = import nixpkgs {
        inherit system;
        overlays = [ poetry2nix.overlay ];  # Add this line
      };
      python = pkgs.python312;

      # Read version from file
      version = builtins.replaceStrings ["\n"] [""] (builtins.readFile ./VERSION);

      # Define poetry2nix application
      rvc2apiPackage = pkgs.poetry2nix.mkPoetryApplication {
        projectDir = self;
        inherit version;

        # Optional but often helpful overrides
        overrides = pkgs.poetry2nix.overrides.withDefaults (final: prev: {
          # Add overrides for any packages that need special handling
          # For example:
          # python-can = prev.python-can.overridePythonAttrs (old: {
          #   buildInputs = (old.buildInputs or []) ++ [ final.setuptools ];
          # });
        });

        # For Linux-specific dependencies
        checkInputs = with pkgs.python312Packages; [ pytest ];
      };

      # For development environment
      devEnv = pkgs.poetry2nix.mkPoetryEnv {
        projectDir = self;
        preferWheels = true;
        python = python;

        # Same overrides as for the package
        overrides = pkgs.poetry2nix.overrides.withDefaults (final: prev: {
          # Same overrides as above
        });

        # For extra development tools not in pyproject.toml
        extraPackages = ps: with ps; [
          ruff
          ruff
          # Using Pyright as the standardized type checker (see pyrightconfig.json)
          pytest
        ];
      };
    in {
      # Keep existing outputs but replace rvc2apiPackage
      packages.default = rvc2apiPackage;
      packages.rvc2api = rvc2apiPackage;

      # Update or add the development shell
      devShells.default = pkgs.mkShell {
        buildInputs = [
          devEnv
          pkgs.poetry
          # Add any other tools needed for development
          pkgs.nodejs_20  # For frontend development
          pkgs.nodePackages.npm
        ];

        shellHook = ''
          # Any commands to run when entering the shell
          echo "rvc2api development environment activated"
          # Configure the project version if needed
          export RVC2API_VERSION="${version}"
        '';
      };

      # Keep other outputs (checks, apps, etc.)
      ...
    }
  );
```

### 3. Testing the Integration

After implementing these changes:

1. Run `nix flake check` to validate the flake
2. Run `nix develop` to test the development environment
3. Run `nix build` to test package building

### 4. Common Issues and Solutions

1. **Native Dependencies**: If packages have native dependencies, use `overrides` to add them
2. **Special Python Packages**: Some packages need special handling (e.g., pytest plugins)
3. **Platform-Specific Dependencies**: Handle with conditionals as already done in your flake

## VS Code Integration

With the [tasks.json](../.vscode/tasks.json) file now available, you can:

1. Press `Ctrl+Shift+P` and select "Tasks: Run Task"
2. Choose "Enter Nix Development Shell" to activate the environment
3. Use other tasks for common development workflows

## Next Steps

1. Gradually refine the poetry2nix overrides as needed
2. Consider moving more development tools into the devEnv
3. Set up CI to test both Poetry and Nix builds

## Resources

- [poetry2nix Documentation](https://github.com/nix-community/poetry2nix)
- [poetry2nix Project Templates](https://github.com/nix-community/poetry2nix/tree/master/templates)
- [Blog: Nix Packaging for Python Projects](https://blog.aicampground.com/p/nix-packaging-python-containers/)
