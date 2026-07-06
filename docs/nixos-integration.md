# Using CoachIQ in NixOS Configurations

This document explains how to include and configure CoachIQ in other NixOS systems and
flakes.

## Overview

CoachIQ is packaged as a Nix flake with:

- A Python package (`packages.<system>.coachiq`) and a prebuilt frontend
  (`packages.<system>.frontend`)
- A NixOS module (`nixosModules.default`) that runs CoachIQ as a hardened systemd
  service under `services.coachiq`
- An overlay (`overlays.default`) exposing `pkgs.coachiq`
- Development shells (`devShells.default`, `devShells.ci`)

The module follows a hybrid options pattern (see
[ADR-0009](adr/ADR-0009-nix-module-hybrid-options.md)): a small set of first-class
typed options for load-bearing deployment knobs, plus a freeform `settings` attrset
that passes `COACHIQ_*` environment variables straight through to the backend's
Pydantic settings.

## Basic Usage

### Including CoachIQ in Your Flake

Add CoachIQ to your flake inputs:

```nix
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-25.11";

    # Add CoachIQ as a dependency
    coachiq.url = "github:carpenike/coachiq";
    coachiq.inputs.nixpkgs.follows = "nixpkgs"; # Optional: use your nixpkgs
  };

  outputs = { self, nixpkgs, coachiq, ... }: {
    # Your outputs...
  };
}
```

### As a Package

To simply include CoachIQ as a package:

```nix
environment.systemPackages = [
  inputs.coachiq.packages.${system}.coachiq
];
```

### As a NixOS Module

For a complete integration with configuration options:

```nix
{
  imports = [
    inputs.coachiq.nixosModules.default
  ];

  services.coachiq = {
    enable = true;

    # First-class options (see docs/nixos-module.md for the full list)
    # host = "127.0.0.1";              # default
    # port = 8000;                     # default
    # dataDir = "/var/lib/coachiq";    # default
    # logLevel = "INFO";               # default
    # tlsTerminationIsExternal = true; # when behind a TLS-terminating proxy

    # Everything else goes through the freeform settings passthrough as
    # COACHIQ_* environment variables:
    settings = {
      COACHIQ_CAN__INTERFACES = "can0,can1";
      COACHIQ_CAN__INTERFACE_MAPPINGS = builtins.toJSON {
        house = "can0";
        chassis = "can1";
      };
    };

    # Secrets (JWT/session keys) belong in a root-readable environment file,
    # never in settings or the Nix store:
    # environmentFile = config.age.secrets.coachiq-env.path;
  };
}
```

For complete configuration options, see the
[NixOS Module Documentation](nixos-module.md).

## Development Usage

To develop against CoachIQ:

```bash
# Enter the development shell
nix develop github:carpenike/coachiq

# Or use the CI shell (includes vcan setup)
nix develop github:carpenike/coachiq#ci
```

The flake also exposes CLI apps runnable with `nix run`, e.g. `nix run .#test`,
`nix run .#lint`, `nix run .#format`, and `nix run .#ci`.

## Architecture Support

CoachIQ supports the following architectures:

- x86_64-linux
- aarch64-linux (Raspberry Pi 4/5, etc.)

## Version Management

The canonical version lives in the root-level `VERSION` file and is managed via
GitHub's release-please automation. You can pin to a specific tag or commit in your
flake for stability:

```nix
coachiq.url = "github:carpenike/coachiq/v1.0.0";
```
