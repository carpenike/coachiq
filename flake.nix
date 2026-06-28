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
#   imports = [ inputs.coachiq.nixosModules.default ];
#   # Then configure it:
#   services.coachiq = { ... };
#
#   # Or to reference CLI apps:
#   nix run inputs.coachiq#check
#
# See docs/nixos-integration.md for more details

{
  description = "CoachIQ Python package and devShells";

  inputs = {
    nixpkgs.url     = "github:NixOS/nixpkgs/nixos-25.11";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils, ... }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
        python = pkgs.python312.override {
          packageOverrides = pyFinal: pyPrev: {
            "paho-mqtt" = pyPrev."paho-mqtt".overridePythonAttrs (oldAttrs: {
              doCheck = false;
            });
          };
        };
        pythonPackages = python.pkgs;
        nodejs = pkgs.nodejs_22;

        # Create Python environment with all dependencies for scripts
        pythonWithDeps = python.withPackages (ps: [
          ps.coloredlogs
          ps.fastapi
          ps.httptools
          ps.httpx
          ps.langchain-community
          ps.langchain-core
          ps."prometheus-client"
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
          ps.greenlet
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

        packageSet = pkgs.callPackage ./nix/package.nix {
          inherit python pythonPackages nodejs version;
          src = self;
          frontendSrc = ./frontend;
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
            pythonPackages."prometheus-client"
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
            pythonPackages.greenlet
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
            nodejs

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
            pythonPackages.sqlalchemy
            pythonPackages.greenlet
            pythonPackages.aiosqlite
            pythonPackages.asyncpg
            pythonPackages.alembic
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
            nodejs
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
              runtimeInputs = [ pkgs.poetry python ];
              text = ''
                export SKIP=djlint
                poetry env use ${python}/bin/python
                poetry install --no-root --with dev
                poetry run pre-commit run
              '';
            };
          }) // {
            meta = {
              description = "Run pre-commit checks on staged files (developer workflow)";
              maintainers = [ "carpenike" ];
              license = pkgs.lib.licenses.asl20;
            };
          };

          test = (flake-utils.lib.mkApp {
            drv = pkgs.writeShellApplication {
              name = "test";
              runtimeInputs = [ pkgs.poetry python ];
              text = ''
                poetry env use ${python}/bin/python
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

          guardrail-coverage = (flake-utils.lib.mkApp {
            drv = pkgs.writeShellApplication {
              name = "guardrail-coverage";
              runtimeInputs = [ pkgs.poetry python ];
              text = ''
                export LD_LIBRARY_PATH=${pkgs.zlib}/lib:${pkgs.stdenv.cc.cc.lib}/lib''${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}
                poetry env use ${python}/bin/python
                poetry install --no-root
                poetry run pytest -m "can or auth or safety or websocket"
                poetry run python scripts/check_module_coverage.py
              '';
            };
          }) // {
            meta = {
              description = "Run guardrail tests and per-module coverage ratchet";
              maintainers = [ "carpenike" ];
              license = pkgs.lib.licenses.asl20;
            };
          };

          rvc-spec-validation = (flake-utils.lib.mkApp {
            drv = pkgs.writeShellApplication {
              name = "rvc-spec-validation";
              runtimeInputs = [ pkgs.poetry python ];
              text = ''
                poetry env use ${python}/bin/python
                poetry install --no-root
                poetry run python scripts/validate_rvc_spec.py
              '';
            };
          }) // {
            meta = {
              description = "Validate rvc.json structure and live-corpus decode sanity";
              maintainers = [ "carpenike" ];
              license = pkgs.lib.licenses.asl20;
            };
          };

          lint = (flake-utils.lib.mkApp {
            drv = pkgs.writeShellApplication {
              name = "lint";
              runtimeInputs = [ pkgs.poetry python ];
              text = ''
                # Run all checks on all files (like CI but local)
                export SKIP=djlint
                poetry env use ${python}/bin/python
                poetry install --no-root --with dev
                poetry run pre-commit run --all-files
              '';
            };
          }) // {
            meta = {
              description = "Run all quality checks on all files (local CI simulation)";
              maintainers = [ "carpenike" ];
              license = pkgs.lib.licenses.asl20;
            };
          };

          format = (flake-utils.lib.mkApp {
            drv = pkgs.writeShellApplication {
              name = "format";
              runtimeInputs = [ pkgs.poetry python ];
              text = ''
                # Backend formatting
                poetry env use ${python}/bin/python
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
              runtimeInputs = [ nodejs ];
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
              runtimeInputs = [ pkgs.poetry python nodejs pkgs.jq pkgs.git ];
              text = ''
                set -e

                # Install dependencies
                poetry env use ${python}/bin/python
                poetry install --no-root --with dev
                poetry check --lock --no-interaction

                # Frontend deps must be installed before quality checks
                if [ -d "frontend" ]; then
                  echo "🔍 Installing frontend dependencies..."
                  cd frontend
                  npm ci
                  cd ..
                fi

                # Run the intelligent diff-aware quality gate
                ./scripts/ci-quality-gate.sh
              '';
            };
          }) // {
            meta = {
              description = "Run the intelligent CI quality gate (diff-aware checks)";
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
        } // pkgs.lib.optionalAttrs pkgs.stdenv.isLinux {
          module = import ./nix/test-module.nix {
            inherit nixpkgs system;
            module = self.nixosModules.default;
            package = self.packages.${system}.coachiq;
          };
        };
      in {
        packages = {
          coachiq = packageSet.coachiq;
          default = packageSet.coachiq;
          frontend = packageSet.frontend;
        };

        devShells = {
          default = devShell;
          ci      = ciShell;
        };

        inherit apps checks;
      }
    ) //
    {
      nixosModules.default = import ./nix/module.nix { inherit self; };

      overlays.default = final: _prev: {
        coachiq = self.packages.${final.system}.coachiq;
      };
    };
}
