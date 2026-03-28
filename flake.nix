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
          pythonEnv = python.withPackages (ps: [
            ps.psutil
            ps.paho-mqtt
            ps.dbus-python
          ]);
        in {
          packages = {
            system2mqtt = pkgs.stdenvNoCC.mkDerivation {
              pname = "system2mqtt";
              version = "1.0.1";
              src = self;
              dontBuild = true;
              installPhase = ''
                mkdir -p $out/bin
                mkdir -p $out/share/system2mqtt
                install -m755 ${./system2mqtt.py} $out/share/system2mqtt/system2mqtt.py
                install -m755 ${./borgmatic_update_mqtt.py} $out/share/system2mqtt/borgmatic_update_mqtt.py

                cat > $out/bin/system2mqtt <<'EOF'
                #!${pkgs.runtimeShell}
                exec ${pythonEnv}/bin/python $out/share/system2mqtt/system2mqtt.py "$@"
                EOF
                chmod +x $out/bin/system2mqtt

                cat > $out/bin/borgmatic-update-mqtt <<'EOF'
                #!${pkgs.runtimeShell}
                exec ${pythonEnv}/bin/python $out/share/system2mqtt/borgmatic_update_mqtt.py "$@"
                EOF
                chmod +x $out/bin/borgmatic-update-mqtt
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
