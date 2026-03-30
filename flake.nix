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
          mkPythonScriptPackage = {
            pname,
            scriptFile,
            scriptName,
            pythonDeps,
          }:
            let
              pythonEnv = python.withPackages pythonDeps;
            in pkgs.stdenvNoCC.mkDerivation {
              inherit pname;
              version = "1.0.1";
              src = self;
              dontBuild = true;
              installPhase = ''
                mkdir -p $out/bin
                mkdir -p $out/share/${pname}
                install -m755 ${scriptFile} $out/share/${pname}/${scriptName}.py

                cat > $out/bin/${scriptName} <<EOF
                #!${pkgs.runtimeShell}
                exec ${pythonEnv}/bin/python $out/share/${pname}/${scriptName}.py "\$@"
                EOF
                chmod +x $out/bin/${scriptName}
              '';
            };

          system2mqttPkg = mkPythonScriptPackage {
            pname = "system2mqtt";
            scriptFile = ./system2mqtt.py;
            scriptName = "system2mqtt";
            pythonDeps = ps: [
              ps.psutil
              ps.paho-mqtt
              ps.dbus-python
            ];
          };

          borgmaticUpdateMqttPkg = mkPythonScriptPackage {
            pname = "borgmatic-update-mqtt";
            scriptFile = ./borgmatic_update_mqtt.py;
            scriptName = "borgmatic-update-mqtt";
            pythonDeps = ps: [
              ps.paho-mqtt
            ];
          };
        in {
          packages = {
            system2mqtt = system2mqttPkg;
            borgmatic-update-mqtt = borgmaticUpdateMqttPkg;
            system2mqtt-bundle = pkgs.symlinkJoin {
              name = "system2mqtt-bundle-1.0.1";
              paths = [
                system2mqttPkg
                borgmaticUpdateMqttPkg
              ];
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
        nixosModules.system2mqtt = { pkgs, ... }@args: import ./module.nix (args // {
          system2mqttPackage = self.packages.${pkgs.system}.system2mqtt;
          borgmaticUpdateMqttPackage = self.packages.${pkgs.system}."borgmatic-update-mqtt";
        });
      };
}
