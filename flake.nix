{
  description = "System2MQTT: Linux system monitoring script with MQTT integration for Home Assistant";
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  inputs.flake-utils.url = "github:numtide/flake-utils";

  outputs = { self, nixpkgs, flake-utils }:
      flake-utils.lib.eachDefaultSystem (system:
        let
          pkgs = import nixpkgs { inherit system; };
          python = pkgs.python3;
          pythonPackages = python.pkgs;
        in {
          packages = {
            system2mqtt = pkgs.stdenvNoCC.mkDerivation {
              pname = "system2mqtt";
              version = "1.0.1";
              src = self;
              dontBuild = true;
              installPhase = ''
                mkdir -p $out/share/system2mqtt
                cp ${./system_monitor.py} $out/share/system2mqtt/system_monitor.py
              '';
            };
            default = self.packages.${system}.system2mqtt;
          };

          devShell = pkgs.mkShell {
            buildInputs = [
              python
              pythonPackages.psutil
              pythonPackages.paho-mqtt
              pythonPackages.dbus-python
            ];
            shellHook = ''
              echo "Development shell for Linux monitoring script (Python)"
            '';
          };
        }
      ) // {
        nixosModules.system2mqtt = import ./module.nix;
      };
}
