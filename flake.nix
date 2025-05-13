# flake.nix — Nix flake definition for rvc2api
#
# This flake provides:
#
# ▸ A Python-based CANbus FastAPI web service built with Poetry
# ▸ Unified versioning via the root-level `VERSION` file
# ▸ Reproducible developer environments with `devShells.default` and `devShells.ci`
# ▸ CLI apps (run with `nix run .#<name>`) for:
#    - `test`     → run unit tests
#    - `lint`     → run flake8, mypy, djlint
#    - `format`   → run black and djlint in reformat mode
#    - `ci`    → run full gate: pre-commit, tests, lints, poetry lock
#    - `precommit`→ run pre-commit checks across the repo
# ▸ Nix flake checks (via `nix flake check`) for:
#    - pytest suite
#    - style (flake8, mypy, djlint)
#    - lockfile validation (poetry check --lock --no-interaction)
# ▸ Package build output under `packages.<system>.rvc2api`
#
# Best Practices:
# - Canonical version is managed in `VERSION`
# - `pyproject.toml` is pinned to version "0.0.0"
# - Release automation is handled via `release-please`, which updates `VERSION` and `flake.nix`
# - Runtime version is available in the app via `core_daemon._version.VERSION`
#
# Usage (in this repo):
#   nix develop             # Enter the default dev environment
#   nix run .#test          # Run tests
#   nix run .#lint          # Run linter suite
#   nix flake check         # Run CI-grade validation
#   nix build .#rvc2api     # Build the package
#
# Usage (in a system flake or NixOS configuration):
#
#   # In your flake inputs:
#   inputs.rvc2api.url = "github:carpenike/rvc2api";
#
#   # In your systemPackages or services:
#   environment.systemPackages = [ inputs.rvc2api.packages.${system}.rvc2api ];
#
#   # Or to reference CLI apps:
#   nix run inputs.rvc2api#check

{
  description = "rvc2api Python package and devShells";

  inputs = {
    nixpkgs.url     = "github:NixOS/nixpkgs/nixpkgs-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        python = pkgs.python312;
        pythonPackages = pkgs.python312Packages;

        version = builtins.replaceStrings ["\n"] [""] (builtins.readFile ./VERSION);

        rvc2apiPackage = pythonPackages.buildPythonPackage {
          pname = "rvc2api";
          inherit version;
          src      = self;
          format   = "pyproject";

          nativeBuildInputs = with pythonPackages; [ poetry-core ];
          propagatedBuildInputs = [
            pythonPackages.fastapi
            pythonPackages.uvicorn  # Base uvicorn
            pythonPackages.websockets # Uvicorn standard extra
            pythonPackages.httptools  # Uvicorn standard extra
            pythonPackages.python-dotenv # Uvicorn standard extra
            pythonPackages.watchfiles # Uvicorn standard extra
            pythonPackages.httpx  # Added for uptimerobot feature
          ] ++ pkgs.lib.optionals (pkgs.stdenv.isLinux || pkgs.stdenv.isDarwin) [
            pythonPackages.uvloop   # Uvicorn standard extra (conditional)
          ] ++ [
            pythonPackages.python-can
            pythonPackages.pydantic
            pythonPackages.pyyaml
            pythonPackages.prometheus_client
            pythonPackages.coloredlogs
            pythonPackages.jinja2
          ] ++ pkgs.lib.optionals pkgs.stdenv.isLinux [
            pythonPackages.pyroute2
          ];

          doCheck    = true;
          checkInputs = [ pythonPackages.pytest ];

          meta = with pkgs.lib; {
            description = "CAN‑bus web service exposing RV‑C network data via HTTP & WebSocket";
            homepage    = "https://github.com/carpenike/rvc2api";
            license     = licenses.asl20;
            maintainers = [{
              name   = "Ryan Holt";
              email  = "ryan@ryanholt.net";
              github = "carpenike";
            }];
          };
        };

        devShell = pkgs.mkShell {
          buildInputs = [
            python
            pkgs.poetry
            pythonPackages.fastapi
            pythonPackages.uvicorn
            pythonPackages.websockets
            pythonPackages.httptools
            pythonPackages.python-dotenv
            pythonPackages.watchfiles
            pythonPackages."python-can"
            pythonPackages.pydantic
            pythonPackages.pyyaml
            pythonPackages.prometheus_client
            pythonPackages.coloredlogs
            pythonPackages.jinja2
            pythonPackages.pytest
            pythonPackages.mypy
            pythonPackages.flake8
            pythonPackages.types-pyyaml
            pkgs.fish
            pythonPackages.pytest-asyncio
          ] ++ pkgs.lib.optionals (pkgs.stdenv.isLinux || pkgs.stdenv.isDarwin) [
            pythonPackages.uvloop
          ] ++ pkgs.lib.optionals pkgs.stdenv.isLinux [
            pythonPackages.pyroute2
            pkgs.iproute2
          ];
          shellHook = ''
            export PYTHONPATH=$PWD/src:$PYTHONPATH
            echo "🐚 Entered rvc2api devShell on ${pkgs.system} with Python ${python.version}"
            echo "💡 Run 'poetry install' or 'nix build .#rvc2api' to get started."
          '';
        };

        ciShell = pkgs.mkShell {
          buildInputs = [
            python
            pkgs.poetry
            pythonPackages.pytest
            pythonPackages.pyyaml
            pythonPackages.uvicorn
            pythonPackages.websockets
            pythonPackages.httptools
            pythonPackages.python-dotenv
            pythonPackages.watchfiles
            pkgs.can-utils
            pythonPackages.pytest-asyncio
          ] ++ pkgs.lib.optionals (pkgs.stdenv.isLinux || pkgs.stdenv.isDarwin) [
            pythonPackages.uvloop
          ] ++ pkgs.lib.optionals pkgs.stdenv.isLinux [
            pythonPackages.pyroute2
            pkgs.iproute2
          ];
          shellHook = ''
            export PYTHONPATH=$PWD/src:$PYTHONPATH
            echo "🧪 Entered CI shell with vcan support"
            sudo modprobe vcan  || true
            sudo ip link add dev vcan0 type vcan  || true
            sudo ip link set up vcan0  || true
          '';
        };

        apps = {
          precommit = flake-utils.lib.mkApp {
            drv = pkgs.writeShellApplication {
              name          = "precommit";
              runtimeInputs = [ pkgs.poetry ];
              text = ''
                export SKIP=djlint
                poetry install --no-root
                poetry run pre-commit run --all-files
              '';
            };
          };

          test = flake-utils.lib.mkApp {
            drv = pkgs.writeShellApplication {
              name          = "test";
              runtimeInputs = [ pkgs.poetry ];
              text = ''
                poetry install --no-root
                poetry run pytest
              '';
            };
          };

          lint = flake-utils.lib.mkApp {
            drv = pkgs.writeShellApplication {
              name          = "lint";
              runtimeInputs = [ pkgs.poetry ];
              text = ''
                poetry install --no-root
                poetry run flake8
                poetry run mypy src
                poetry run djlint src/core_daemon/web_ui/templates --check
              '';
            };
          };

          format = flake-utils.lib.mkApp {
            drv = pkgs.writeShellApplication {
              name          = "format";
              runtimeInputs = [ pkgs.poetry ];
              text = ''
                poetry install --no-root
                poetry run black src
                poetry run djlint src/core_daemon/web_ui/templates --reformat
              '';
            };
          };

          # single “nix run .#ci entrypoint for CI
          ci = flake-utils.lib.mkApp {
            drv = pkgs.writeShellApplication {
              name          = "ci";
              runtimeInputs = [ pkgs.poetry ];
              text = ''
                export SKIP=djlint
                poetry install --no-root
                poetry check --lock --no-interaction
                poetry run pre-commit run --all-files --hook-stage commit
                poetry run djlint src/core_daemon/web_ui/templates --check
              '';
            };
          };
        };

        checks = {
          # only lock‑file validation in `nix flake check`
          poetry-lock-check = pkgs.runCommand "poetry-lock-check" {
            src         = ./.;
            buildInputs = [ pkgs.poetry ];
          } ''
            cd $src
            poetry check --lock --no-interaction
            touch $out
          '';
        };
      in {
        packages.rvc2api = rvc2apiPackage;
        defaultPackage   = self.packages.${system}.rvc2api;

        devShells = {
          default = devShell;
          ci      = ciShell;
        };

        inherit apps checks;
      }
    ) //
    {
    nixosModules.rvc2api = { config, lib, ... }: {
      options.rvc2api.settings = {
        pushover = {
          enable = lib.mkOption {
            type = lib.types.bool;
            default = false;
            description = "Enable Pushover integration";
          };
          apiToken = lib.mkOption {
            type = lib.types.str;
            default = "";
            description = "Pushover API token";
          };
          userKey = lib.mkOption {
            type = lib.types.str;
            default = "";
            description = "Pushover user key";
          };
          device = lib.mkOption {
            type = lib.types.nullOr lib.types.str;
            default = null;
            description = "Pushover device name (optional)";
          };
          priority = lib.mkOption {
            type = lib.types.nullOr lib.types.int;
            default = null;
            description = "Pushover message priority (optional)";
          };
        };
        uptimerobot = {
          enable = lib.mkOption {
            type = lib.types.bool;
            default = false;
            description = "Enable UptimeRobot integration";
          };
          apiKey = lib.mkOption {
            type = lib.types.str;
            default = "";
            description = "UptimeRobot API key";
          };
        };
        canbus = {
          channels = lib.mkOption {
            type = lib.types.listOf lib.types.str;
            default = [ "can0" ];
            description = ''
              SocketCAN interfaces to listen on (comma-separated for env).
              Default is [ "can0" ].
              To use multiple interfaces, set to e.g. [ "can0" "can1" ] in your configuration.
            '';
          };
          bustype = lib.mkOption {
            type = lib.types.str;
            default = "socketcan";
            description = "python-can bus type";
          };
          bitrate = lib.mkOption {
            type = lib.types.int;
            default = 500000;
            description = "CAN bus bitrate";
          };
        };
        rvcSpecPath = lib.mkOption {
          type = lib.types.nullOr lib.types.str;
          default = null;
          description = "Override path to rvc.json (RVC spec file)";
        };
        deviceMappingPath = lib.mkOption {
          type = lib.types.nullOr lib.types.str;
          default = null;
          description = "Override path to device_mapping.yml or a model-specific mapping file. If not set, uses modelSelector if provided.";
        };
        modelSelector = lib.mkOption {
          type = lib.types.nullOr lib.types.str;
          default = null;
          description = ''
            Model selector for device mapping file. Example: "2021_Entegra_Aspire_44R" will use
            "${config.rvc2api.package}/share/rvc2api/mappings/" + config.rvc2api.settings.modelSelector + ".yml" as the mapping file if deviceMappingPath is not set.
            If both are unset, falls back to device_mapping.yml.
          '';
        };
      };
      options.rvc2api.package = lib.mkOption {
        type = lib.types.package;
        # NOTE: No default is set here because pkgs is not available in the module context.
        # Consumers should set this to their rvc2api package, e.g. pkgs.rvc2api or inputs.rvc2api.packages.<system>.rvc2api
        description = ''
          The rvc2api package to run as a service.
          You must set this in your system configuration, e.g.:
            rvc2api.package = pkgs.rvc2api;
          or
            rvc2api.package = inputs.rvc2api.packages."aarch64-linux".rvc2api;
          (replace "aarch64-linux" with your system if different)
        '';
      };
      config = {
        systemd.services.rvc2api = {
          description = "RV-C HTTP/WebSocket API";
          after       = [ "network.target" ];
          wantedBy    = [ "multi-user.target" ];
          serviceConfig = {
            ExecStart = "${config.rvc2api.package}/bin/rvc2api-daemon";
            Restart    = "always";
            RestartSec = 5;
          };
          environment = {
            ENABLE_PUSHOVER = if config.rvc2api.settings.pushover.enable then "1" else "0";
            PUSHOVER_API_TOKEN = config.rvc2api.settings.pushover.apiToken;
            PUSHOVER_USER_KEY = config.rvc2api.settings.pushover.userKey;
            PUSHOVER_DEVICE = lib.mkIf (config.rvc2api.settings.pushover.device != null) config.rvc2api.settings.pushover.device;
            PUSHOVER_PRIORITY = lib.mkIf (config.rvc2api.settings.pushover.priority != null) (toString config.rvc2api.settings.pushover.priority);
            ENABLE_UPTIMEROBOT = if config.rvc2api.settings.uptimerobot.enable then "1" else "0";
            UPTIMEROBOT_API_KEY = config.rvc2api.settings.uptimerobot.apiKey;
            CAN_CHANNELS = lib.concatStringsSep "," config.rvc2api.settings.canbus.channels;
            CAN_BUSTYPE = config.rvc2api.settings.canbus.bustype;
            CAN_BITRATE = toString config.rvc2api.settings.canbus.bitrate;
            CAN_SPEC_PATH = lib.mkIf (config.rvc2api.settings.rvcSpecPath != null) config.rvc2api.settings.rvcSpecPath;
            CAN_MAP_PATH =
              if config.rvc2api.settings.deviceMappingPath != null then config.rvc2api.settings.deviceMappingPath
              else if config.rvc2api.settings.modelSelector != null then "${config.rvc2api.package}/lib/python3.12/site-packages/rvc_decoder/config/" + config.rvc2api.settings.modelSelector + ".yml"
              else "${config.rvc2api.package}/lib/python3.12/site-packages/rvc_decoder/config/device_mapping.yml";
          };
        };
      };
    };
  };
}
