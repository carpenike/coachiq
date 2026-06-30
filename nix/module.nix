# nix/module.nix
#
# CoachIQ NixOS module. Pydantic Settings in backend/core/config.py own the
# long-tail schema; this module keeps only load-bearing options first-class.

{ self }:

{ config, lib, pkgs, ... }:

let
  cfg = config.services.coachiq;
  settingNames = lib.attrNames cfg.settings;
  secretSettingNames = [
    "COACHIQ_AUTH__SECRET_KEY"
    "COACHIQ_AUTH__SECRET_KEY_FILE"
    "COACHIQ_SECURITY__SECRET_KEY"
    "COACHIQ_SECURITY__SECRET_KEY_FILE"
  ];

  toEnvValue = value:
    if builtins.isBool value then
      (if value then "true" else "false")
    else
      toString value;

  settingsEnv = lib.mapAttrs (_name: toEnvValue) cfg.settings;

  firstClassEnv = {
    COACHIQ_ENVIRONMENT = "production";
    COACHIQ_SERVER__HOST = cfg.host;
    COACHIQ_SERVER__PORT = toString cfg.port;
    COACHIQ_PERSISTENCE__DATA_DIR = cfg.dataDir;
    COACHIQ_LOGGING__LEVEL = cfg.logLevel;
    COACHIQ_SECURITY__TLS_TERMINATION_IS_EXTERNAL = toEnvValue cfg.tlsTerminationIsExternal;
  };

  finalEnv = settingsEnv // firstClassEnv;
in
{
  options.services.coachiq = {
    enable = lib.mkEnableOption "CoachIQ RV-C network server";

    package = lib.mkOption {
      type = lib.types.package;
      default = self.packages.${pkgs.system}.coachiq;
      description = "The CoachIQ package to run.";
    };

    host = lib.mkOption {
      type = lib.types.str;
      default = "127.0.0.1";
      description = ''
        Interface to bind. Default `127.0.0.1` assumes a reverse proxy
        on the same host. Use `0.0.0.0` only on controlled networks.
      '';
    };

    port = lib.mkOption {
      type = lib.types.port;
      default = 8000;
      description = "TCP port to bind on `host`.";
    };

    dataDir = lib.mkOption {
      type = lib.types.str;
      default = "/var/lib/coachiq";
      description = ''
        Base directory for CoachIQ persistent data. This maps to
        `COACHIQ_PERSISTENCE__DATA_DIR`; persistence is mandatory in the
        current backend architecture.
      '';
    };

    environmentFile = lib.mkOption {
      type = lib.types.nullOr lib.types.path;
      default = null;
      description = ''
        Optional root-readable EnvironmentFile carrying secrets. Use this
        for `COACHIQ_SECURITY__SECRET_KEY`, `COACHIQ_AUTH__SECRET_KEY`, or
        their `_FILE` variants from a deployment secret manager such as
        sops-nix or agenix. Secret values must not be placed in Nix options
        or the world-readable Nix store.
      '';
    };

    openFirewall = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = ''
        Open `port` in the host firewall. Default is false because the
        expected topology is a local reverse proxy in front of CoachIQ.
      '';
    };

    logLevel = lib.mkOption {
      type = lib.types.enum [ "DEBUG" "INFO" "WARNING" "ERROR" "CRITICAL" ];
      default = "INFO";
      description = "CoachIQ logging level.";
    };

    tlsTerminationIsExternal = lib.mkOption {
      type = lib.types.bool;
      default = false;
      description = ''
        Set `COACHIQ_SECURITY__TLS_TERMINATION_IS_EXTERNAL=true` when Caddy
        or another trusted reverse proxy terminates TLS for CoachIQ.
      '';
    };

    settings = lib.mkOption {
      type = with lib.types; attrsOf (oneOf [ str int bool ]);
      default = { };
      example = lib.literalExpression ''
        {
          COACHIQ_CAN__INTERFACES = "can0,can1";
          COACHIQ_CAN__INTERFACE_MAPPINGS = builtins.toJSON {
            house = "can0";
            chassis = "can1";
          };
          COACHIQ_FEATURES__DOMAIN_API_V2 = false;
          COACHIQ_MULTI_NETWORK__CROSS_NETWORK_WHITELIST = ''${builtins.toJSON [ "rvc" "j1939" ]};
          COACHIQ_MULTI_NETWORK__MESSAGE_ROUTING_TIMEOUT = "0.25";
        }
      '';
      description = ''
        Non-secret `COACHIQ_*` environment variables passed to the service.
        Use current Pydantic field names from `backend/core/config.py`.

        Values appear in the Nix store. Do not put secrets here; use
        `environmentFile` instead.

        Encoding convention: booleans and integers may use native Nix bool/int
        values; strings are passed as-is. Floats must be quoted strings because
        this option intentionally accepts only str/int/bool. List and dict
        settings should be JSON strings unless a specific Pydantic field parser
        is known to accept comma-separated strings.
      '';
    };
  };

  config = lib.mkIf cfg.enable {
    assertions = [
      {
        assertion = lib.all (name: lib.hasPrefix "COACHIQ_" name) settingNames;
        message = "services.coachiq.settings keys must be full COACHIQ_* environment variable names.";
      }
      {
        assertion = lib.all (name: !(builtins.elem name secretSettingNames)) settingNames;
        message = "CoachIQ secret settings must be supplied through services.coachiq.environmentFile, not services.coachiq.settings.";
      }
    ];

    environment.systemPackages = [ cfg.package ];

    systemd.tmpfiles.rules = [
      "d ${cfg.dataDir} 0755 coachiq coachiq -"
      "d ${cfg.dataDir}/databases 0755 coachiq coachiq -"
      "d ${cfg.dataDir}/backups 0755 coachiq coachiq -"
      "d ${cfg.dataDir}/config 0755 coachiq coachiq -"
      "d ${cfg.dataDir}/themes 0755 coachiq coachiq -"
      "d ${cfg.dataDir}/dashboards 0755 coachiq coachiq -"
      "d ${cfg.dataDir}/logs 0755 coachiq coachiq -"
      "d ${cfg.dataDir}/reference 0755 root root -"
    ] ++ lib.optionals (cfg.dataDir == "/var/lib/coachiq") [
      "C ${cfg.dataDir}/reference 0755 root root - ${cfg.package}/share/coachiq/config"
    ];

    users.users.coachiq = {
      isSystemUser = true;
      group = "coachiq";
      description = "CoachIQ service user";
    };

    users.groups.coachiq = { };

    systemd.services.coachiq = {
      description = "CoachIQ RV-C HTTP/WebSocket API";
      after = [ "network.target" ];
      wantedBy = [ "multi-user.target" ];

      environment = finalEnv;

      serviceConfig = {
        ExecStartPre = [
          "${cfg.package}/bin/coachiq-validate-config"
          "+${pkgs.coreutils}/bin/mkdir -p ${cfg.dataDir}"
          "+${pkgs.coreutils}/bin/chown -R coachiq:coachiq ${cfg.dataDir}"
        ];
        ExecStart = "${cfg.package}/bin/coachiq-daemon";
        ExecStartPost = [
          "${pkgs.bash}/bin/bash -c 'sleep 20 && ${cfg.package}/share/coachiq/nix/health-check.sh'"
        ];
        Restart = "always";
        RestartSec = 5;
        User = "coachiq";
        Group = "coachiq";
        WorkingDirectory = cfg.dataDir;
        SupplementaryGroups = [ "dialout" ];

        NoNewPrivileges = true;
        PrivateTmp = true;
        ProtectSystem = "strict";
        ProtectHome = true;
        StateDirectory = "coachiq";
        ReadWritePaths = [
          cfg.dataDir
          "/dev"
        ];
      } // lib.optionalAttrs (cfg.environmentFile != null) {
        EnvironmentFile = cfg.environmentFile;
      };
    };

    networking.firewall.allowedTCPPorts = lib.mkIf cfg.openFirewall [ cfg.port ];
  };
}
