# flake# ▸ CLI apps (run with `nix run .#<n>`) for:
#    - `test`     → run unit tests
#    - `lint`     → run ruff, pyright, djlint
#    - `format`   → run black and djlint in reformat mode — Nix flake definition for rvc2api
#
# This flake provides:
#
# ▸ A Python-based CANbus FastAPI web service built with Poetry
# ▸ Unified versioning via the root-level `VERSION` file
# ▸ Reproducible developer environments with `devShells.default` and `devShells.ci`
# ▸ CLI apps (run with `nix run .#<name>`) for:
#    - `test`     → run unit tests
#    - `lint`     → run ruff, mypy, djlint
#    - `format`   → run black and djlint in reformat mode
#    - `ci`       → run full gate: pre-commit, tests, lints, poetry lock
#    - `precommit`→ run pre-commit checks across the repo
# ▸ Nix flake checks (via `nix flake check`) for:
#    - pytest suite
#    - style (ruff, pyright, djlint)
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
#   # As a package:
#   environment.systemPackages = [ inputs.rvc2api.packages.${system}.rvc2api ];
#
#   # As a NixOS module:
#   imports = [ inputs.rvc2api.nixosModules.rvc2api ];
#   # Then configure it:
#   rvc2api.settings = { ... };
#
#   # Or to reference CLI apps:
#   nix run inputs.rvc2api#check
#
# See docs/nixos-integration.md for more details

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
            # --- Backend dependencies ---
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
            pythonPackages.ruff
            pythonPackages.types-pyyaml
            pkgs.fish
            pythonPackages.pytest-asyncio

            # --- Frontend dependencies ---
            # Only include Node.js runtime, npm will manage package dependencies
            pkgs.nodejs_20

            # --- Development tools ---
            pkgs.pyright  # For Python type checking
          ] ++ pkgs.lib.optionals (pkgs.stdenv.isLinux || pkgs.stdenv.isDarwin) [
            pythonPackages.uvloop
          ] ++ pkgs.lib.optionals pkgs.stdenv.isLinux [
            pythonPackages.pyroute2
            pkgs.iproute2
          ];
          shellHook = ''
            export PYTHONPATH=$PWD/src:$PYTHONPATH
            # Set up Node.js environment
            export NODE_PATH=$PWD/web_ui/node_modules

            echo "🐚 Entered rvc2api devShell on ${pkgs.system} with Python ${python.version} and Node.js $(node --version)"
            echo "💡 Backend commands:"
            echo "  • poetry install              # Install Python dependencies"
            echo "  • poetry run python src/core_daemon/main.py  # Run API server"
            echo ""
            echo "💡 Frontend commands:"
            echo "  • cd web_ui && npm install    # Install frontend dependencies"
            echo "  • cd web_ui && npm run dev    # Start React dev server"
            echo "  • cd web_ui && npm run build  # Build production frontend"

            # Setup frontend if web_ui directory exists
            if [ -d "web_ui" ] && [ ! -d "web_ui/node_modules" ]; then
              echo "🔧 Setting up frontend development environment..."
              (cd web_ui && npm install)
              echo "✅ Frontend dependencies installed"
            fi
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
            pythonPackages.pytest-asyncio
            pkgs.pyright  # For Python type checking
          ] ++ pkgs.lib.optionals (pkgs.stdenv.isLinux || pkgs.stdenv.isDarwin) [
            pythonPackages.uvloop
          ] ++ pkgs.lib.optionals pkgs.stdenv.isLinux [
            pkgs.can-utils
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
                # Backend linting
                poetry install --no-root
                poetry run ruff check .
                npx pyright src

                # Frontend linting (if web_ui directory exists)
                if [ -d "web_ui" ]; then
                  cd web_ui
                  npm run lint
                  npm run typecheck
                fi
              '';
            };
          };

          format = flake-utils.lib.mkApp {
            drv = pkgs.writeShellApplication {
              name          = "format";
              runtimeInputs = [ pkgs.poetry ];
              text = ''
                # Backend formatting
                poetry install --no-root
                poetry run black src

                # Frontend formatting (if web_ui directory exists)
                if [ -d "web_ui" ]; then
                  cd web_ui
                  npm run lint -- --fix
                fi
              '';
            };
          };

          build-frontend = flake-utils.lib.mkApp {
            drv = pkgs.writeShellApplication {
              name          = "build-frontend";
              runtimeInputs = [ pkgs.nodejs_20 ];
              text = ''
                if [ ! -d "web_ui" ]; then
                  echo "Error: web_ui directory not found"
                  exit 1
                fi

                cd web_ui
                echo "📦 Installing frontend dependencies..."
                npm ci
                echo "🏗️ Building frontend..."
                npm run build

                echo "✅ Frontend built successfully to web_ui/dist/"
                echo "To deploy, copy the dist directory to your webserver"
              '';
            };
          };

          # single "nix run .#ci entrypoint for CI
          ci = flake-utils.lib.mkApp {
            drv = pkgs.writeShellApplication {
              name          = "ci";
              runtimeInputs = [ pkgs.poetry ];
              text = ''
                export SKIP=djlint
                poetry install --no-root
                poetry check --lock --no-interaction
                poetry run pre-commit run --all-files --hook-stage commit
                poetry run ruff check .
                npx pyright src
                poetry run djlint src/core_daemon/web_ui/templates --check

                # Frontend checks
                if [ -d "web_ui" ]; then
                  echo "🔍 Running frontend checks..."
                  cd web_ui
                  npm ci
                  echo "🧪 Running lint checks..."
                  npm run lint
                  echo "🏗️ Testing build process..."
                  npm run build
                  echo "✅ Frontend checks passed"
                fi
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
      nixosModules.rvc2api = { config, lib, pkgs, ... }: {
        options.rvc2api = {
          enable = lib.mkEnableOption "Enable rvc2api RV-C network server";

          package = lib.mkOption {
            type = lib.types.package;
            default = self.packages.${pkgs.system}.rvc2api;
            description = "The rvc2api package to use";
          };

          settings = {
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

            # Add any other configuration options from config.py
            userCoachInfoPath = lib.mkOption {
              type = lib.types.nullOr lib.types.str;
              default = null;
              description = "Path to user coach info YAML file";
            };

            # Server configuration
            host = lib.mkOption {
              type = lib.types.str;
              default = "0.0.0.0";
              description = "Host IP to bind the API server to";
            };

            port = lib.mkOption {
              type = lib.types.int;
              default = 8000;
              description = "Port to run the API server on";
            };

            logLevel = lib.mkOption {
              type = lib.types.str;
              default = "INFO";
              description = "Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)";
            };

            # Controller configuration
            controllerSourceAddr = lib.mkOption {
              type = lib.types.str;
              default = "0xF9";
              description = "Controller source address in hex (default: 0xF9)";
            };

            # GitHub update checker
            githubUpdateRepo = lib.mkOption {
              type = lib.types.nullOr lib.types.str;
              default = null;
              description = "GitHub repository to check for updates (format: owner/repo)";
            };
          };
        };

        config = lib.mkIf config.rvc2api.enable {
          # Include the package in systemPackages
          environment.systemPackages = [ config.rvc2api.package ];

          # Set up the systemd service
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
              # Pushover settings
              ENABLE_PUSHOVER = if config.rvc2api.settings.pushover.enable then "1" else "0";
              PUSHOVER_API_TOKEN = config.rvc2api.settings.pushover.apiToken;
              PUSHOVER_USER_KEY = config.rvc2api.settings.pushover.userKey;
              PUSHOVER_DEVICE = lib.mkIf (config.rvc2api.settings.pushover.device != null)
                config.rvc2api.settings.pushover.device;
              PUSHOVER_PRIORITY = lib.mkIf (config.rvc2api.settings.pushover.priority != null)
                (toString config.rvc2api.settings.pushover.priority);

              # UptimeRobot settings
              ENABLE_UPTIMEROBOT = if config.rvc2api.settings.uptimerobot.enable then "1" else "0";
              UPTIMEROBOT_API_KEY = config.rvc2api.settings.uptimerobot.apiKey;

              # CANbus settings
              CAN_CHANNELS = lib.concatStringsSep "," config.rvc2api.settings.canbus.channels;
              CAN_BUSTYPE = config.rvc2api.settings.canbus.bustype;
              CAN_BITRATE = toString config.rvc2api.settings.canbus.bitrate;

              # Server settings
              RVC2API_HOST = config.rvc2api.settings.host;
              RVC2API_PORT = toString config.rvc2api.settings.port;
              LOG_LEVEL = config.rvc2api.settings.logLevel;

              # Controller settings
              CONTROLLER_SOURCE_ADDR = config.rvc2api.settings.controllerSourceAddr;

              # GitHub update checker
              GITHUB_UPDATE_REPO = lib.mkIf (config.rvc2api.settings.githubUpdateRepo != null)
                config.rvc2api.settings.githubUpdateRepo;

              # Model selector (used by rvc_decoder if CAN_MAP_PATH isn't set)
              CAN_MODEL_SELECTOR = lib.mkIf (config.rvc2api.settings.modelSelector != null)
                config.rvc2api.settings.modelSelector;

              # RVC spec and device mapping paths
              CAN_SPEC_PATH = lib.mkIf (config.rvc2api.settings.rvcSpecPath != null)
                config.rvc2api.settings.rvcSpecPath;

              # Device mapping path - complex logic to select the right path
              CAN_MAP_PATH =
                if config.rvc2api.settings.deviceMappingPath != null then
                  config.rvc2api.settings.deviceMappingPath
                else if config.rvc2api.settings.modelSelector != null then
                  "${config.rvc2api.package}/lib/python3.12/site-packages/rvc_decoder/config/" +
                  config.rvc2api.settings.modelSelector + ".yml"
                else
                  "${config.rvc2api.package}/lib/python3.12/site-packages/rvc_decoder/config/device_mapping.yml";

              # User coach info path
              RVC2API_USER_COACH_INFO_PATH = lib.mkIf (config.rvc2api.settings.userCoachInfoPath != null)
                config.rvc2api.settings.userCoachInfoPath;
            };
          };
        };
      };
    };
}
