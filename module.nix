{ config, lib, pkgs, self ? null, ... }:

let
  cfg = config.services.system-monitor;
  defaultPackage = if self != null then
    self.packages.${pkgs.system}.system-monitor
  else
    pkgs.stdenvNoCC.mkDerivation {
      pname = "system-monitor";
      version = "1.0.1";
      src = ./.;
      dontBuild = true;
      installPhase = ''
        mkdir -p $out/share/system-monitor
        cp ${./system_monitor.py} $out/share/system-monitor/system_monitor.py
      '';
    };
  pythonEnv = pkgs.python3.withPackages (ps: [
    ps.psutil
    ps.paho-mqtt
  ]);
  scriptPath = "${cfg.package}/share/system-monitor/system_monitor.py";
  diskArgs = lib.optionalString (cfg.mountpoints != []) "--disk-mountpoints ${lib.escapeShellArgs cfg.mountpoints}";
  netArgs = lib.optionalString (cfg.interfaces != []) "--net-interfaces ${lib.escapeShellArgs cfg.interfaces}";
  serviceArgs = lib.optionalString (cfg.services != []) "--services ${lib.escapeShellArgs cfg.services}";
in {
  options.services.system-monitor = with lib; {
    enable = mkEnableOption "System Monitor MQTT publisher";

    package = mkOption {
      type = types.package;
      default = defaultPackage;
      description = "Package providing system_monitor.py";
    };

    mqtt = mkOption {
      type = types.submodule ({ ... }: {
        options = {
          host = mkOption {
            type = types.str;
            default = "localhost";
            description = "MQTT broker host";
          };

          port = mkOption {
            type = types.port;
            default = 1883;
            description = "MQTT broker port";
          };

          user = mkOption {
            type = types.str;
            default = "";
            description = "MQTT username";
          };

          password = mkOption {
            type = types.str;
            default = "";
            description = "MQTT password (stored in Nix store; use passwordFile for secrets)";
          };

          passwordFile = mkOption {
            type = types.nullOr types.path;
            default = null;
            description = "Path to password file (loaded via systemd LoadCredential as mqtt_password)";
          };
        };
      });
      default = {};
      description = "MQTT connection settings";
    };

    interval = mkOption {
      type = types.int;
      default = 30;
      description = "Update interval in seconds";
    };

    defaults = mkOption {
      type = types.bool;
      default = true;
      description = "Enable default sensors";
    };

    mountpoints = mkOption {
      type = types.listOf types.str;
      default = [];
      description = "Disk mountpoints to monitor";
    };

    interfaces = mkOption {
      type = types.listOf types.str;
      default = [];
      description = "Network interfaces to monitor";
    };

    services = mkOption {
      type = types.listOf types.str;
      default = [];
      description = "Systemd services to monitor";
    };

    stateFile = mkOption {
      type = types.str;
      default = "/var/lib/system-monitor/state.json";
      description = "Path to discovery state file";
    };

    user = mkOption {
      type = types.str;
      default = "system-monitor";
      description = "User to run the service";
    };

    group = mkOption {
      type = types.str;
      default = "system-monitor";
      description = "Group to run the service";
    };

    createUser = mkOption {
      type = types.bool;
      default = true;
      description = "Create system user and group";
    };
  };

  config = lib.mkIf cfg.enable {
    users.users = lib.mkIf cfg.createUser {
      ${cfg.user} = {
        isSystemUser = true;
        group = cfg.group;
        description = "System Monitor service user";
      };
    };

    users.groups = lib.mkIf cfg.createUser {
      ${cfg.group} = {};
    };

    systemd.services.system-monitor = {
      description = "System Monitor MQTT publisher";
      after = [ "network-online.target" ];
      wants = [ "network-online.target" ];
      wantedBy = [ "multi-user.target" ];

      serviceConfig = {
        Type = "simple";
        User = cfg.user;
        Group = cfg.group;
        Restart = "on-failure";
        StateDirectory = "system-monitor";
      } // lib.optionalAttrs (cfg.mqtt.passwordFile != null) {
        LoadCredential = "mqtt_password:${cfg.mqtt.passwordFile}";
      };

      script = let
        passwordArg = if cfg.mqtt.passwordFile != null
          then "$(cat $CREDENTIALS_DIRECTORY/mqtt_password)"
          else lib.escapeShellArg cfg.mqtt.password;
      in ''
        exec ${pythonEnv}/bin/python ${scriptPath} \
          --host ${lib.escapeShellArg cfg.mqtt.host} \
          --port ${toString cfg.mqtt.port} \
          --user ${lib.escapeShellArg cfg.mqtt.user} \
          --pass ${passwordArg} \
          --interval ${toString cfg.interval} \
          --state-file ${lib.escapeShellArg cfg.stateFile} \
          ${lib.optionalString cfg.defaults "--use-defaults"} \
          ${diskArgs} \
          ${netArgs} \
          ${serviceArgs}
      '';
    };
  };
}
