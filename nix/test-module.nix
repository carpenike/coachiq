# Test the CoachIQ NixOS module configuration.

{
  nixpkgs ? <nixpkgs>,
  system ? builtins.currentSystem,
  module ? null,
  package ? null,
  frontend ? null,
}:

let
  pkgs =
    if builtins.isAttrs nixpkgs && nixpkgs ? legacyPackages then
      nixpkgs.legacyPackages.${system}
    else
      import nixpkgs { inherit system; };
  lib =
    if builtins.isAttrs nixpkgs && nixpkgs ? lib then
      nixpkgs.lib
    else
      pkgs.lib;

  testPackage =
    if package != null then
      package
    else
      pkgs.runCommand "coachiq-test-package" { } ''
        mkdir -p $out/bin $out/share/coachiq/nix $out/share/coachiq/config
        touch $out/bin/coachiq-daemon
        touch $out/bin/coachiq-validate-config
        touch $out/share/coachiq/nix/health-check.sh
      '';

  testFrontendPackage =
    if frontend != null then
      frontend
    else
      pkgs.runCommand "coachiq-test-frontend" { } ''
        mkdir -p $out
        touch $out/index.html
      '';

  coachiqModule =
    if module != null then
      module
    else
      import ./module.nix {
        self.packages.${system}.coachiq = testPackage;
        self.packages.${system}.frontend = testFrontendPackage;
      };

  envFile = "/run/secrets/coachiq.env";
  evaluatedConfig = lib.nixosSystem {
    inherit system;
    modules = [
      coachiqModule
      {
        services.coachiq = {
          enable = true;
          package = testPackage;
          host = "127.0.0.1";
          port = 8080;
          dataDir = "/var/lib/coachiq-test";
          environmentFile = envFile;
          logLevel = "WARNING";
          tlsTerminationIsExternal = true;
          settings = {
            COACHIQ_CAN__INTERFACE_MAPPINGS = builtins.toJSON {
              house = "can0";
              chassis = "can1";
            };
            COACHIQ_FEATURES__DOMAIN_API_V2 = false;
            COACHIQ_MULTI_NETWORK__CROSS_NETWORK_WHITELIST = builtins.toJSON [ "rvc" "j1939" ];
            COACHIQ_MULTI_NETWORK__MESSAGE_ROUTING_TIMEOUT = "0.25";
          };
        };
      }
    ];
  };

  service = evaluatedConfig.config.systemd.services.coachiq;
  env = service.environment;
  serviceConfig = service.serviceConfig;
  checks = [
    {
      name = "services.coachiq namespace is preserved";
      ok = evaluatedConfig.config.services.coachiq.enable == true;
    }
    {
      name = "configured server port reaches environment";
      ok = env.COACHIQ_SERVER__PORT == "8080";
    }
    {
      name = "data dir reaches environment";
      ok = env.COACHIQ_PERSISTENCE__DATA_DIR == "/var/lib/coachiq-test";
    }
    {
      name = "environment file reaches systemd service";
      ok = serviceConfig.EnvironmentFile == envFile;
    }
    {
      name = "working directory is the configured data dir";
      ok = serviceConfig.WorkingDirectory == "/var/lib/coachiq-test";
    }
    {
      name = "first-class log level reaches environment";
      ok = env.COACHIQ_LOGGING__LEVEL == "WARNING";
    }
    {
      name = "first-class TLS termination reaches environment";
      ok = env.COACHIQ_SECURITY__TLS_TERMINATION_IS_EXTERNAL == "true";
    }
    {
      name = "freeform bool uses current Pydantic key";
      ok = env.COACHIQ_FEATURES__DOMAIN_API_V2 == "false";
    }
    {
      name = "freeform JSON dict reaches environment";
      ok = env.COACHIQ_CAN__INTERFACE_MAPPINGS == ''{"chassis":"can1","house":"can0"}'';
    }
    {
      name = "freeform JSON list reaches environment";
      ok = env.COACHIQ_MULTI_NETWORK__CROSS_NETWORK_WHITELIST == ''["rvc","j1939"]'';
    }
    {
      name = "freeform float string reaches environment";
      ok = env.COACHIQ_MULTI_NETWORK__MESSAGE_ROUTING_TIMEOUT == "0.25";
    }
    {
      name = "frontend package reaches static dir environment";
      ok = env.COACHIQ_STATIC_DIR == "${testFrontendPackage}";
    }
  ];

  failures = map (check: check.name) (builtins.filter (check: !check.ok) checks);
in
if failures == [ ] then
  pkgs.runCommand "coachiq-module-test-ok" { } ''
    touch $out
  ''
else
  throw "CoachIQ module test failed: ${lib.concatStringsSep ", " failures}"
