{ config, lib, pkgs, system2mqttPackage ? null, borgmaticUpdateMqttPackage ? null, ... }:

let
  cfg = config.services.system2mqtt;

  scriptPath = "${cfg.package}/bin/system2mqtt";
  diskArgs = lib.optionalString (cfg.mountpoints != []) "--mountpoints ${lib.escapeShellArgs cfg.mountpoints}";
  netArgs = lib.optionalString (cfg.interfaces != []) "--interfaces ${lib.escapeShellArgs cfg.interfaces}";
  serviceArgs = lib.optionalString (cfg.services != []) "--services ${lib.escapeShellArgs cfg.services}";
  borgmaticArgs = lib.optionalString (cfg.borgmatic != []) "--borgmatic ${lib.escapeShellArgs cfg.borgmatic}";
in {
  options.services.system2mqtt = with lib; {
    enable = mkEnableOption "System2MQTT MQTT publisher";

    package = mkOption {
      type = types.package;
      default = system2mqttPackage;
      description = "Package providing the system2mqtt executable";
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

    borgmatic = mkOption {
      type = types.listOf types.str;
      default = [];
      description = "Borgmatic backups to monitor";
    };

    stateFile = mkOption {
      type = types.str;
      default = "/var/lib/system2mqtt/state.json";
      description = "Path to discovery state file";
    };

    user = mkOption {
      type = types.str;
      default = "system2mqtt";
      description = "User to run the service";
    };

    group = mkOption {
      type = types.str;
      default = "system2mqtt";
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
        description = "System2MQTT service user";
      };
    };

    users.groups = lib.mkIf cfg.createUser {
      ${cfg.group} = {};
    };
    environment.systemPackages = [ pkgs.borgmatic-update-mqtt ];
    systemd.services.system2mqtt = {
      description = "System2MQTT MQTT publisher";
      after = [ "network-online.target" ];
      wants = [ "network-online.target" ];
      wantedBy = [ "multi-user.target" ];

      serviceConfig = {
        Type = "simple";
        User = cfg.user;
        Group = cfg.group;
        Restart = "on-failure";
        StateDirectory = "system2mqtt";
      } // lib.optionalAttrs (cfg.mqtt.passwordFile != null) {
        LoadCredential = "mqtt_password:${cfg.mqtt.passwordFile}";
      };

      script = let
        passwordArg = if cfg.mqtt.passwordFile != null
          then "$(cat $CREDENTIALS_DIRECTORY/mqtt_password)"
          else lib.escapeShellArg cfg.mqtt.password;
      in ''
        exec ${scriptPath} \
          --host ${lib.escapeShellArg cfg.mqtt.host} \
          --port ${toString cfg.mqtt.port} \
          --user ${lib.escapeShellArg cfg.mqtt.user} \
          --pass ${passwordArg} \
          --interval ${toString cfg.interval} \
          --state-file ${lib.escapeShellArg cfg.stateFile} \
          ${lib.optionalString cfg.defaults "--use-defaults"} \
          ${diskArgs} \
          ${netArgs} \
          ${serviceArgs} \
          ${borgmaticArgs}
      '';
    };
  };
}
