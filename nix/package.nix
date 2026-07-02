# nix/package.nix
#
# CoachIQ package definitions extracted mechanically from flake.nix.
# Keep behavior stable: no build-identity inputs, no option changes.

{ pkgs
, python
, pythonPackages
, nodejs
, version
, src
, frontendSrc
}:

{
  coachiq = pythonPackages.buildPythonPackage {
    pname = "coachiq";
    inherit version;
    src      = src;
    format   = "pyproject";

    nativeBuildInputs = with pythonPackages; [ poetry-core ] ++ [ pkgs.makeWrapper ];
    propagatedBuildInputs = [
      pythonPackages.coloredlogs
      pythonPackages.fastapi
      pythonPackages.httptools
      pythonPackages.httpx
      pythonPackages.langchain-community
      pythonPackages.langchain-core
      pythonPackages."prometheus-client"
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
      pythonPackages.greenlet
      pythonPackages.aiosqlite
      pythonPackages.aiofiles
      pythonPackages.asyncpg
      pythonPackages.alembic
      # Router sidecar Starlink gRPC client
      pythonPackages.grpcio
      pythonPackages."grpcio-reflection"
      pythonPackages.protobuf
      # Notification system dependencies
      pythonPackages.apprise
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
      # Knowledge subsystem vector store
      pythonPackages."sqlite-vec"
    ] ++ pkgs.lib.optionals (pkgs.stdenv.isLinux || pkgs.stdenv.isDarwin) [
      pythonPackages.uvloop   # Uvicorn standard extra (conditional)
    ] ++ pkgs.lib.optionals pkgs.stdenv.isLinux [
      pythonPackages.pyroute2
      # CAN protocol handling (Linux only due to crccheck platform constraints)
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
      cp ${./health-check.sh} $out/share/coachiq/nix/health-check.sh
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

  frontend = pkgs.buildNpmPackage {
    pname = "coachiq-frontend";
    inherit version;
    src = frontendSrc;

    npmDepsHash = "sha256-/m2Y2A/+BTJVnW/8Fs234DngHNejzBDDZP0FC6otdM4=";

    # Handle React 19 peer dependency conflicts
    npmFlags = [ "--legacy-peer-deps" ];

    nativeBuildInputs = [
      nodejs
      pkgs.python3
      pkgs.pkg-config
    ] ++ pkgs.lib.optionals pkgs.stdenv.isDarwin [
      pkgs.apple-sdk
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
}
