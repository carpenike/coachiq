# flake# ▸ CLI apps (run with `nix run .#<n>`) for:
#    - `test`     → run unit tests
#    - `lint`     → run ruff, pyright, djlint
#    - `format`   → run ruff format and djlint in reformat mode — Nix flake definition for CoachIQ
#
# This flake provides:
#
# ▸ A Python-based CANbus FastAPI web service built with Poetry
# ▸ Multi-protocol support: RV-C, J1939, Firefly, Spartan K2
# ▸ Advanced diagnostics with predictive maintenance and fault correlation
# ▸ Performance analytics with telemetry collection and optimization
# ▸ Unified versioning via the root-level `VERSION` file
# ▸ Reproducible developer environments with `devShells.default` and `devShells.ci`
# ▸ CLI apps (run with `nix run .#<name>`) for:
#    - `test`     → run unit tests
#    - `lint`     → run ruff, mypy, djlint
#    - `format`   → run ruff format and djlint in reformat mode
#    - `ci`       → run full gate: pre-commit, tests, lints, poetry lock
#    - `precommit`→ run pre-commit checks across the repo
# ▸ Nix flake checks (via `nix flake check`) for:
#    - pytest suite
#    - style (ruff, pyright, djlint)
#    - lockfile validation (poetry check --lock --no-interaction)
# ▸ Package build output under `packages.<system>.coachiq`
#
# Best Practices:
# - Canonical version is managed in `VERSION` file
# - `pyproject.toml` is synchronized with the VERSION file during builds
# - Release automation is handled via `release-please`, which updates `VERSION` and `flake.nix`
# - Runtime version is available in the app via `core_daemon._version.VERSION`
#
# Usage (in this repo):
#   nix develop             # Enter the default dev environment
#   nix run .#test          # Run tests
#   nix run .#lint          # Run linter suite
#   nix flake check         # Run CI-grade validation
#   nix build .#coachiq     # Build the package
#
# Usage (in a system flake or NixOS configuration):
#
#   # In your flake inputs:
#   inputs.coachiq.url = "github:carpenike/coachiq";
#
#   # As a package:
#   environment.systemPackages = [ inputs.coachiq.packages.${system}.coachiq ];
#
#   # As a NixOS module:
#   imports = [ inputs.coachiq.nixosModules.coachiq ];
#   # Then configure it:
#   coachiq.settings = { ... };
#
#   # Or to reference CLI apps:
#   nix run inputs.coachiq#check
#
# See docs/nixos-integration.md for more details

{
  description = "CoachIQ Python package and devShells";

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

        # Create Python environment with all dependencies for scripts
        pythonWithDeps = python.withPackages (ps: [
          ps.coloredlogs
          ps.fastapi
          ps.httptools
          ps.httpx
          ps.langchain-community
          ps.langchain-core
          ps.prometheus_client
          ps.psutil
          ps.pydantic
          ps.pyroute2
          ps.python-can
          ps.python-dotenv
          ps.pyyaml
          ps.uvicorn
          ps.watchfiles
          ps.websockets
          ps.sqlalchemy
          ps.aiosqlite
          ps.asyncpg
          ps.alembic
          ps.jinja2
          ps.pyjwt
          ps.passlib
          ps.python-multipart
          ps.email-validator
          ps.pyotp
          ps.qrcode
          ps.slowapi
          ps.cachetools
          ps.numpy
          ps.scipy
          ps.scikit-learn
          ps.pandas
          ps.cryptography
          ps.networkx
        ] ++ pkgs.lib.optionals (pkgs.stdenv.isLinux || pkgs.stdenv.isDarwin) [
          ps.uvloop
        ] ++ pkgs.lib.optionals pkgs.stdenv.isLinux [
          ps.apprise
        ]);

        # Read version from VERSION file (source of truth)
        version = builtins.replaceStrings ["\n"] [""] (builtins.readFile ./VERSION);

        coachiqPackage = pythonPackages.buildPythonPackage {
          pname = "coachiq";
          inherit version;
          src      = self;
          format   = "pyproject";

          nativeBuildInputs = with pythonPackages; [ poetry-core ] ++ [ pkgs.makeWrapper ];
          propagatedBuildInputs = [
            pythonPackages.coloredlogs
            pythonPackages.fastapi
            pythonPackages.httptools
            pythonPackages.httpx
            pythonPackages.langchain-community
            pythonPackages.langchain-core
            pythonPackages.prometheus_client
            pythonPackages.psutil
            pythonPackages.pydantic
            pythonPackages.pyroute2
            pythonPackages.python-can
            pythonPackages.python-dotenv
            pythonPackages.pyyaml
            pythonPackages.uvicorn
            pythonPackages.watchfiles
            pythonPackages.websockets
            # Database dependencies
            pythonPackages.sqlalchemy
            pythonPackages.aiosqlite
            pythonPackages.aiofiles
            pythonPackages.asyncpg
            pythonPackages.alembic
            # Notification system dependencies
            pythonPackages.jinja2
            # Authentication system dependencies
            pythonPackages.pyjwt
            pythonPackages.passlib
            pythonPackages.python-multipart
            pythonPackages.email-validator
            # MFA and rate limiting dependencies
            pythonPackages.pyotp
            pythonPackages.qrcode
            pythonPackages.slowapi
            pythonPackages.cachetools
            # Advanced analytics and diagnostics dependencies
            pythonPackages.numpy
            pythonPackages.scipy
            pythonPackages.scikit-learn
            pythonPackages.pandas
            # Security and protocol dependencies
            pythonPackages.cryptography
            # Network analysis for fault isolation
            pythonPackages.networkx
          ] ++ pkgs.lib.optionals (pkgs.stdenv.isLinux || pkgs.stdenv.isDarwin) [
            pythonPackages.uvloop   # Uvicorn standard extra (conditional)
          ] ++ pkgs.lib.optionals pkgs.stdenv.isLinux [
            pythonPackages.pyroute2
            # Notification system dependencies (Linux only due to platform constraints)
            pythonPackages.apprise
            # CAN protocol handling (Linux only due to platform constraints)
            pythonPackages.cantools
            # pkgs.can-utils removed - will be added to PATH via makeWrapper
          ];

          doCheck    = true;
          checkInputs = [ pythonPackages.pytest ];

          # Install configuration files to the package site-packages directory
          # This allows the NixOS module to reference them at the expected path
          postInstall = ''
            # Install reference data to package directory
            mkdir -p $out/${python.sitePackages}/config
            cp -r $src/config/* $out/${python.sitePackages}/config/

            # Also install to a predictable location for NixOS module
            mkdir -p $out/share/coachiq/config
            cp -r $src/config/* $out/share/coachiq/config/

            # Console scripts are automatically created by buildPythonPackage
            # from [tool.poetry.scripts] in pyproject.toml:
            # - coachiq-daemon (from backend.cli:main)
            # - coachiq-validate-config (from backend.core.config:validate_config_cli)

            # Health check script with Nix-compatible shebang
            mkdir -p $out/share/coachiq/nix
            cp ${./nix/health-check.sh} $out/share/coachiq/nix/health-check.sh
            # Replace the shebang to use Nix-provided bash and add curl to PATH
            sed -i '1s|#!/usr/bin/env bash|#!${pkgs.bash}/bin/bash|' $out/share/coachiq/nix/health-check.sh
            sed -i '2i\\nexport PATH="${pkgs.curl}/bin:$PATH"' $out/share/coachiq/nix/health-check.sh
            chmod +x $out/share/coachiq/nix/health-check.sh
          '';

          meta = with pkgs.lib; {
            description = "Multi-protocol CAN-bus web service with RV-C, J1939, advanced diagnostics, and performance analytics";
            homepage    = "https://github.com/carpenike/coachiq";
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
            pythonPackages.python-can
            pythonPackages.pydantic
            pythonPackages.pyyaml
            pythonPackages.prometheus_client
            pythonPackages.coloredlogs
            pythonPackages.jinja2
            pythonPackages.pyjwt
            pythonPackages.passlib
            pythonPackages.python-multipart
            pythonPackages.email-validator
            # MFA and rate limiting dependencies
            pythonPackages.pyotp
            pythonPackages.qrcode
            pythonPackages.slowapi
            pythonPackages.cachetools
            # Database dependencies for dev
            pythonPackages.sqlalchemy
            pythonPackages.aiosqlite
            pythonPackages.asyncpg
            pythonPackages.alembic
            pythonPackages.pytest
            pythonPackages.mypy
            pythonPackages.ruff
            pythonPackages.types-pyyaml
            pkgs.fish
            pythonPackages.pytest-asyncio

            # --- Dev Tools dependencies ---
            pythonPackages.langchain
            pythonPackages."langchain-openai"
            pythonPackages.pymupdf  # PyMuPDF, imported as fitz
            pythonPackages."faiss"

            # --- Advanced analytics and diagnostics dependencies ---
            pythonPackages.numpy
            pythonPackages.scipy
            pythonPackages.scikit-learn
            pythonPackages.pandas
            # Security and protocol dependencies
            pythonPackages.cryptography
            # Network analysis for fault isolation
            pythonPackages.networkx

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
            pkgs.stdenv.cc.cc.lib
            pkgs.zlib
            # Notification system dependencies (Linux only due to platform constraints)
            pythonPackages.apprise
            # CAN protocol handling (Linux only due to platform constraints)
            pythonPackages.cantools
            # CAN system utilities for debugging and management
            pkgs.can-utils
          ];
          shellHook = ''
            export PYTHONPATH=$PWD:$PYTHONPATH
            # Helper: run poetry with Nix's libstdc++ only for Python invocations
            poetry() {
              LD_LIBRARY_PATH=${pkgs.zlib}/lib:${pkgs.stdenv.cc.cc.lib}/lib''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH} command poetry "$@"
            }
            export -f poetry
            # Set prompt reliably in bash (including VS Code) and zsh
            if [ -n "$BASH_VERSION" ]; then
              export OLD_PS1="$PS1"
              export PS1="\[\033[1;32m\](nix develop)\[\033[0m\] $OLD_PS1"
            elif [ -n "$ZSH_VERSION" ]; then
              export PS1="%F{green}(nix develop)%f $PS1"
            fi
            if [ -n "$FISH_VERSION" ] || [ -x "$(command -v fish)" ]; then
              mkdir -p "$HOME/.config/fish/conf.d"
              cat > "$HOME/.config/fish/conf.d/nix_devshell_prompt.fish" <<'EOF'
function fish_prompt
  set_color green
  echo -n "(nix develop) "
  set_color normal
  echo -n (prompt_pwd) " > "
end
EOF
              if [ -n "$FISH_VERSION" ]; then
                source "$HOME/.config/fish/conf.d/nix_devshell_prompt.fish"
              fi
            fi
            # Set up Node.js environment
            export NODE_PATH=$PWD/frontend/node_modules

            echo "🐚 Entered CoachIQ devShell on ${pkgs.system} with Python ${python.version} and Node.js $(node --version)"
            echo "🚗 Multi-protocol CAN support: RV-C, J1939, Firefly, Spartan K2"
            echo "🔧 Advanced diagnostics with predictive maintenance and performance analytics"
            echo "💡 Backend commands:"
            echo "  • poetry install              # Install Python dependencies (now always uses correct LD_LIBRARY_PATH)"
            echo "  • poetry run python run_server.py  # Run API server"
            echo "  • poetry run pytest           # Run tests"
            echo "  • poetry run ruff check .     # Lint"
            echo "  • poetry run ruff format backend  # Format"
            echo "  • poetry run pyright backend  # Type checking"
            echo ""
            echo "💡 Frontend commands:"
            echo "  • cd frontend && npm install    # Install frontend dependencies"
            echo "  • cd frontend && npm run dev    # Start React dev server"
            echo "  • cd frontend && npm run build  # Build production frontend"
            echo ""
            echo "💡 Dev Tools commands:"
            echo "  • poetry install --with devtools  # Install dev tools dependencies"
            echo "  • python dev_tools/generate_embeddings.py  # Process RV-C spec PDF"
            echo "  • python dev_tools/query_faiss.py \"query\"  # Search RV-C spec"

            # Setup frontend if frontend directory exists
            if [ -d "frontend" ] && [ ! -d "frontend/node_modules" ]; then
              echo "🔧 Setting up frontend development environment..."
              (cd frontend && npm install)
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
            pythonPackages.pyjwt
            pythonPackages.passlib
            pythonPackages.python-multipart
            pythonPackages.email-validator
            pythonPackages.pytest-asyncio
            pkgs.pyright

            # --- Dev Tools dependencies for CI ---
            pythonPackages.langchain
            pythonPackages."langchain-openai"
            pythonPackages.pymupdf  # PyMuPDF, imported as fitz
            pythonPackages."faiss"
            # --- Advanced analytics and diagnostics dependencies ---
            pythonPackages.numpy
            pythonPackages.scipy
            pythonPackages.scikit-learn
            pythonPackages.pandas
            pythonPackages.cryptography
            pythonPackages.networkx
            pkgs.nodejs_20
          ] ++ pkgs.lib.optionals (pkgs.stdenv.isLinux || pkgs.stdenv.isDarwin) [
            pythonPackages.uvloop
          ] ++ pkgs.lib.optionals pkgs.stdenv.isLinux [
            pkgs.can-utils
            pythonPackages.pyroute2
            pkgs.iproute2
            # Notification system dependencies (Linux only due to platform constraints)
            pythonPackages.apprise
            # CAN protocol handling (Linux only due to platform constraints)
            pythonPackages.cantools
          ];
          shellHook = ''
            export PYTHONPATH=$PWD:$PYTHONPATH
            echo "🧪 Entered CI shell with vcan support"
            sudo modprobe vcan  || true
            sudo ip link add dev vcan0 type vcan  || true
            sudo ip link set up vcan0  || true
          '';
        };

        apps = {
          precommit = (flake-utils.lib.mkApp {
            drv = pkgs.writeShellApplication {
              name = "precommit";
              runtimeInputs = [ pkgs.poetry ];
              text = ''
                export SKIP=djlint
                poetry install --no-root --with dev
                poetry run pre-commit run --all-files
              '';
            };
          }) // {
            meta = {
              description = "Run pre-commit checks across the repo";
              maintainers = [ "carpenike" ];
              license = pkgs.lib.licenses.asl20;
            };
          };

          test = (flake-utils.lib.mkApp {
            drv = pkgs.writeShellApplication {
              name = "test";
              runtimeInputs = [ pkgs.poetry ];
              text = ''
                poetry install --no-root
                poetry run pytest
              '';
            };
          }) // {
            meta = {
              description = "Run unit tests";
              maintainers = [ "carpenike" ];
              license = pkgs.lib.licenses.asl20;
            };
          };

          lint = (flake-utils.lib.mkApp {
            drv = pkgs.writeShellApplication {
              name = "lint";
              runtimeInputs = [ pkgs.poetry ];
              text = ''
                # Backend linting
                poetry install --no-root
                poetry run ruff check .
                poetry run pyright backend

                # Frontend linting (if frontend directory exists)
                if [ -d "frontend" ]; then
                  cd frontend
                  npm run lint
                  npm run typecheck
                fi
              '';
            };
          }) // {
            meta = {
              description = "Run Python and frontend linters";
              maintainers = [ "carpenike" ];
              license = pkgs.lib.licenses.asl20;
            };
          };

          format = (flake-utils.lib.mkApp {
            drv = pkgs.writeShellApplication {
              name = "format";
              runtimeInputs = [ pkgs.poetry ];
              text = ''
                # Backend formatting
                poetry install --no-root
                poetry run ruff format backend

                # Frontend formatting (if frontend directory exists)
                if [ -d "frontend" ];then
                  cd frontend
                  npm run lint -- --fix
                fi
              '';
            };
          }) // {
            meta = {
              description = "Format Python and frontend code";
              maintainers = [ "carpenike" ];
              license = pkgs.lib.licenses.asl20;
            };
          };

          build-frontend = (flake-utils.lib.mkApp {
            drv = pkgs.writeShellApplication {
              name = "build-frontend";
              runtimeInputs = [ pkgs.nodejs_20 ];
              text = ''
                if [ ! -d "frontend" ]; then
                  echo "Error: frontend directory not found"
                  exit 1
                fi

                cd frontend
                echo "📦 Installing frontend dependencies..."
                npm ci
                echo "🏗️ Building frontend..."
                npm run build

                echo "✅ Frontend built successfully to frontend/dist/"
                echo "To deploy, copy the dist directory to your webserver"
              '';
            };
          }) // {
            meta = {
              description = "Build the frontend (React) application";
              maintainers = [ "carpenike" ];
              license = pkgs.lib.licenses.asl20;
            };
          };

          ci = (flake-utils.lib.mkApp {
            drv = pkgs.writeShellApplication {
              name = "ci";
              runtimeInputs = [ pkgs.poetry pkgs.nodejs_20 ];
              text = ''
                set -e
                export SKIP=djlint
                poetry install --no-root --with dev
                poetry check --lock --no-interaction

                # Frontend deps must be installed before pre-commit
                if [ -d "frontend" ]; then
                  echo "🔍 Installing frontend dependencies..."
                  cd frontend
                  npm ci
                  cd ..
                fi

                poetry run pre-commit run --all-files

                # Frontend checks
                # if [ -d "frontend" ]; then
                #   echo "🔍 Running frontend checks..."
                #   cd frontend
                #   npm run lint
                #   npm run typecheck
                #   npm run build
                #   cd ..
                # fi
              '';
            };
          }) // {
            meta = {
              description = "Run the full CI suite (pre-commit, tests, lint, build)";
              maintainers = [ "carpenike" ];
              license = pkgs.lib.licenses.asl20;
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
        packages = {
          coachiq = coachiqPackage;
          default = coachiqPackage;
          frontend = pkgs.buildNpmPackage {
            pname = "coachiq-frontend";
            inherit version;
            src = ./frontend;

            npmDepsHash = "sha256-eY3ikgJDgfpwq2BgiPorWlZdsaiG0wRDtcKagp4T1VM=";

            # Handle React 19 peer dependency conflicts
            npmFlags = [ "--legacy-peer-deps" ];

            nativeBuildInputs = [
              pkgs.nodejs_20
              pkgs.python3
              pkgs.pkg-config
            ] ++ pkgs.lib.optionals pkgs.stdenv.isDarwin [
              pkgs.darwin.apple_sdk.frameworks.Security
            ] ++ pkgs.lib.optionals pkgs.stdenv.isLinux [
              pkgs.libsecret
            ];

            # Set production environment variables for Vite build
            # Use relative paths for reverse proxy deployment
            preBuild = ''
              export VITE_API_URL=""
              export VITE_WS_URL=""
              export VITE_BACKEND_WS_URL=""
            '';

            # Use Vite directly to avoid TypeScript path resolution issues
            buildPhase = ''
              runHook preBuild
              npx vite build
              runHook postBuild
            '';

            installPhase = ''
              mkdir -p $out
              cp -r dist/* $out/
            '';

            meta = {
              description = "CoachIQ React frontend static files (built with Vite)";
              license = pkgs.lib.licenses.mit;
              platforms = pkgs.lib.platforms.unix;
            };
          };
        };

        devShells = {
          default = devShell;
          ci      = ciShell;
        };

        inherit apps checks;
      }
    ) //
    {
      nixosModules.coachiq = { config, lib, pkgs, ... }: {
        options.coachiq = {
          enable = lib.mkEnableOption "Enable CoachIQ RV-C network server";

          package = lib.mkOption {
            type = lib.types.package;
            default = self.packages.${pkgs.system}.coachiq;
            description = "The CoachIQ package to use";
          };

          settings = {
            # App metadata
            appName = lib.mkOption {
              type = lib.types.str;
              default = "CoachIQ";
              description = "Application name";
            };

            appVersion = lib.mkOption {
              type = lib.types.str;
              default = "0.0.0";
              description = "Application version";
            };

            appDescription = lib.mkOption {
              type = lib.types.str;
              default = "API for RV-C CANbus";
              description = "Application description";
            };

            appTitle = lib.mkOption {
              type = lib.types.str;
              default = "RV-C API";
              description = "API title for documentation";
            };

            # Server configuration
            server = {
              host = lib.mkOption {
                type = lib.types.nullOr lib.types.str;
                default = null;
                description = ''
                  Host to bind the server to.
                  Default: "0.0.0.0" (binds to all interfaces)
                  Example: "127.0.0.1" (localhost only)
                '';
              };

              port = lib.mkOption {
                type = lib.types.nullOr lib.types.int;
                default = null;
                description = ''
                  Port to bind the server to.
                  Default: 8000
                  Example: 8080
                '';
              };

              workers = lib.mkOption {
                type = lib.types.int;
                default = 1;
                description = "Number of worker processes";
              };

              reload = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Enable auto-reload for development";
              };

              debug = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Enable debug mode";
              };

              rootPath = lib.mkOption {
                type = lib.types.str;
                default = "";
                description = "Root path for the application";
              };

              accessLog = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable access logging";
              };

              keepAliveTimeout = lib.mkOption {
                type = lib.types.int;
                default = 5;
                description = "Keep-alive timeout in seconds";
              };

              timeoutGracefulShutdown = lib.mkOption {
                type = lib.types.int;
                default = 30;
                description = "Graceful shutdown timeout";
              };

              limitConcurrency = lib.mkOption {
                type = lib.types.nullOr lib.types.int;
                default = null;
                description = "Maximum number of concurrent connections";
              };

              limitMaxRequests = lib.mkOption {
                type = lib.types.nullOr lib.types.int;
                default = null;
                description = "Maximum number of requests before worker restart";
              };

              timeoutNotify = lib.mkOption {
                type = lib.types.int;
                default = 30;
                description = "Timeout for worker startup notification";
              };

              # SSL/TLS settings
              sslKeyfile = lib.mkOption {
                type = lib.types.nullOr lib.types.str;
                default = null;
                description = "SSL key file path";
              };

              sslCertfile = lib.mkOption {
                type = lib.types.nullOr lib.types.str;
                default = null;
                description = "SSL certificate file path";
              };

              sslCaCerts = lib.mkOption {
                type = lib.types.nullOr lib.types.str;
                default = null;
                description = "SSL CA certificates file path";
              };

              sslCertReqs = lib.mkOption {
                type = lib.types.int;
                default = 0;
                description = "SSL certificate verification mode (0=CERT_NONE, 1=CERT_OPTIONAL, 2=CERT_REQUIRED)";
              };

              workerClass = lib.mkOption {
                type = lib.types.str;
                default = "uvicorn.workers.UvicornWorker";
                description = "Worker class to use";
              };

              workerConnections = lib.mkOption {
                type = lib.types.int;
                default = 1000;
                description = "Maximum number of simultaneous clients";
              };

              serverHeader = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Include server header in responses";
              };

              dateHeader = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Include date header in responses";
              };
            };

            # CORS settings
            cors = {
              allowedOrigins = lib.mkOption {
                type = lib.types.listOf lib.types.str;
                default = [ "*" ];
                description = "Allowed origins for CORS";
              };

              allowedCredentials = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Allow credentials in CORS";
              };

              allowedMethods = lib.mkOption {
                type = lib.types.listOf lib.types.str;
                default = [ "*" ];
                description = "Allowed methods for CORS";
              };

              allowedHeaders = lib.mkOption {
                type = lib.types.listOf lib.types.str;
                default = [ "*" ];
                description = "Allowed headers for CORS";
              };
            };

            # Security settings
            security = {
              secretKey = lib.mkOption {
                type = lib.types.nullOr lib.types.str;
                default = null;
                description = "Secret key for JWT tokens";
              };

              jwtAlgorithm = lib.mkOption {
                type = lib.types.str;
                default = "HS256";
                description = "JWT algorithm";
              };

              jwtExpireMinutes = lib.mkOption {
                type = lib.types.int;
                default = 30;
                description = "JWT token expiration in minutes";
              };

              tlsTerminationIsExternal = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "When true, the application assumes it's behind a TLS-terminating reverse proxy. The proxy is responsible for HTTP->HTTPS redirection and HSTS headers. The application MUST be run with --proxy-headers for this to be secure.";
              };
            };

            # Logging settings
            logging = {
              level = lib.mkOption {
                type = lib.types.str;
                default = "INFO";
                description = "Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)";
              };

              format = lib.mkOption {
                type = lib.types.str;
                default = "%(asctime)s - %(name)s - %(levelname)s - %(message)s";
                description = "Log message format";
              };

              logToFile = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Enable file logging";
              };

              logFile = lib.mkOption {
                type = lib.types.nullOr lib.types.str;
                default = null;
                description = "Log file path";
              };

              maxFileSize = lib.mkOption {
                type = lib.types.int;
                default = 10485760;
                description = "Max log file size in bytes (10MB)";
              };

              backupCount = lib.mkOption {
                type = lib.types.int;
                default = 5;
                description = "Number of backup log files to keep";
              };
            };

            # CAN bus settings
            canbus = {
              bustype = lib.mkOption {
                type = lib.types.str;
                default = "virtual";
                description = ''
                  CAN bus type. Options:
                  - "virtual": Cross-platform virtual CAN (recommended for development)
                  - "socketcan": Linux-only socketcan interface
                  - "pcan": PEAK CAN hardware
                '';
              };

              channels = lib.mkOption {
                type = lib.types.listOf lib.types.str;
                default = [ "virtual0" ];
                description = ''
                  CAN channels to use.
                  Default is [ "virtual0" ] for cross-platform development.
                  For Linux with socketcan: [ "can0" ] or [ "vcan0" ]
                  For multiple interfaces: [ "can0" "can1" ]
                '';
              };

              bitrate = lib.mkOption {
                type = lib.types.int;
                default = 500000;
                description = "CAN bus bitrate (RV-C standard is 500000)";
              };

              interfaceMappings = lib.mkOption {
                type = lib.types.attrsOf lib.types.str;
                default = { house = "can0"; chassis = "can1"; };
                description = ''
                  Logical to physical CAN interface mappings.
                  Maps logical interface names (used in coach configs) to physical interfaces.
                  Example: { house = "can0"; chassis = "can1"; engine = "can2"; }
                '';
              };
            };

            # Persistence settings
            persistence = {
              enabled = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Enable data persistence";
              };

              dataDir = lib.mkOption {
                type = lib.types.str;
                default = "/var/lib/coachiq";
                description = "Base directory for persistent data storage";
              };

              createDirs = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Automatically create data directories if they don't exist";
              };

              backupEnabled = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable automatic backups";
              };

              backupRetentionDays = lib.mkOption {
                type = lib.types.int;
                default = 30;
                description = "Number of days to retain backups (1-365)";
              };

              maxBackupSizeMb = lib.mkOption {
                type = lib.types.int;
                default = 500;
                description = "Maximum backup size in MB (1-10000)";
              };
            };

            # Feature flags
            features = {
              enableMaintenanceTracking = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Enable maintenance tracking features";
              };

              enableNotifications = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Enable notification services";
              };

              enableUptimerobot = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Enable UptimeRobot integration";
              };

              enablePushover = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Enable Pushover notifications";
              };

              enableVectorSearch = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable vector search features";
              };

              enableApiDocs = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable API documentation endpoints";
              };

              enableMetrics = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable Prometheus metrics";
              };

              # Multi-protocol features
              enableJ1939 = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Enable J1939 protocol integration for engine, transmission, and chassis systems";
              };

              enableFirefly = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Enable Firefly RV systems integration with proprietary DGN support";
              };

              enableSpartanK2 = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Enable Spartan K2 chassis integration with advanced diagnostics";
              };

              enableMultiNetworkCAN = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Enable multi-network CAN management with fault isolation";
              };

              enableAdvancedDiagnostics = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Enable advanced diagnostics with fault correlation and predictive maintenance";
              };

              enablePerformanceAnalytics = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Enable performance analytics with telemetry collection and optimization";
              };

              enableDeviceDiscovery = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Enable device discovery and active polling";
              };

              # New features from feature_flags.yaml
              enableCanbusDeoderV2 = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Enable enhanced CAN bus decoder architecture with safety state engine";
              };

              enableDashboardAggregation = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable aggregated dashboard endpoints for optimized data loading";
              };

              enableSystemAnalytics = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable system analytics, performance monitoring, and alerting";
              };

              enableActivityTracking = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable activity feed tracking and recent events monitoring";
              };

              enableAnalyticsDashboard = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable advanced analytics dashboard with performance visualization";
              };

              enablePredictiveMaintenance = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable predictive maintenance with component health tracking";
              };

              enableLogHistory = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable REST API and WebSocket endpoints for log history";
              };

              enableLogStreaming = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable WebSocket log streaming endpoints and handlers";
              };

              enableGithubUpdateChecker = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Enable GitHub update checker service for application updates";
              };

              # Domain API v2 features
              enableDomainApiV2 = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable Domain-driven API v2 with safety-critical command patterns";
              };

              enableEntitiesApiV2 = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable Domain-specific entities API v2 with bulk operations";
              };

              enableDiagnosticsApiV2 = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Enable Domain-specific diagnostics API v2 with enhanced fault correlation";
              };

              enableAnalyticsApiV2 = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Enable Domain-specific analytics API v2 with advanced telemetry";
              };

              enableNetworksApiV2 = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Enable Domain-specific networks API v2 with CAN bus monitoring";
              };

              enableSystemApiV2 = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Enable Domain-specific system API v2 with configuration management";
              };
            };

            # CAN Bus Decoder v2 configuration
            canbusDecoderV2 = {
              enableSafetyStateEngine = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable safety state engine for enhanced CAN decoder";
              };

              enableProtocolRouter = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable protocol router for multi-protocol support";
              };

              enableConfigurationService = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable configuration service for dynamic settings";
              };

              enableBamOptimization = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable BAM (Broadcast Announce Message) optimization";
              };

              enableAdaptiveSecurity = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Enable adaptive security features";
              };

              enablePerformanceMonitoring = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable performance monitoring for CAN decoder";
              };

              safetyStateTimeoutSeconds = lib.mkOption {
                type = lib.types.float;
                default = 30.0;
                description = "Safety state timeout in seconds";
              };

              movingSpeedThresholdMph = lib.mkOption {
                type = lib.types.float;
                default = 0.5;
                description = "Moving speed threshold in MPH for safety state";
              };

              configurationCacheTtlSeconds = lib.mkOption {
                type = lib.types.int;
                default = 300;
                description = "Configuration cache TTL in seconds";
              };

              maxConcurrentBamSessions = lib.mkOption {
                type = lib.types.int;
                default = 100;
                description = "Maximum concurrent BAM sessions";
              };

              performanceMonitoringIntervalSeconds = lib.mkOption {
                type = lib.types.float;
                default = 10.0;
                description = "Performance monitoring interval in seconds";
              };
            };

            # Maintenance settings
            maintenance = {
              checkInterval = lib.mkOption {
                type = lib.types.int;
                default = 3600;
                description = "Check interval in seconds (minimum 60)";
              };

              notificationThresholdDays = lib.mkOption {
                type = lib.types.int;
                default = 7;
                description = "Days before due to send notifications";
              };

              databasePath = lib.mkOption {
                type = lib.types.nullOr lib.types.str;
                default = null;
                description = "Maintenance database path";
              };
            };

            # RV-C protocol configuration
            rvc = {
              enableEncoder = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable RV-C command encoding for bidirectional communication";
              };

              enableValidator = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable enhanced message validation with multi-layer checking";
              };

              enableSecurity = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable security features with anomaly detection and rate limiting";
              };

              enablePerformance = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable performance optimization with priority-based processing";
              };

              maxQueueSize = lib.mkOption {
                type = lib.types.int;
                default = 10000;
                description = "Maximum message queue size for performance optimization";
              };
            };

            # J1939 protocol configuration
            j1939 = {
              enableCumminsExtensions = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable Cummins engine-specific PGN extensions";
              };

              enableAllisonExtensions = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable Allison transmission-specific PGN extensions";
              };

              enableChassisExtensions = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable chassis system PGN extensions";
              };

              enableRvcBridge = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable bidirectional J1939 ↔ RV-C protocol bridge";
              };

              enableValidator = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable J1939 message validation";
              };

              enableSecurity = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable J1939 security features";
              };

              maxQueueSize = lib.mkOption {
                type = lib.types.int;
                default = 10000;
                description = "Maximum J1939 message queue size";
              };
            };

            # Firefly RV systems configuration
            firefly = {
              enableMultiplexing = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable Firefly message multiplexing support";
              };

              enableCustomDgns = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable Firefly proprietary DGN support";
              };

              enableStateInterlocks = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable Firefly safety interlock system";
              };

              enableCanDetectiveIntegration = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Enable integration with Firefly's CAN Detective tool";
              };

              multiplexTimeoutMs = lib.mkOption {
                type = lib.types.int;
                default = 1000;
                description = "Timeout for multiplex message assembly in milliseconds";
              };

              multiplexBufferSize = lib.mkOption {
                type = lib.types.int;
                default = 100;
                description = "Buffer size for multiplex message assembly";
              };
            };

            # Spartan K2 chassis configuration
            spartanK2 = {
              enableSafetyInterlocks = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable Spartan K2 chassis safety interlock validation";
              };

              enableAdvancedDiagnostics = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable advanced chassis diagnostic capabilities";
              };

              enableBrakeMonitoring = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable brake system monitoring and validation";
              };

              enableSuspensionControl = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable suspension system control and monitoring";
              };

              enableSteeringMonitoring = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable steering system monitoring";
              };

              brakePressureThreshold = lib.mkOption {
                type = lib.types.float;
                default = 80.0;
                description = "Brake pressure threshold in PSI for safety validation";
              };

              levelDifferentialThreshold = lib.mkOption {
                type = lib.types.float;
                default = 15.0;
                description = "Suspension level differential threshold in degrees";
              };

              steeringPressureThreshold = lib.mkOption {
                type = lib.types.float;
                default = 1000.0;
                description = "Steering assist pressure threshold in PSI";
              };

              safetyCheckFrequency = lib.mkOption {
                type = lib.types.int;
                default = 5;
                description = "Safety check frequency in seconds";
              };
            };

            # Multi-network CAN configuration
            multiNetworkCAN = {
              enableHealthMonitoring = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable continuous network health monitoring";
              };

              enableFaultIsolation = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable automatic network fault isolation";
              };

              enableCrossNetworkRouting = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Enable cross-network message routing (security consideration)";
              };

              enableNetworkSecurity = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable network-level security filtering";
              };

              maxNetworks = lib.mkOption {
                type = lib.types.int;
                default = 8;
                description = "Maximum number of supported network segments";
              };

              healthCheckInterval = lib.mkOption {
                type = lib.types.int;
                default = 5;
                description = "Network health check interval in seconds";
              };
            };

            # Advanced diagnostics configuration
            advancedDiagnostics = {
              enableDtcProcessing = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable diagnostic trouble code processing";
              };

              enableFaultCorrelation = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable fault correlation analysis";
              };

              enablePredictiveMaintenance = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable predictive maintenance analysis";
              };

              enableCrossProtocolAnalysis = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable cross-protocol diagnostic analysis";
              };

              correlationTimeWindowSeconds = lib.mkOption {
                type = lib.types.float;
                default = 60.0;
                description = "Time window for fault correlation analysis in seconds";
              };

              dtcRetentionDays = lib.mkOption {
                type = lib.types.int;
                default = 90;
                description = "Number of days to retain diagnostic trouble codes";
              };

              predictionConfidenceThreshold = lib.mkOption {
                type = lib.types.float;
                default = 0.7;
                description = "Minimum confidence threshold for predictive maintenance";
              };

              performanceHistoryDays = lib.mkOption {
                type = lib.types.int;
                default = 30;
                description = "Number of days of performance history to analyze";
              };
            };

            # Performance analytics configuration
            performanceAnalytics = {
              enableTelemetryCollection = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable performance telemetry collection";
              };

              enableResourceMonitoring = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable system resource monitoring";
              };

              enableTrendAnalysis = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable performance trend analysis";
              };

              enableOptimizationRecommendations = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable automated optimization recommendations";
              };

              telemetryCollectionIntervalSeconds = lib.mkOption {
                type = lib.types.float;
                default = 5.0;
                description = "Telemetry collection interval in seconds";
              };

              resourceMonitoringIntervalSeconds = lib.mkOption {
                type = lib.types.float;
                default = 10.0;
                description = "Resource monitoring interval in seconds";
              };

              metricRetentionHours = lib.mkOption {
                type = lib.types.int;
                default = 24;
                description = "Number of hours to retain performance metrics";
              };

              baselineEstablishmentHours = lib.mkOption {
                type = lib.types.int;
                default = 1;
                description = "Hours required to establish performance baselines";
              };

              cpuWarningThresholdPercent = lib.mkOption {
                type = lib.types.float;
                default = 80.0;
                description = "CPU usage warning threshold percentage";
              };

              memoryWarningThresholdPercent = lib.mkOption {
                type = lib.types.float;
                default = 80.0;
                description = "Memory usage warning threshold percentage";
              };

              canBusLoadWarningThresholdPercent = lib.mkOption {
                type = lib.types.float;
                default = 70.0;
                description = "CAN bus load warning threshold percentage";
              };
            };

            # Unified notification system settings
            notifications = {
              enabled = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Enable unified notification system using Apprise";
              };

              defaultTitle = lib.mkOption {
                type = lib.types.str;
                default = "CoachIQ Notification";
                description = "Default notification title";
              };

              templatePath = lib.mkOption {
                type = lib.types.str;
                default = "templates/notifications/";
                description = "Path to notification templates";
              };

              logNotifications = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Log notification attempts and results";
              };

              # SMTP configuration
              smtp = {
                enabled = lib.mkOption {
                  type = lib.types.bool;
                  default = false;
                  description = "Enable SMTP email notifications";
                };

                host = lib.mkOption {
                  type = lib.types.str;
                  default = "localhost";
                  description = "SMTP server hostname";
                };

                port = lib.mkOption {
                  type = lib.types.int;
                  default = 587;
                  description = "SMTP server port";
                };

                username = lib.mkOption {
                  type = lib.types.str;
                  default = "";
                  description = "SMTP authentication username";
                };

                password = lib.mkOption {
                  type = lib.types.str;
                  default = "";
                  description = "SMTP authentication password";
                };

                fromEmail = lib.mkOption {
                  type = lib.types.str;
                  default = "noreply@coachiq.com";
                  description = "From email address";
                };

                fromName = lib.mkOption {
                  type = lib.types.str;
                  default = "CoachIQ";
                  description = "From display name";
                };

                useTls = lib.mkOption {
                  type = lib.types.bool;
                  default = true;
                  description = "Use TLS encryption";
                };

                useSsl = lib.mkOption {
                  type = lib.types.bool;
                  default = false;
                  description = "Use SSL encryption";
                };

                timeout = lib.mkOption {
                  type = lib.types.int;
                  default = 30;
                  description = "Connection timeout in seconds";
                };
              };

              # Slack configuration
              slack = {
                enabled = lib.mkOption {
                  type = lib.types.bool;
                  default = false;
                  description = "Enable Slack notifications";
                };

                webhookUrl = lib.mkOption {
                  type = lib.types.str;
                  default = "";
                  description = "Slack webhook URL";
                };
              };

              # Discord configuration
              discord = {
                enabled = lib.mkOption {
                  type = lib.types.bool;
                  default = false;
                  description = "Enable Discord notifications";
                };

                webhookUrl = lib.mkOption {
                  type = lib.types.str;
                  default = "";
                  description = "Discord webhook URL";
                };
              };

              # Legacy Pushover settings (deprecated)
              pushoverUserKey = lib.mkOption {
                type = lib.types.nullOr lib.types.str;
                default = null;
                description = "DEPRECATED: Pushover user key - migrate to unified notification system";
              };

              pushoverApiToken = lib.mkOption {
                type = lib.types.nullOr lib.types.str;
                default = null;
                description = "DEPRECATED: Pushover API token - migrate to unified notification system";
              };

              pushoverDevice = lib.mkOption {
                type = lib.types.nullOr lib.types.str;
                default = null;
                description = "DEPRECATED: Pushover device name - migrate to unified notification system";
              };

              pushoverPriority = lib.mkOption {
                type = lib.types.nullOr lib.types.int;
                default = null;
                description = "DEPRECATED: Pushover message priority (-2 to 2) - migrate to unified notification system";
              };

              # UptimeRobot settings
              uptimerobotApiKey = lib.mkOption {
                type = lib.types.nullOr lib.types.str;
                default = null;
                description = "UptimeRobot API key";
              };
            };

            # Authentication system settings
            authentication = {
              enabled = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Enable authentication system";
              };

              secretKey = lib.mkOption {
                type = lib.types.str;
                default = "";
                description = "Secret key for JWT tokens";
              };

              jwtAlgorithm = lib.mkOption {
                type = lib.types.str;
                default = "HS256";
                description = "JWT signing algorithm";
              };

              jwtExpireMinutes = lib.mkOption {
                type = lib.types.int;
                default = 30;
                description = "JWT token expiration in minutes";
              };

              baseUrl = lib.mkOption {
                type = lib.types.str;
                default = "http://localhost:8000";
                description = "Base URL for magic link generation";
              };

              # Single-user mode settings
              adminUsername = lib.mkOption {
                type = lib.types.str;
                default = "admin";
                description = "Admin username for single-user mode";
              };

              adminPassword = lib.mkOption {
                type = lib.types.str;
                default = "";
                description = "Admin password for single-user mode (leave empty to auto-generate)";
              };

              # Multi-user mode settings
              adminEmail = lib.mkOption {
                type = lib.types.str;
                default = "";
                description = "Admin email for multi-user mode";
              };

              enableMagicLinks = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable magic link authentication";
              };

              magicLinkExpireMinutes = lib.mkOption {
                type = lib.types.int;
                default = 15;
                description = "Magic link expiration in minutes";
              };

              # OAuth settings
              enableOauth = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Enable OAuth authentication";
              };

              oauthGithubClientId = lib.mkOption {
                type = lib.types.str;
                default = "";
                description = "GitHub OAuth client ID";
              };

              oauthGithubClientSecret = lib.mkOption {
                type = lib.types.str;
                default = "";
                description = "GitHub OAuth client secret";
              };

              oauthGoogleClientId = lib.mkOption {
                type = lib.types.str;
                default = "";
                description = "Google OAuth client ID";
              };

              oauthGoogleClientSecret = lib.mkOption {
                type = lib.types.str;
                default = "";
                description = "Google OAuth client secret";
              };

              oauthMicrosoftClientId = lib.mkOption {
                type = lib.types.str;
                default = "";
                description = "Microsoft OAuth client ID";
              };

              oauthMicrosoftClientSecret = lib.mkOption {
                type = lib.types.str;
                default = "";
                description = "Microsoft OAuth client secret";
              };

              # Session management
              sessionExpireHours = lib.mkOption {
                type = lib.types.int;
                default = 24;
                description = "Session expiration in hours";
              };

              maxSessionsPerUser = lib.mkOption {
                type = lib.types.int;
                default = 5;
                description = "Maximum sessions per user";
              };

              # Security settings
              requireSecureCookies = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Require secure cookies in production";
              };

              rateLimitAuthAttempts = lib.mkOption {
                type = lib.types.int;
                default = 5;
                description = "Rate limit for authentication attempts";
              };

              rateLimitWindowMinutes = lib.mkOption {
                type = lib.types.int;
                default = 15;
                description = "Rate limit window in minutes";
              };
            };

            # Multi-Factor Authentication system settings
            multiFactorAuthentication = {
              enabled = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Enable Multi-Factor Authentication system";
              };

              enableTotp = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable TOTP (Time-based One-Time Password) authentication";
              };

              enableBackupCodes = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable backup codes for account recovery";
              };

              enableRecoveryCodes = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable recovery codes for account recovery";
              };

              totpIssuer = lib.mkOption {
                type = lib.types.str;
                default = "CoachIQ";
                description = "TOTP issuer name displayed in authenticator apps";
              };

              totpDigits = lib.mkOption {
                type = lib.types.int;
                default = 6;
                description = "Number of digits in TOTP codes";
              };

              totpWindow = lib.mkOption {
                type = lib.types.int;
                default = 1;
                description = "TOTP time window tolerance";
              };

              backupCodesCount = lib.mkOption {
                type = lib.types.int;
                default = 10;
                description = "Number of backup codes to generate";
              };

              backupCodeLength = lib.mkOption {
                type = lib.types.int;
                default = 8;
                description = "Length of each backup code";
              };

              requireMfaForAdmin = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Require MFA for administrator accounts";
              };

              allowMfaBypass = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Allow MFA bypass during emergency situations";
              };

              mfaSetupGracePeriodHours = lib.mkOption {
                type = lib.types.int;
                default = 24;
                description = "Grace period in hours for MFA setup";
              };

              backupCodeRegenerationThreshold = lib.mkOption {
                type = lib.types.int;
                default = 3;
                description = "Minimum backup codes remaining before regeneration warning";
              };
            };

            # Notification routing configuration
            notificationRouting = {
              enabled = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable intelligent notification routing";
              };

              quietHoursEnabled = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable quiet hours for notifications";
              };

              defaultQuietHoursStart = lib.mkOption {
                type = lib.types.str;
                default = "22:00";
                description = "Default quiet hours start time (HH:MM)";
              };

              defaultQuietHoursEnd = lib.mkOption {
                type = lib.types.str;
                default = "08:00";
                description = "Default quiet hours end time (HH:MM)";
              };

              escalationEnabled = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable notification escalation";
              };

              escalationDelayMinutes = lib.mkOption {
                type = lib.types.int;
                default = 15;
                description = "Delay before escalating notifications";
              };

              maxRoutingRules = lib.mkOption {
                type = lib.types.int;
                default = 100;
                description = "Maximum number of routing rules";
              };
            };

            # Notification analytics configuration
            notificationAnalytics = {
              enabled = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable notification analytics and metrics";
              };

              bufferSizeLimit = lib.mkOption {
                type = lib.types.int;
                default = 100;
                description = "Analytics buffer size limit";
              };

              bufferFlushInterval = lib.mkOption {
                type = lib.types.int;
                default = 30;
                description = "Buffer flush interval in seconds";
              };

              metricCacheTtl = lib.mkOption {
                type = lib.types.int;
                default = 300;
                description = "Metric cache TTL in seconds";
              };

              aggregationInterval = lib.mkOption {
                type = lib.types.int;
                default = 3600;
                description = "Metric aggregation interval in seconds";
              };

              healthCheckInterval = lib.mkOption {
                type = lib.types.int;
                default = 300;
                description = "Health check interval in seconds";
              };

              retentionDays = lib.mkOption {
                type = lib.types.int;
                default = 90;
                description = "Analytics data retention in days";
              };

              enableRealTimeMetrics = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable real-time metric collection";
              };

              enableErrorAnalysis = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable error analysis and tracking";
              };
            };

            # Email template configuration
            emailTemplates = {
              templateDir = lib.mkOption {
                type = lib.types.str;
                default = "backend/templates/email";
                description = "Email template directory";
              };

              cacheTtlMinutes = lib.mkOption {
                type = lib.types.int;
                default = 60;
                description = "Template cache TTL in minutes";
              };

              enableCaching = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable template caching";
              };

              enableValidation = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable template validation";
              };

              enableSandbox = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable sandboxed template environment";
              };

              defaultLanguage = lib.mkOption {
                type = lib.types.str;
                default = "en";
                description = "Default template language";
              };

              supportedLanguages = lib.mkOption {
                type = lib.types.listOf lib.types.str;
                default = ["en" "es" "fr"];
                description = "Supported template languages";
              };

              enableAbTesting = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "Enable A/B testing for templates";
              };
            };

            # Notification performance configuration
            notificationPerformance = {
              connectionPoolSize = lib.mkOption {
                type = lib.types.int;
                default = 10;
                description = "Connection pool size for notification channels";
              };

              circuitBreakerEnabled = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable circuit breaker pattern";
              };

              circuitBreakerThreshold = lib.mkOption {
                type = lib.types.int;
                default = 5;
                description = "Circuit breaker failure threshold";
              };

              circuitBreakerTimeout = lib.mkOption {
                type = lib.types.int;
                default = 60;
                description = "Circuit breaker timeout in seconds";
              };

              batchSize = lib.mkOption {
                type = lib.types.int;
                default = 50;
                description = "Notification batch size";
              };

              batchTimeout = lib.mkOption {
                type = lib.types.int;
                default = 5;
                description = "Batch timeout in seconds";
              };

              enableConnectionPooling = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable connection pooling";
              };

              enableRetryBackoff = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable exponential retry backoff";
              };

              maxRetryDelay = lib.mkOption {
                type = lib.types.int;
                default = 300;
                description = "Maximum retry delay in seconds";
              };
            };

            # Notification batching configuration
            notificationBatching = {
              enabled = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable notification batching";
              };

              maxBatchSize = lib.mkOption {
                type = lib.types.int;
                default = 100;
                description = "Maximum batch size";
              };

              batchTimeoutSeconds = lib.mkOption {
                type = lib.types.int;
                default = 10;
                description = "Batch timeout in seconds";
              };

              maxRetryAttempts = lib.mkOption {
                type = lib.types.int;
                default = 3;
                description = "Maximum retry attempts for batch";
              };

              enableSmartBatching = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable smart batching logic";
              };

              priorityThreshold = lib.mkOption {
                type = lib.types.str;
                default = "high";
                description = "Priority threshold for immediate delivery";
              };
            };

            # Notification rate limiting configuration
            notificationRateLimiting = {
              enabled = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable notification rate limiting";
              };

              defaultRateLimit = lib.mkOption {
                type = lib.types.int;
                default = 100;
                description = "Default rate limit per window";
              };

              defaultWindowSeconds = lib.mkOption {
                type = lib.types.int;
                default = 3600;
                description = "Default rate limit window in seconds";
              };

              perChannelLimits = lib.mkOption {
                type = lib.types.attrsOf lib.types.int;
                default = {
                  email = 50;
                  slack = 100;
                  webhook = 200;
                };
                description = "Per-channel rate limits";
              };

              enableBurstAllowance = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable burst allowance";
              };

              burstMultiplier = lib.mkOption {
                type = lib.types.float;
                default = 1.5;
                description = "Burst multiplier for rate limits";
              };
            };

            # Notification queue configuration
            notificationQueue = {
              maxQueueSize = lib.mkOption {
                type = lib.types.int;
                default = 10000;
                description = "Maximum queue size";
              };

              workerCount = lib.mkOption {
                type = lib.types.int;
                default = 4;
                description = "Number of queue workers";
              };

              priorityLevels = lib.mkOption {
                type = lib.types.listOf lib.types.str;
                default = ["low" "medium" "high" "critical"];
                description = "Notification priority levels";
              };

              enablePersistence = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable queue persistence";
              };

              persistenceInterval = lib.mkOption {
                type = lib.types.int;
                default = 60;
                description = "Queue persistence interval in seconds";
              };

              deadLetterEnabled = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable dead letter queue";
              };

              deadLetterThreshold = lib.mkOption {
                type = lib.types.int;
                default = 5;
                description = "Dead letter threshold";
              };
            };

            # Legacy compatibility options (for existing deployments)
            pushover = {
              enable = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "DEPRECATED: Use features.enablePushover instead";
              };
              apiToken = lib.mkOption {
                type = lib.types.str;
                default = "";
                description = "DEPRECATED: Use notifications.pushoverApiToken instead";
              };
              userKey = lib.mkOption {
                type = lib.types.str;
                default = "";
                description = "DEPRECATED: Use notifications.pushoverUserKey instead";
              };
              device = lib.mkOption {
                type = lib.types.nullOr lib.types.str;
                default = null;
                description = "DEPRECATED: Use notifications.pushoverDevice instead";
              };
              priority = lib.mkOption {
                type = lib.types.nullOr lib.types.int;
                default = null;
                description = "DEPRECATED: Use notifications.pushoverPriority instead";
              };
            };

            uptimerobot = {
              enable = lib.mkOption {
                type = lib.types.bool;
                default = false;
                description = "DEPRECATED: Use features.enableUptimerobot instead";
              };
              apiKey = lib.mkOption {
                type = lib.types.str;
                default = "";
                description = "DEPRECATED: Use notifications.uptimerobotApiKey instead";
              };
            };

            # File paths
            rvcSpecPath = lib.mkOption {
              type = lib.types.nullOr lib.types.str;
              default = null;
              description = "Override path to rvc.json (RVC spec file)";
            };

            rvcCoachMappingPath = lib.mkOption {
              type = lib.types.nullOr lib.types.str;
              default = null;
              description = "Coach mapping file path";
            };

            rvcCoachModel = lib.mkOption {
              type = lib.types.nullOr lib.types.str;
              default = null;
              description = ''
                RV-C coach model for automatic mapping selection.
                Example: "2021_Entegra_Aspire_44R"
                If set, will load the corresponding coach mapping file with interface requirements.
              '';
            };

            staticDir = lib.mkOption {
              type = lib.types.str;
              default = "static";
              description = "Static files directory";
            };

            deviceMappingPath = lib.mkOption {
              type = lib.types.nullOr lib.types.str;
              default = null;
              description = "Override path to coach_mapping.default.yml or a model-specific mapping file. If not set, uses modelSelector if provided.";
            };

            modelSelector = lib.mkOption {
              type = lib.types.nullOr lib.types.str;
              default = null;
              description = ''
                Model selector for coach mapping file. Example: "2021_Entegra_Aspire_44R" will use
                "${config.coachiq.package}/share/coachiq/mappings/" + config.coachiq.settings.modelSelector + ".yml" as the mapping file if deviceMappingPath is not set.
                If both are unset, falls back to coach_mapping.default.yml.
              '';
            };

            userCoachInfoPath = lib.mkOption {
              type = lib.types.nullOr lib.types.str;
              default = null;
              description = "Path to user coach info YAML file";
            };

            # Legacy server configuration (for backward compatibility)
            host = lib.mkOption {
              type = lib.types.str;
              default = "0.0.0.0";
              description = "DEPRECATED: Use server.host instead - Host IP to bind the API server to";
            };

            port = lib.mkOption {
              type = lib.types.int;
              default = 8000;
              description = "DEPRECATED: Use server.port instead - Port to run the API server on";
            };

            logLevel = lib.mkOption {
              type = lib.types.str;
              default = "INFO";
              description = "DEPRECATED: Use logging.level instead - Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)";
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

            # Analytics dashboard configuration
            analyticsDashboard = {
              enabled = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable analytics dashboard";
              };

              # Memory-based analytics (no persistence required)
              memoryRetentionHours = lib.mkOption {
                type = lib.types.int;
                default = 2;
                description = "Hours to retain analytics data in memory";
              };

              insightGenerationIntervalSeconds = lib.mkOption {
                type = lib.types.int;
                default = 900;
                description = "Interval for generating system insights in seconds";
              };

              patternAnalysisIntervalSeconds = lib.mkOption {
                type = lib.types.int;
                default = 1800;
                description = "Interval for pattern analysis in seconds";
              };

              maxMemoryInsights = lib.mkOption {
                type = lib.types.int;
                default = 100;
                description = "Maximum number of insights to keep in memory";
              };

              maxMemoryPatterns = lib.mkOption {
                type = lib.types.int;
                default = 50;
                description = "Maximum number of patterns to keep in memory";
              };

              # Persistence settings (only used when persistence feature is enabled)
              persistenceRetentionDays = lib.mkOption {
                type = lib.types.int;
                default = 30;
                description = "Days to retain data in SQLite when persistence is enabled";
              };

              enableBackgroundPersistence = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable background tasks for data persistence";
              };

              sqliteBatchSize = lib.mkOption {
                type = lib.types.int;
                default = 100;
                description = "Batch size for SQLite operations";
              };

              dbPath = lib.mkOption {
                type = lib.types.str;
                default = "data/analytics.db";
                description = "Path to SQLite database file when persistence is enabled";
              };

              # Background processing
              enableBackgroundCleanup = lib.mkOption {
                type = lib.types.bool;
                default = true;
                description = "Enable automatic cleanup of old data";
              };

              cleanupIntervalSeconds = lib.mkOption {
                type = lib.types.int;
                default = 3600;
                description = "Interval for cleanup operations in seconds";
              };
            };
          };
        };

        config = lib.mkIf config.coachiq.enable {
          # Include the package in systemPackages
          environment.systemPackages = [ config.coachiq.package ];

          # Create persistent data directories with proper permissions
          systemd.tmpfiles.rules = lib.mkIf config.coachiq.settings.persistence.enabled ([
            # Main data directory
            "d ${config.coachiq.settings.persistence.dataDir} 0755 coachiq coachiq -"

            # User-writable directories
            "d ${config.coachiq.settings.persistence.dataDir}/database 0755 coachiq coachiq -"
            "d ${config.coachiq.settings.persistence.dataDir}/backups 0755 coachiq coachiq -"
            "d ${config.coachiq.settings.persistence.dataDir}/config 0755 coachiq coachiq -"
            "d ${config.coachiq.settings.persistence.dataDir}/themes 0755 coachiq coachiq -"
            "d ${config.coachiq.settings.persistence.dataDir}/dashboards 0755 coachiq coachiq -"
            "d ${config.coachiq.settings.persistence.dataDir}/logs 0755 coachiq coachiq -"

            # Read-only reference directory (owned by root, readable by coachiq)
            "d ${config.coachiq.settings.persistence.dataDir}/reference 0755 root root -"
          ] ++ lib.optionals (config.coachiq.settings.persistence.dataDir == "/var/lib/coachiq") [
            # Copy reference files from package on first install
            # These are read-only configuration files (RV-C specs, coach mappings)
            "C ${config.coachiq.settings.persistence.dataDir}/reference 0755 root root - ${config.coachiq.package}/share/coachiq/config"
          ]);

          # Create system user for coachiq service
          users.users.coachiq = {
            isSystemUser = true;
            group = "coachiq";
            description = "CoachIQ service user";
          };

          users.groups.coachiq = {};

          # Set up the systemd service
          systemd.services.coachiq = {
            description = "CoachIQ RV-C HTTP/WebSocket API";
            after       = [ "network.target" ];
            wantedBy    = [ "multi-user.target" ];

            serviceConfig = {
              ExecStartPre = [
                # Validate configuration before starting
                "${config.coachiq.package}/bin/coachiq-validate-config"
                # Ensure data directory exists with correct permissions
                "+${pkgs.coreutils}/bin/mkdir -p ${config.coachiq.settings.persistence.dataDir}"
                "+${pkgs.coreutils}/bin/chown -R coachiq:coachiq ${config.coachiq.settings.persistence.dataDir}"
              ];
              ExecStart = "${config.coachiq.package}/bin/coachiq-daemon";
              ExecStartPost = [
                # Wait for service to be ready (increased from 2s to 10s for proper initialization)
                "${pkgs.bash}/bin/bash -c 'sleep 10 && ${config.coachiq.package}/share/coachiq/nix/health-check.sh'"
              ];
              Restart    = "always";
              RestartSec = 5;
              User = "coachiq";
              Group = "coachiq";
              # Ensure the service can access CAN interfaces if needed
              SupplementaryGroups = [ "dialout" ];

              # Security hardening
              NoNewPrivileges = true;
              PrivateTmp = true;
              ProtectSystem = "strict";
              ProtectHome = true;
              StateDirectory = "coachiq";
              ReadWritePaths = [
                config.coachiq.settings.persistence.dataDir
                "/dev" # For CAN access
              ];
            };

            environment = lib.filterAttrs (n: v: v != null) ({
              # Always set environment (for production deployment)
              COACHIQ_ENVIRONMENT = "production";

              # App metadata - set if user provided values
              COACHIQ_APP_NAME = if config.coachiq.settings.appName != null then config.coachiq.settings.appName else null;
              COACHIQ_APP_VERSION = if config.coachiq.settings.appVersion != null then config.coachiq.settings.appVersion else null;

              # Server settings - set all user-configured values
              COACHIQ_SERVER__HOST = if config.coachiq.settings.server.host != null then config.coachiq.settings.server.host else null;
              COACHIQ_SERVER__PORT = if config.coachiq.settings.server.port != null then toString config.coachiq.settings.server.port else null;
              COACHIQ_SERVER__WORKERS = if config.coachiq.settings.server.workers != null then toString config.coachiq.settings.server.workers else null;

              # Never set reload in production - let application handle this based on environment
              # COACHIQ_SERVER__RELOAD is intentionally not set here

              # CORS - only if not using defaults
              COACHIQ_CORS__ALLOW_ORIGINS = lib.mkIf
                (config.coachiq.settings.cors.allowedOrigins != ["*"])
                (lib.concatStringsSep "," config.coachiq.settings.cors.allowedOrigins);

              # Security - only if provided
              COACHIQ_SECURITY__SECRET_KEY = lib.mkIf (config.coachiq.settings.security.secretKey != null) config.coachiq.settings.security.secretKey;
              COACHIQ_SECURITY__TLS_TERMINATION_IS_EXTERNAL = lib.mkIf config.coachiq.settings.security.tlsTerminationIsExternal "true";

              # Logging - only if explicitly set
              COACHIQ_LOGGING__LEVEL = lib.mkIf (config.coachiq.settings.logging.level != "INFO") config.coachiq.settings.logging.level;
              COACHIQ_LOGGING__LOG_FILE = lib.mkIf (config.coachiq.settings.logging.logFile != null) config.coachiq.settings.logging.logFile;

              # CAN settings - only if not default
              COACHIQ_CAN__BUSTYPE = lib.mkIf (config.coachiq.settings.canbus.bustype != "virtual") config.coachiq.settings.canbus.bustype;
              COACHIQ_CAN__INTERFACES = lib.mkIf
                (config.coachiq.settings.canbus.channels != ["virtual0"])
                (lib.concatStringsSep "," config.coachiq.settings.canbus.channels);

              # Persistence - only if enabled
              COACHIQ_PERSISTENCE__ENABLED = lib.mkIf config.coachiq.settings.persistence.enabled "true";
              COACHIQ_PERSISTENCE__DATA_DIR = lib.mkIf
                (config.coachiq.settings.persistence.enabled && config.coachiq.settings.persistence.dataDir != "/var/lib/coachiq")
                config.coachiq.settings.persistence.dataDir;

              # Features - only if different from defaults
              COACHIQ_FEATURES__ENABLE_MAINTENANCE_TRACKING = lib.mkIf config.coachiq.settings.features.enableMaintenanceTracking "true";
              COACHIQ_FEATURES__ENABLE_NOTIFICATIONS = lib.mkIf config.coachiq.settings.features.enableNotifications "true";
              COACHIQ_FEATURES__ENABLE_VECTOR_SEARCH = lib.mkIf (!config.coachiq.settings.features.enableVectorSearch) "false";
              COACHIQ_FEATURES__ENABLE_API_DOCS = lib.mkIf (!config.coachiq.settings.features.enableApiDocs) "false";
              COACHIQ_FEATURES__ENABLE_METRICS = lib.mkIf (!config.coachiq.settings.features.enableMetrics) "false";

              # Multi-protocol features - only if enabled
              COACHIQ_J1939__ENABLED = lib.mkIf config.coachiq.settings.features.enableJ1939 "true";
              COACHIQ_FIREFLY__ENABLED = lib.mkIf config.coachiq.settings.features.enableFirefly "true";
              COACHIQ_SPARTAN_K2__ENABLED = lib.mkIf config.coachiq.settings.features.enableSpartanK2 "true";
              COACHIQ_MULTI_NETWORK_CAN__ENABLED = lib.mkIf config.coachiq.settings.features.enableMultiNetworkCAN "true";
              COACHIQ_ADVANCED_DIAGNOSTICS__ENABLED = lib.mkIf config.coachiq.settings.features.enableAdvancedDiagnostics "true";
              COACHIQ_PERFORMANCE_ANALYTICS__ENABLED = lib.mkIf config.coachiq.settings.features.enablePerformanceAnalytics "true";
              COACHIQ_DEVICE_DISCOVERY__ENABLED = lib.mkIf config.coachiq.settings.features.enableDeviceDiscovery "true";

              # RV-C protocol settings - only if different from defaults
              COACHIQ_RVC__ENABLE_ENCODER = lib.mkIf (!config.coachiq.settings.rvc.enableEncoder) "false";
              COACHIQ_RVC__ENABLE_VALIDATOR = lib.mkIf (!config.coachiq.settings.rvc.enableValidator) "false";
              COACHIQ_RVC__ENABLE_SECURITY = lib.mkIf (!config.coachiq.settings.rvc.enableSecurity) "false";
              COACHIQ_RVC__ENABLE_PERFORMANCE = lib.mkIf (!config.coachiq.settings.rvc.enablePerformance) "false";
              COACHIQ_RVC__MAX_QUEUE_SIZE = lib.mkIf (config.coachiq.settings.rvc.maxQueueSize != 10000) (toString config.coachiq.settings.rvc.maxQueueSize);

              # J1939 protocol settings - only if enabled and different from defaults
              COACHIQ_J1939__ENABLE_CUMMINS_EXTENSIONS = lib.mkIf (config.coachiq.settings.features.enableJ1939 && !config.coachiq.settings.j1939.enableCumminsExtensions) "false";
              COACHIQ_J1939__ENABLE_ALLISON_EXTENSIONS = lib.mkIf (config.coachiq.settings.features.enableJ1939 && !config.coachiq.settings.j1939.enableAllisonExtensions) "false";
              COACHIQ_J1939__ENABLE_CHASSIS_EXTENSIONS = lib.mkIf (config.coachiq.settings.features.enableJ1939 && !config.coachiq.settings.j1939.enableChassisExtensions) "false";
              COACHIQ_J1939__ENABLE_RVC_BRIDGE = lib.mkIf (config.coachiq.settings.features.enableJ1939 && !config.coachiq.settings.j1939.enableRvcBridge) "false";
              COACHIQ_J1939__MAX_QUEUE_SIZE = lib.mkIf (config.coachiq.settings.features.enableJ1939 && config.coachiq.settings.j1939.maxQueueSize != 10000) (toString config.coachiq.settings.j1939.maxQueueSize);

              # Firefly settings - only if enabled and different from defaults
              COACHIQ_FIREFLY__ENABLE_MULTIPLEXING = lib.mkIf (config.coachiq.settings.features.enableFirefly && !config.coachiq.settings.firefly.enableMultiplexing) "false";
              COACHIQ_FIREFLY__ENABLE_CUSTOM_DGNS = lib.mkIf (config.coachiq.settings.features.enableFirefly && !config.coachiq.settings.firefly.enableCustomDgns) "false";
              COACHIQ_FIREFLY__ENABLE_STATE_INTERLOCKS = lib.mkIf (config.coachiq.settings.features.enableFirefly && !config.coachiq.settings.firefly.enableStateInterlocks) "false";
              COACHIQ_FIREFLY__ENABLE_CAN_DETECTIVE_INTEGRATION = lib.mkIf (config.coachiq.settings.features.enableFirefly && config.coachiq.settings.firefly.enableCanDetectiveIntegration) "true";
              COACHIQ_FIREFLY__MULTIPLEX_TIMEOUT_MS = lib.mkIf (config.coachiq.settings.features.enableFirefly && config.coachiq.settings.firefly.multiplexTimeoutMs != 1000) (toString config.coachiq.settings.firefly.multiplexTimeoutMs);

              # Spartan K2 settings - only if enabled and different from defaults
              COACHIQ_SPARTAN_K2__ENABLE_SAFETY_INTERLOCKS = lib.mkIf (config.coachiq.settings.features.enableSpartanK2 && !config.coachiq.settings.spartanK2.enableSafetyInterlocks) "false";
              COACHIQ_SPARTAN_K2__ENABLE_ADVANCED_DIAGNOSTICS = lib.mkIf (config.coachiq.settings.features.enableSpartanK2 && !config.coachiq.settings.spartanK2.enableAdvancedDiagnostics) "false";
              COACHIQ_SPARTAN_K2__BRAKE_PRESSURE_THRESHOLD = lib.mkIf (config.coachiq.settings.features.enableSpartanK2 && config.coachiq.settings.spartanK2.brakePressureThreshold != 80.0) (toString config.coachiq.settings.spartanK2.brakePressureThreshold);
              COACHIQ_SPARTAN_K2__LEVEL_DIFFERENTIAL_THRESHOLD = lib.mkIf (config.coachiq.settings.features.enableSpartanK2 && config.coachiq.settings.spartanK2.levelDifferentialThreshold != 15.0) (toString config.coachiq.settings.spartanK2.levelDifferentialThreshold);

              # Multi-network CAN settings - only if enabled and different from defaults
              COACHIQ_MULTI_NETWORK__ENABLE_HEALTH_MONITORING = lib.mkIf (config.coachiq.settings.features.enableMultiNetworkCAN && !config.coachiq.settings.multiNetworkCAN.enableHealthMonitoring) "false";
              COACHIQ_MULTI_NETWORK__ENABLE_FAULT_ISOLATION = lib.mkIf (config.coachiq.settings.features.enableMultiNetworkCAN && !config.coachiq.settings.multiNetworkCAN.enableFaultIsolation) "false";
              COACHIQ_MULTI_NETWORK__ENABLE_CROSS_NETWORK_ROUTING = lib.mkIf (config.coachiq.settings.features.enableMultiNetworkCAN && config.coachiq.settings.multiNetworkCAN.enableCrossNetworkRouting) "true";
              COACHIQ_MULTI_NETWORK__MAX_NETWORKS = lib.mkIf (config.coachiq.settings.features.enableMultiNetworkCAN && config.coachiq.settings.multiNetworkCAN.maxNetworks != 8) (toString config.coachiq.settings.multiNetworkCAN.maxNetworks);

              # Advanced diagnostics settings - only if enabled and different from defaults
              COACHIQ_ADVANCED_DIAGNOSTICS__ENABLE_DTC_PROCESSING = lib.mkIf (config.coachiq.settings.features.enableAdvancedDiagnostics && !config.coachiq.settings.advancedDiagnostics.enableDtcProcessing) "false";
              COACHIQ_ADVANCED_DIAGNOSTICS__ENABLE_FAULT_CORRELATION = lib.mkIf (config.coachiq.settings.features.enableAdvancedDiagnostics && !config.coachiq.settings.advancedDiagnostics.enableFaultCorrelation) "false";
              COACHIQ_ADVANCED_DIAGNOSTICS__ENABLE_PREDICTIVE_MAINTENANCE = lib.mkIf (config.coachiq.settings.features.enableAdvancedDiagnostics && !config.coachiq.settings.advancedDiagnostics.enablePredictiveMaintenance) "false";
              COACHIQ_ADVANCED_DIAGNOSTICS__CORRELATION_TIME_WINDOW_SECONDS = lib.mkIf (config.coachiq.settings.features.enableAdvancedDiagnostics && config.coachiq.settings.advancedDiagnostics.correlationTimeWindowSeconds != 60.0) (toString config.coachiq.settings.advancedDiagnostics.correlationTimeWindowSeconds);
              COACHIQ_ADVANCED_DIAGNOSTICS__DTC_RETENTION_DAYS = lib.mkIf (config.coachiq.settings.features.enableAdvancedDiagnostics && config.coachiq.settings.advancedDiagnostics.dtcRetentionDays != 90) (toString config.coachiq.settings.advancedDiagnostics.dtcRetentionDays);

              # Performance analytics settings - only if enabled and different from defaults
              COACHIQ_PERFORMANCE_ANALYTICS__ENABLE_TELEMETRY_COLLECTION = lib.mkIf (config.coachiq.settings.features.enablePerformanceAnalytics && !config.coachiq.settings.performanceAnalytics.enableTelemetryCollection) "false";
              COACHIQ_PERFORMANCE_ANALYTICS__ENABLE_RESOURCE_MONITORING = lib.mkIf (config.coachiq.settings.features.enablePerformanceAnalytics && !config.coachiq.settings.performanceAnalytics.enableResourceMonitoring) "false";
              COACHIQ_PERFORMANCE_ANALYTICS__TELEMETRY_COLLECTION_INTERVAL_SECONDS = lib.mkIf (config.coachiq.settings.features.enablePerformanceAnalytics && config.coachiq.settings.performanceAnalytics.telemetryCollectionIntervalSeconds != 5.0) (toString config.coachiq.settings.performanceAnalytics.telemetryCollectionIntervalSeconds);
              COACHIQ_PERFORMANCE_ANALYTICS__CPU_WARNING_THRESHOLD_PERCENT = lib.mkIf (config.coachiq.settings.features.enablePerformanceAnalytics && config.coachiq.settings.performanceAnalytics.cpuWarningThresholdPercent != 80.0) (toString config.coachiq.settings.performanceAnalytics.cpuWarningThresholdPercent);
              COACHIQ_PERFORMANCE_ANALYTICS__MEMORY_WARNING_THRESHOLD_PERCENT = lib.mkIf (config.coachiq.settings.features.enablePerformanceAnalytics && config.coachiq.settings.performanceAnalytics.memoryWarningThresholdPercent != 80.0) (toString config.coachiq.settings.performanceAnalytics.memoryWarningThresholdPercent);

              # Notification system settings - only if enabled and different from defaults
              COACHIQ_NOTIFICATIONS__ENABLED = lib.mkIf config.coachiq.settings.notifications.enabled "true";
              COACHIQ_NOTIFICATIONS__DEFAULT_TITLE = lib.mkIf (config.coachiq.settings.notifications.enabled && config.coachiq.settings.notifications.defaultTitle != "CoachIQ Notification") config.coachiq.settings.notifications.defaultTitle;
              COACHIQ_NOTIFICATIONS__TEMPLATE_PATH = lib.mkIf (config.coachiq.settings.notifications.enabled && config.coachiq.settings.notifications.templatePath != "templates/notifications/") config.coachiq.settings.notifications.templatePath;
              COACHIQ_NOTIFICATIONS__LOG_NOTIFICATIONS = lib.mkIf (config.coachiq.settings.notifications.enabled && !config.coachiq.settings.notifications.logNotifications) "false";

              # SMTP configuration - only if enabled
              COACHIQ_NOTIFICATIONS__SMTP__ENABLED = lib.mkIf config.coachiq.settings.notifications.smtp.enabled "true";
              COACHIQ_NOTIFICATIONS__SMTP__HOST = lib.mkIf (config.coachiq.settings.notifications.smtp.enabled && config.coachiq.settings.notifications.smtp.host != "localhost") config.coachiq.settings.notifications.smtp.host;
              COACHIQ_NOTIFICATIONS__SMTP__PORT = lib.mkIf (config.coachiq.settings.notifications.smtp.enabled && config.coachiq.settings.notifications.smtp.port != 587) (toString config.coachiq.settings.notifications.smtp.port);
              COACHIQ_NOTIFICATIONS__SMTP__USERNAME = lib.mkIf (config.coachiq.settings.notifications.smtp.enabled && config.coachiq.settings.notifications.smtp.username != "") config.coachiq.settings.notifications.smtp.username;
              COACHIQ_NOTIFICATIONS__SMTP__PASSWORD = lib.mkIf (config.coachiq.settings.notifications.smtp.enabled && config.coachiq.settings.notifications.smtp.password != "") config.coachiq.settings.notifications.smtp.password;
              COACHIQ_NOTIFICATIONS__SMTP__FROM_EMAIL = lib.mkIf (config.coachiq.settings.notifications.smtp.enabled && config.coachiq.settings.notifications.smtp.fromEmail != "noreply@coachiq.com") config.coachiq.settings.notifications.smtp.fromEmail;
              COACHIQ_NOTIFICATIONS__SMTP__FROM_NAME = lib.mkIf (config.coachiq.settings.notifications.smtp.enabled && config.coachiq.settings.notifications.smtp.fromName != "CoachIQ") config.coachiq.settings.notifications.smtp.fromName;
              COACHIQ_NOTIFICATIONS__SMTP__USE_TLS = lib.mkIf (config.coachiq.settings.notifications.smtp.enabled && !config.coachiq.settings.notifications.smtp.useTls) "false";
              COACHIQ_NOTIFICATIONS__SMTP__USE_SSL = lib.mkIf (config.coachiq.settings.notifications.smtp.enabled && config.coachiq.settings.notifications.smtp.useSsl) "true";
              COACHIQ_NOTIFICATIONS__SMTP__TIMEOUT = lib.mkIf (config.coachiq.settings.notifications.smtp.enabled && config.coachiq.settings.notifications.smtp.timeout != 30) (toString config.coachiq.settings.notifications.smtp.timeout);

              # Slack configuration - only if enabled
              COACHIQ_NOTIFICATIONS__SLACK__ENABLED = lib.mkIf config.coachiq.settings.notifications.slack.enabled "true";
              COACHIQ_NOTIFICATIONS__SLACK__WEBHOOK_URL = lib.mkIf (config.coachiq.settings.notifications.slack.enabled && config.coachiq.settings.notifications.slack.webhookUrl != "") config.coachiq.settings.notifications.slack.webhookUrl;

              # Discord configuration - only if enabled
              COACHIQ_NOTIFICATIONS__DISCORD__ENABLED = lib.mkIf config.coachiq.settings.notifications.discord.enabled "true";
              COACHIQ_NOTIFICATIONS__DISCORD__WEBHOOK_URL = lib.mkIf (config.coachiq.settings.notifications.discord.enabled && config.coachiq.settings.notifications.discord.webhookUrl != "") config.coachiq.settings.notifications.discord.webhookUrl;

              # Notification routing settings - only if different from defaults
              COACHIQ_NOTIFICATION_ROUTING__ENABLED = lib.mkIf (!config.coachiq.settings.notificationRouting.enabled) "false";
              COACHIQ_NOTIFICATION_ROUTING__QUIET_HOURS_ENABLED = lib.mkIf (!config.coachiq.settings.notificationRouting.quietHoursEnabled) "false";
              COACHIQ_NOTIFICATION_ROUTING__DEFAULT_QUIET_HOURS_START = lib.mkIf (config.coachiq.settings.notificationRouting.defaultQuietHoursStart != "22:00") config.coachiq.settings.notificationRouting.defaultQuietHoursStart;
              COACHIQ_NOTIFICATION_ROUTING__DEFAULT_QUIET_HOURS_END = lib.mkIf (config.coachiq.settings.notificationRouting.defaultQuietHoursEnd != "08:00") config.coachiq.settings.notificationRouting.defaultQuietHoursEnd;
              COACHIQ_NOTIFICATION_ROUTING__ESCALATION_ENABLED = lib.mkIf (!config.coachiq.settings.notificationRouting.escalationEnabled) "false";
              COACHIQ_NOTIFICATION_ROUTING__ESCALATION_DELAY_MINUTES = lib.mkIf (config.coachiq.settings.notificationRouting.escalationDelayMinutes != 15) (toString config.coachiq.settings.notificationRouting.escalationDelayMinutes);
              COACHIQ_NOTIFICATION_ROUTING__MAX_ROUTING_RULES = lib.mkIf (config.coachiq.settings.notificationRouting.maxRoutingRules != 100) (toString config.coachiq.settings.notificationRouting.maxRoutingRules);

              # Notification analytics settings - only if different from defaults
              COACHIQ_NOTIFICATION_ANALYTICS__ENABLED = lib.mkIf (!config.coachiq.settings.notificationAnalytics.enabled) "false";
              COACHIQ_NOTIFICATION_ANALYTICS__BUFFER_SIZE_LIMIT = lib.mkIf (config.coachiq.settings.notificationAnalytics.bufferSizeLimit != 100) (toString config.coachiq.settings.notificationAnalytics.bufferSizeLimit);
              COACHIQ_NOTIFICATION_ANALYTICS__BUFFER_FLUSH_INTERVAL = lib.mkIf (config.coachiq.settings.notificationAnalytics.bufferFlushInterval != 30) (toString config.coachiq.settings.notificationAnalytics.bufferFlushInterval);
              COACHIQ_NOTIFICATION_ANALYTICS__METRIC_CACHE_TTL = lib.mkIf (config.coachiq.settings.notificationAnalytics.metricCacheTtl != 300) (toString config.coachiq.settings.notificationAnalytics.metricCacheTtl);
              COACHIQ_NOTIFICATION_ANALYTICS__AGGREGATION_INTERVAL = lib.mkIf (config.coachiq.settings.notificationAnalytics.aggregationInterval != 3600) (toString config.coachiq.settings.notificationAnalytics.aggregationInterval);
              COACHIQ_NOTIFICATION_ANALYTICS__HEALTH_CHECK_INTERVAL = lib.mkIf (config.coachiq.settings.notificationAnalytics.healthCheckInterval != 300) (toString config.coachiq.settings.notificationAnalytics.healthCheckInterval);
              COACHIQ_NOTIFICATION_ANALYTICS__RETENTION_DAYS = lib.mkIf (config.coachiq.settings.notificationAnalytics.retentionDays != 90) (toString config.coachiq.settings.notificationAnalytics.retentionDays);
              COACHIQ_NOTIFICATION_ANALYTICS__ENABLE_REAL_TIME_METRICS = lib.mkIf (!config.coachiq.settings.notificationAnalytics.enableRealTimeMetrics) "false";
              COACHIQ_NOTIFICATION_ANALYTICS__ENABLE_ERROR_ANALYSIS = lib.mkIf (!config.coachiq.settings.notificationAnalytics.enableErrorAnalysis) "false";

              # Email template settings - only if different from defaults
              COACHIQ_EMAIL_TEMPLATES__TEMPLATE_DIR = lib.mkIf (config.coachiq.settings.emailTemplates.templateDir != "backend/templates/email") config.coachiq.settings.emailTemplates.templateDir;
              COACHIQ_EMAIL_TEMPLATES__CACHE_TTL_MINUTES = lib.mkIf (config.coachiq.settings.emailTemplates.cacheTtlMinutes != 60) (toString config.coachiq.settings.emailTemplates.cacheTtlMinutes);
              COACHIQ_EMAIL_TEMPLATES__ENABLE_CACHING = lib.mkIf (!config.coachiq.settings.emailTemplates.enableCaching) "false";
              COACHIQ_EMAIL_TEMPLATES__ENABLE_VALIDATION = lib.mkIf (!config.coachiq.settings.emailTemplates.enableValidation) "false";
              COACHIQ_EMAIL_TEMPLATES__ENABLE_SANDBOX = lib.mkIf (!config.coachiq.settings.emailTemplates.enableSandbox) "false";
              COACHIQ_EMAIL_TEMPLATES__DEFAULT_LANGUAGE = lib.mkIf (config.coachiq.settings.emailTemplates.defaultLanguage != "en") config.coachiq.settings.emailTemplates.defaultLanguage;
              COACHIQ_EMAIL_TEMPLATES__SUPPORTED_LANGUAGES = lib.mkIf (config.coachiq.settings.emailTemplates.supportedLanguages != ["en" "es" "fr"]) (lib.concatStringsSep "," config.coachiq.settings.emailTemplates.supportedLanguages);
              COACHIQ_EMAIL_TEMPLATES__ENABLE_AB_TESTING = lib.mkIf config.coachiq.settings.emailTemplates.enableAbTesting "true";

              # Notification performance settings - only if different from defaults
              COACHIQ_NOTIFICATION_PERFORMANCE__CONNECTION_POOL_SIZE = lib.mkIf (config.coachiq.settings.notificationPerformance.connectionPoolSize != 10) (toString config.coachiq.settings.notificationPerformance.connectionPoolSize);
              COACHIQ_NOTIFICATION_PERFORMANCE__CIRCUIT_BREAKER_ENABLED = lib.mkIf (!config.coachiq.settings.notificationPerformance.circuitBreakerEnabled) "false";
              COACHIQ_NOTIFICATION_PERFORMANCE__CIRCUIT_BREAKER_THRESHOLD = lib.mkIf (config.coachiq.settings.notificationPerformance.circuitBreakerThreshold != 5) (toString config.coachiq.settings.notificationPerformance.circuitBreakerThreshold);
              COACHIQ_NOTIFICATION_PERFORMANCE__CIRCUIT_BREAKER_TIMEOUT = lib.mkIf (config.coachiq.settings.notificationPerformance.circuitBreakerTimeout != 60) (toString config.coachiq.settings.notificationPerformance.circuitBreakerTimeout);
              COACHIQ_NOTIFICATION_PERFORMANCE__BATCH_SIZE = lib.mkIf (config.coachiq.settings.notificationPerformance.batchSize != 50) (toString config.coachiq.settings.notificationPerformance.batchSize);
              COACHIQ_NOTIFICATION_PERFORMANCE__BATCH_TIMEOUT = lib.mkIf (config.coachiq.settings.notificationPerformance.batchTimeout != 5) (toString config.coachiq.settings.notificationPerformance.batchTimeout);
              COACHIQ_NOTIFICATION_PERFORMANCE__ENABLE_CONNECTION_POOLING = lib.mkIf (!config.coachiq.settings.notificationPerformance.enableConnectionPooling) "false";
              COACHIQ_NOTIFICATION_PERFORMANCE__ENABLE_RETRY_BACKOFF = lib.mkIf (!config.coachiq.settings.notificationPerformance.enableRetryBackoff) "false";
              COACHIQ_NOTIFICATION_PERFORMANCE__MAX_RETRY_DELAY = lib.mkIf (config.coachiq.settings.notificationPerformance.maxRetryDelay != 300) (toString config.coachiq.settings.notificationPerformance.maxRetryDelay);

              # Notification batching settings - only if different from defaults
              COACHIQ_NOTIFICATION_BATCHING__ENABLED = lib.mkIf (!config.coachiq.settings.notificationBatching.enabled) "false";
              COACHIQ_NOTIFICATION_BATCHING__MAX_BATCH_SIZE = lib.mkIf (config.coachiq.settings.notificationBatching.maxBatchSize != 100) (toString config.coachiq.settings.notificationBatching.maxBatchSize);
              COACHIQ_NOTIFICATION_BATCHING__BATCH_TIMEOUT_SECONDS = lib.mkIf (config.coachiq.settings.notificationBatching.batchTimeoutSeconds != 10) (toString config.coachiq.settings.notificationBatching.batchTimeoutSeconds);
              COACHIQ_NOTIFICATION_BATCHING__MAX_RETRY_ATTEMPTS = lib.mkIf (config.coachiq.settings.notificationBatching.maxRetryAttempts != 3) (toString config.coachiq.settings.notificationBatching.maxRetryAttempts);
              COACHIQ_NOTIFICATION_BATCHING__ENABLE_SMART_BATCHING = lib.mkIf (!config.coachiq.settings.notificationBatching.enableSmartBatching) "false";
              COACHIQ_NOTIFICATION_BATCHING__PRIORITY_THRESHOLD = lib.mkIf (config.coachiq.settings.notificationBatching.priorityThreshold != "high") config.coachiq.settings.notificationBatching.priorityThreshold;

              # Notification rate limiting settings - only if different from defaults
              COACHIQ_NOTIFICATION_RATE_LIMITING__ENABLED = lib.mkIf (!config.coachiq.settings.notificationRateLimiting.enabled) "false";
              COACHIQ_NOTIFICATION_RATE_LIMITING__DEFAULT_RATE_LIMIT = lib.mkIf (config.coachiq.settings.notificationRateLimiting.defaultRateLimit != 100) (toString config.coachiq.settings.notificationRateLimiting.defaultRateLimit);
              COACHIQ_NOTIFICATION_RATE_LIMITING__DEFAULT_WINDOW_SECONDS = lib.mkIf (config.coachiq.settings.notificationRateLimiting.defaultWindowSeconds != 3600) (toString config.coachiq.settings.notificationRateLimiting.defaultWindowSeconds);
              COACHIQ_NOTIFICATION_RATE_LIMITING__PER_CHANNEL_LIMITS = lib.mkIf (config.coachiq.settings.notificationRateLimiting.perChannelLimits != {email = 50; slack = 100; webhook = 200;}) (builtins.toJSON config.coachiq.settings.notificationRateLimiting.perChannelLimits);
              COACHIQ_NOTIFICATION_RATE_LIMITING__ENABLE_BURST_ALLOWANCE = lib.mkIf (!config.coachiq.settings.notificationRateLimiting.enableBurstAllowance) "false";
              COACHIQ_NOTIFICATION_RATE_LIMITING__BURST_MULTIPLIER = lib.mkIf (config.coachiq.settings.notificationRateLimiting.burstMultiplier != 1.5) (toString config.coachiq.settings.notificationRateLimiting.burstMultiplier);

              # Notification queue settings - only if different from defaults
              COACHIQ_NOTIFICATION_QUEUE__MAX_QUEUE_SIZE = lib.mkIf (config.coachiq.settings.notificationQueue.maxQueueSize != 10000) (toString config.coachiq.settings.notificationQueue.maxQueueSize);
              COACHIQ_NOTIFICATION_QUEUE__WORKER_COUNT = lib.mkIf (config.coachiq.settings.notificationQueue.workerCount != 4) (toString config.coachiq.settings.notificationQueue.workerCount);
              COACHIQ_NOTIFICATION_QUEUE__PRIORITY_LEVELS = lib.mkIf (config.coachiq.settings.notificationQueue.priorityLevels != ["low" "medium" "high" "critical"]) (lib.concatStringsSep "," config.coachiq.settings.notificationQueue.priorityLevels);
              COACHIQ_NOTIFICATION_QUEUE__ENABLE_PERSISTENCE = lib.mkIf (!config.coachiq.settings.notificationQueue.enablePersistence) "false";
              COACHIQ_NOTIFICATION_QUEUE__PERSISTENCE_INTERVAL = lib.mkIf (config.coachiq.settings.notificationQueue.persistenceInterval != 60) (toString config.coachiq.settings.notificationQueue.persistenceInterval);
              COACHIQ_NOTIFICATION_QUEUE__DEAD_LETTER_ENABLED = lib.mkIf (!config.coachiq.settings.notificationQueue.deadLetterEnabled) "false";
              COACHIQ_NOTIFICATION_QUEUE__DEAD_LETTER_THRESHOLD = lib.mkIf (config.coachiq.settings.notificationQueue.deadLetterThreshold != 5) (toString config.coachiq.settings.notificationQueue.deadLetterThreshold);

              # Authentication settings - only if enabled
              COACHIQ_AUTH__ENABLED = lib.mkIf config.coachiq.settings.authentication.enabled "true";
              COACHIQ_AUTH__SECRET_KEY = lib.mkIf (config.coachiq.settings.authentication.enabled && config.coachiq.settings.authentication.secretKey != "") config.coachiq.settings.authentication.secretKey;
              COACHIQ_AUTH__JWT_ALGORITHM = lib.mkIf (config.coachiq.settings.authentication.enabled && config.coachiq.settings.authentication.jwtAlgorithm != "HS256") config.coachiq.settings.authentication.jwtAlgorithm;
              COACHIQ_AUTH__JWT_EXPIRE_MINUTES = lib.mkIf (config.coachiq.settings.authentication.enabled && config.coachiq.settings.authentication.jwtExpireMinutes != 30) (toString config.coachiq.settings.authentication.jwtExpireMinutes);
              COACHIQ_AUTH__BASE_URL = lib.mkIf (config.coachiq.settings.authentication.enabled && config.coachiq.settings.authentication.baseUrl != "http://localhost:8000") config.coachiq.settings.authentication.baseUrl;

              # Single-user mode settings
              COACHIQ_AUTH__ADMIN_USERNAME = lib.mkIf (config.coachiq.settings.authentication.enabled && config.coachiq.settings.authentication.adminUsername != "admin") config.coachiq.settings.authentication.adminUsername;
              COACHIQ_AUTH__ADMIN_PASSWORD = lib.mkIf (config.coachiq.settings.authentication.enabled && config.coachiq.settings.authentication.adminPassword != "") config.coachiq.settings.authentication.adminPassword;

              # Multi-user mode settings
              COACHIQ_AUTH__ADMIN_EMAIL = lib.mkIf (config.coachiq.settings.authentication.enabled && config.coachiq.settings.authentication.adminEmail != "") config.coachiq.settings.authentication.adminEmail;
              COACHIQ_AUTH__ENABLE_MAGIC_LINKS = lib.mkIf (config.coachiq.settings.authentication.enabled && !config.coachiq.settings.authentication.enableMagicLinks) "false";
              COACHIQ_AUTH__MAGIC_LINK_EXPIRE_MINUTES = lib.mkIf (config.coachiq.settings.authentication.enabled && config.coachiq.settings.authentication.magicLinkExpireMinutes != 15) (toString config.coachiq.settings.authentication.magicLinkExpireMinutes);

              # OAuth settings
              COACHIQ_AUTH__ENABLE_OAUTH = lib.mkIf (config.coachiq.settings.authentication.enabled && config.coachiq.settings.authentication.enableOauth) "true";
              COACHIQ_AUTH__OAUTH_GITHUB_CLIENT_ID = lib.mkIf (config.coachiq.settings.authentication.enabled && config.coachiq.settings.authentication.oauthGithubClientId != "") config.coachiq.settings.authentication.oauthGithubClientId;
              COACHIQ_AUTH__OAUTH_GITHUB_CLIENT_SECRET = lib.mkIf (config.coachiq.settings.authentication.enabled && config.coachiq.settings.authentication.oauthGithubClientSecret != "") config.coachiq.settings.authentication.oauthGithubClientSecret;
              COACHIQ_AUTH__OAUTH_GOOGLE_CLIENT_ID = lib.mkIf (config.coachiq.settings.authentication.enabled && config.coachiq.settings.authentication.oauthGoogleClientId != "") config.coachiq.settings.authentication.oauthGoogleClientId;
              COACHIQ_AUTH__OAUTH_GOOGLE_CLIENT_SECRET = lib.mkIf (config.coachiq.settings.authentication.enabled && config.coachiq.settings.authentication.oauthGoogleClientSecret != "") config.coachiq.settings.authentication.oauthGoogleClientSecret;
              COACHIQ_AUTH__OAUTH_MICROSOFT_CLIENT_ID = lib.mkIf (config.coachiq.settings.authentication.enabled && config.coachiq.settings.authentication.oauthMicrosoftClientId != "") config.coachiq.settings.authentication.oauthMicrosoftClientId;
              COACHIQ_AUTH__OAUTH_MICROSOFT_CLIENT_SECRET = lib.mkIf (config.coachiq.settings.authentication.enabled && config.coachiq.settings.authentication.oauthMicrosoftClientSecret != "") config.coachiq.settings.authentication.oauthMicrosoftClientSecret;

              # Session and security settings
              COACHIQ_AUTH__SESSION_EXPIRE_HOURS = lib.mkIf (config.coachiq.settings.authentication.enabled && config.coachiq.settings.authentication.sessionExpireHours != 24) (toString config.coachiq.settings.authentication.sessionExpireHours);
              COACHIQ_AUTH__MAX_SESSIONS_PER_USER = lib.mkIf (config.coachiq.settings.authentication.enabled && config.coachiq.settings.authentication.maxSessionsPerUser != 5) (toString config.coachiq.settings.authentication.maxSessionsPerUser);
              COACHIQ_AUTH__REQUIRE_SECURE_COOKIES = lib.mkIf (config.coachiq.settings.authentication.enabled && !config.coachiq.settings.authentication.requireSecureCookies) "false";
              COACHIQ_AUTH__RATE_LIMIT_AUTH_ATTEMPTS = lib.mkIf (config.coachiq.settings.authentication.enabled && config.coachiq.settings.authentication.rateLimitAuthAttempts != 5) (toString config.coachiq.settings.authentication.rateLimitAuthAttempts);
              COACHIQ_AUTH__RATE_LIMIT_WINDOW_MINUTES = lib.mkIf (config.coachiq.settings.authentication.enabled && config.coachiq.settings.authentication.rateLimitWindowMinutes != 15) (toString config.coachiq.settings.authentication.rateLimitWindowMinutes);

              # Multi-Factor Authentication settings - only if enabled
              COACHIQ_MFA__ENABLED = lib.mkIf config.coachiq.settings.multiFactorAuthentication.enabled "true";
              COACHIQ_MFA__ENABLE_TOTP = lib.mkIf (config.coachiq.settings.multiFactorAuthentication.enabled && !config.coachiq.settings.multiFactorAuthentication.enableTotp) "false";
              COACHIQ_MFA__ENABLE_BACKUP_CODES = lib.mkIf (config.coachiq.settings.multiFactorAuthentication.enabled && !config.coachiq.settings.multiFactorAuthentication.enableBackupCodes) "false";
              COACHIQ_MFA__ENABLE_RECOVERY_CODES = lib.mkIf (config.coachiq.settings.multiFactorAuthentication.enabled && !config.coachiq.settings.multiFactorAuthentication.enableRecoveryCodes) "false";
              COACHIQ_MFA__TOTP_ISSUER = lib.mkIf (config.coachiq.settings.multiFactorAuthentication.enabled && config.coachiq.settings.multiFactorAuthentication.totpIssuer != "CoachIQ") config.coachiq.settings.multiFactorAuthentication.totpIssuer;
              COACHIQ_MFA__TOTP_DIGITS = lib.mkIf (config.coachiq.settings.multiFactorAuthentication.enabled && config.coachiq.settings.multiFactorAuthentication.totpDigits != 6) (toString config.coachiq.settings.multiFactorAuthentication.totpDigits);
              COACHIQ_MFA__TOTP_WINDOW = lib.mkIf (config.coachiq.settings.multiFactorAuthentication.enabled && config.coachiq.settings.multiFactorAuthentication.totpWindow != 1) (toString config.coachiq.settings.multiFactorAuthentication.totpWindow);
              COACHIQ_MFA__BACKUP_CODES_COUNT = lib.mkIf (config.coachiq.settings.multiFactorAuthentication.enabled && config.coachiq.settings.multiFactorAuthentication.backupCodesCount != 10) (toString config.coachiq.settings.multiFactorAuthentication.backupCodesCount);
              COACHIQ_MFA__BACKUP_CODE_LENGTH = lib.mkIf (config.coachiq.settings.multiFactorAuthentication.enabled && config.coachiq.settings.multiFactorAuthentication.backupCodeLength != 8) (toString config.coachiq.settings.multiFactorAuthentication.backupCodeLength);
              COACHIQ_MFA__REQUIRE_MFA_FOR_ADMIN = lib.mkIf (config.coachiq.settings.multiFactorAuthentication.enabled && config.coachiq.settings.multiFactorAuthentication.requireMfaForAdmin) "true";
              COACHIQ_MFA__ALLOW_MFA_BYPASS = lib.mkIf (config.coachiq.settings.multiFactorAuthentication.enabled && !config.coachiq.settings.multiFactorAuthentication.allowMfaBypass) "false";
              COACHIQ_MFA__MFA_SETUP_GRACE_PERIOD_HOURS = lib.mkIf (config.coachiq.settings.multiFactorAuthentication.enabled && config.coachiq.settings.multiFactorAuthentication.mfaSetupGracePeriodHours != 24) (toString config.coachiq.settings.multiFactorAuthentication.mfaSetupGracePeriodHours);
              COACHIQ_MFA__BACKUP_CODE_REGENERATION_THRESHOLD = lib.mkIf (config.coachiq.settings.multiFactorAuthentication.enabled && config.coachiq.settings.multiFactorAuthentication.backupCodeRegenerationThreshold != 3) (toString config.coachiq.settings.multiFactorAuthentication.backupCodeRegenerationThreshold);

              # Optional paths - only if provided
              COACHIQ_RVC_SPEC_PATH = lib.mkIf (config.coachiq.settings.rvcSpecPath != null) config.coachiq.settings.rvcSpecPath;
              COACHIQ_RVC_COACH_MAPPING_PATH = lib.mkIf (config.coachiq.settings.rvcCoachMappingPath != null) config.coachiq.settings.rvcCoachMappingPath;
              COACHIQ_RVC__COACH_MODEL = lib.mkIf (config.coachiq.settings.rvcCoachModel != null) config.coachiq.settings.rvcCoachModel;

              # GitHub update repo - only if provided
              COACHIQ_GITHUB_UPDATE_REPO = lib.mkIf (config.coachiq.settings.githubUpdateRepo != null) config.coachiq.settings.githubUpdateRepo;

              # New feature flags - only if enabled
              COACHIQ_FEATURES__ENABLE_CANBUS_DECODER_V2 = lib.mkIf config.coachiq.settings.features.enableCanbusDeoderV2 "true";
              COACHIQ_FEATURES__ENABLE_DASHBOARD_AGGREGATION = lib.mkIf (!config.coachiq.settings.features.enableDashboardAggregation) "false";
              COACHIQ_FEATURES__ENABLE_SYSTEM_ANALYTICS = lib.mkIf (!config.coachiq.settings.features.enableSystemAnalytics) "false";
              COACHIQ_FEATURES__ENABLE_ACTIVITY_TRACKING = lib.mkIf (!config.coachiq.settings.features.enableActivityTracking) "false";
              COACHIQ_FEATURES__ENABLE_ANALYTICS_DASHBOARD = lib.mkIf (!config.coachiq.settings.features.enableAnalyticsDashboard) "false";
              COACHIQ_FEATURES__ENABLE_PREDICTIVE_MAINTENANCE = lib.mkIf (!config.coachiq.settings.features.enablePredictiveMaintenance) "false";
              COACHIQ_FEATURES__ENABLE_LOG_HISTORY = lib.mkIf (!config.coachiq.settings.features.enableLogHistory) "false";
              COACHIQ_FEATURES__ENABLE_LOG_STREAMING = lib.mkIf (!config.coachiq.settings.features.enableLogStreaming) "false";
              COACHIQ_FEATURES__ENABLE_GITHUB_UPDATE_CHECKER = lib.mkIf config.coachiq.settings.features.enableGithubUpdateChecker "true";

              # Domain API v2 features - only if different from defaults
              COACHIQ_FEATURES__ENABLE_DOMAIN_API_V2 = lib.mkIf (!config.coachiq.settings.features.enableDomainApiV2) "false";
              COACHIQ_FEATURES__ENABLE_ENTITIES_API_V2 = lib.mkIf (!config.coachiq.settings.features.enableEntitiesApiV2) "false";
              COACHIQ_FEATURES__ENABLE_DIAGNOSTICS_API_V2 = lib.mkIf config.coachiq.settings.features.enableDiagnosticsApiV2 "true";
              COACHIQ_FEATURES__ENABLE_ANALYTICS_API_V2 = lib.mkIf config.coachiq.settings.features.enableAnalyticsApiV2 "true";
              COACHIQ_FEATURES__ENABLE_NETWORKS_API_V2 = lib.mkIf config.coachiq.settings.features.enableNetworksApiV2 "true";
              COACHIQ_FEATURES__ENABLE_SYSTEM_API_V2 = lib.mkIf config.coachiq.settings.features.enableSystemApiV2 "true";

              # CAN Bus Decoder v2 settings - only if enabled and different from defaults
              COACHIQ_CANBUS_DECODER_V2__ENABLED = lib.mkIf config.coachiq.settings.features.enableCanbusDeoderV2 "true";
              COACHIQ_CANBUS_DECODER_V2__ENABLE_SAFETY_STATE_ENGINE = lib.mkIf (config.coachiq.settings.features.enableCanbusDeoderV2 && !config.coachiq.settings.canbusDecoderV2.enableSafetyStateEngine) "false";
              COACHIQ_CANBUS_DECODER_V2__ENABLE_PROTOCOL_ROUTER = lib.mkIf (config.coachiq.settings.features.enableCanbusDeoderV2 && !config.coachiq.settings.canbusDecoderV2.enableProtocolRouter) "false";
              COACHIQ_CANBUS_DECODER_V2__ENABLE_CONFIGURATION_SERVICE = lib.mkIf (config.coachiq.settings.features.enableCanbusDeoderV2 && !config.coachiq.settings.canbusDecoderV2.enableConfigurationService) "false";
              COACHIQ_CANBUS_DECODER_V2__ENABLE_BAM_OPTIMIZATION = lib.mkIf (config.coachiq.settings.features.enableCanbusDeoderV2 && !config.coachiq.settings.canbusDecoderV2.enableBamOptimization) "false";
              COACHIQ_CANBUS_DECODER_V2__ENABLE_ADAPTIVE_SECURITY = lib.mkIf (config.coachiq.settings.features.enableCanbusDeoderV2 && config.coachiq.settings.canbusDecoderV2.enableAdaptiveSecurity) "true";
              COACHIQ_CANBUS_DECODER_V2__ENABLE_PERFORMANCE_MONITORING = lib.mkIf (config.coachiq.settings.features.enableCanbusDeoderV2 && !config.coachiq.settings.canbusDecoderV2.enablePerformanceMonitoring) "false";
              COACHIQ_CANBUS_DECODER_V2__SAFETY_STATE_TIMEOUT_SECONDS = lib.mkIf (config.coachiq.settings.features.enableCanbusDeoderV2 && config.coachiq.settings.canbusDecoderV2.safetyStateTimeoutSeconds != 30.0) (toString config.coachiq.settings.canbusDecoderV2.safetyStateTimeoutSeconds);
              COACHIQ_CANBUS_DECODER_V2__MOVING_SPEED_THRESHOLD_MPH = lib.mkIf (config.coachiq.settings.features.enableCanbusDeoderV2 && config.coachiq.settings.canbusDecoderV2.movingSpeedThresholdMph != 0.5) (toString config.coachiq.settings.canbusDecoderV2.movingSpeedThresholdMph);
              COACHIQ_CANBUS_DECODER_V2__CONFIGURATION_CACHE_TTL_SECONDS = lib.mkIf (config.coachiq.settings.features.enableCanbusDeoderV2 && config.coachiq.settings.canbusDecoderV2.configurationCacheTtlSeconds != 300) (toString config.coachiq.settings.canbusDecoderV2.configurationCacheTtlSeconds);
              COACHIQ_CANBUS_DECODER_V2__MAX_CONCURRENT_BAM_SESSIONS = lib.mkIf (config.coachiq.settings.features.enableCanbusDeoderV2 && config.coachiq.settings.canbusDecoderV2.maxConcurrentBamSessions != 100) (toString config.coachiq.settings.canbusDecoderV2.maxConcurrentBamSessions);
              COACHIQ_CANBUS_DECODER_V2__PERFORMANCE_MONITORING_INTERVAL_SECONDS = lib.mkIf (config.coachiq.settings.features.enableCanbusDeoderV2 && config.coachiq.settings.canbusDecoderV2.performanceMonitoringIntervalSeconds != 10.0) (toString config.coachiq.settings.canbusDecoderV2.performanceMonitoringIntervalSeconds);

              # Analytics dashboard settings - only if different from defaults
              COACHIQ_ANALYTICS__ENABLED = lib.mkIf (!config.coachiq.settings.analyticsDashboard.enabled) "false";
              COACHIQ_ANALYTICS__MEMORY_RETENTION_HOURS = lib.mkIf (config.coachiq.settings.analyticsDashboard.memoryRetentionHours != 2) (toString config.coachiq.settings.analyticsDashboard.memoryRetentionHours);
              COACHIQ_ANALYTICS__INSIGHT_GENERATION_INTERVAL_SECONDS = lib.mkIf (config.coachiq.settings.analyticsDashboard.insightGenerationIntervalSeconds != 900) (toString config.coachiq.settings.analyticsDashboard.insightGenerationIntervalSeconds);
              COACHIQ_ANALYTICS__PATTERN_ANALYSIS_INTERVAL_SECONDS = lib.mkIf (config.coachiq.settings.analyticsDashboard.patternAnalysisIntervalSeconds != 1800) (toString config.coachiq.settings.analyticsDashboard.patternAnalysisIntervalSeconds);
              COACHIQ_ANALYTICS__MAX_MEMORY_INSIGHTS = lib.mkIf (config.coachiq.settings.analyticsDashboard.maxMemoryInsights != 100) (toString config.coachiq.settings.analyticsDashboard.maxMemoryInsights);
              COACHIQ_ANALYTICS__MAX_MEMORY_PATTERNS = lib.mkIf (config.coachiq.settings.analyticsDashboard.maxMemoryPatterns != 50) (toString config.coachiq.settings.analyticsDashboard.maxMemoryPatterns);
              COACHIQ_ANALYTICS__PERSISTENCE_RETENTION_DAYS = lib.mkIf (config.coachiq.settings.analyticsDashboard.persistenceRetentionDays != 30) (toString config.coachiq.settings.analyticsDashboard.persistenceRetentionDays);
              COACHIQ_ANALYTICS__ENABLE_BACKGROUND_PERSISTENCE = lib.mkIf (!config.coachiq.settings.analyticsDashboard.enableBackgroundPersistence) "false";
              COACHIQ_ANALYTICS__SQLITE_BATCH_SIZE = lib.mkIf (config.coachiq.settings.analyticsDashboard.sqliteBatchSize != 100) (toString config.coachiq.settings.analyticsDashboard.sqliteBatchSize);
              COACHIQ_ANALYTICS__DB_PATH = lib.mkIf (config.coachiq.settings.analyticsDashboard.dbPath != "data/analytics.db") config.coachiq.settings.analyticsDashboard.dbPath;
              COACHIQ_ANALYTICS__ENABLE_BACKGROUND_CLEANUP = lib.mkIf (!config.coachiq.settings.analyticsDashboard.enableBackgroundCleanup) "false";
              COACHIQ_ANALYTICS__CLEANUP_INTERVAL_SECONDS = lib.mkIf (config.coachiq.settings.analyticsDashboard.cleanupIntervalSeconds != 3600) (toString config.coachiq.settings.analyticsDashboard.cleanupIntervalSeconds);

              # Legacy compatibility - only if using non-default values
              COACHIQ_HOST = lib.mkIf (config.coachiq.settings.host != "0.0.0.0") config.coachiq.settings.host;
              COACHIQ_PORT = lib.mkIf (config.coachiq.settings.port != 8000) (toString config.coachiq.settings.port);
            });
          };
        };
      };
    };
}
