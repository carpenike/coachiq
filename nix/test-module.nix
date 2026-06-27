# Test the CoachIQ NixOS module configuration.
# Wired into flake checks by HOF-019.

{
  nixpkgs ? <nixpkgs>,
  system ? builtins.currentSystem,
  module ? null,
  package ? null,
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

  coachiqModule =
    if module != null then
      module
    else
      import ./module.nix {
        self.packages.${system}.coachiq = testPackage;
      };

  evaluatedConfig = lib.nixosSystem {
    inherit system;
    modules = [
      coachiqModule
      {
        coachiq.enable = true;
        coachiq.package = testPackage;
        coachiq.settings = {
          server.port = 8080;
          security.secretKeyFile = "/run/secrets/coachiq-security-secret";
          features.enableJ1939 = true;
        };
      }
    ];
  };

  env = evaluatedConfig.config.systemd.services.coachiq.environment;
  checks = [
    {
      name = "coachiq namespace is preserved";
      ok = evaluatedConfig.config.coachiq.enable == true;
    }
    {
      name = "configured server port reaches environment";
      ok = env.COACHIQ_SERVER__PORT == "8080";
    }
    {
      name = "default server host stays unset";
      ok = !(env ? COACHIQ_SERVER__HOST);
    }
    {
      name = "security secret file reaches environment";
      ok = env.COACHIQ_SECURITY__SECRET_KEY_FILE == "/run/secrets/coachiq-security-secret";
    }
    {
      name = "J1939 feature flag reaches environment";
      ok = env.COACHIQ_J1939__ENABLED == "true";
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
