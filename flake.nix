{
  description = "Linux system monitoring script with MQTT integration for Home Assistant";
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
            system-monitor = pkgs.stdenvNoCC.mkDerivation {
              pname = "system-monitor";
              version = "1.0.1";
              src = self;
              dontBuild = true;
              installPhase = ''
                mkdir -p $out/share/system-monitor
                cp ${./system_monitor.py} $out/share/system-monitor/system_monitor.py
              '';
            };
            default = self.packages.${system}.system-monitor;
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
        nixosModules.system-monitor = import ./module.nix;
      };
}
