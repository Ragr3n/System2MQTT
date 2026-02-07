
import argparse
import psutil
import dbus
import paho.mqtt.client as mqtt
import time
import json
import socket

def parse_args():
    parser = argparse.ArgumentParser(description="Linux system monitoring script for Home Assistant via MQTT")
    parser.add_argument('--mqtt-broker', type=str, default='localhost', help='MQTT broker address')
    parser.add_argument('--mqtt-port', type=int, default=1883, help='MQTT broker port')
    parser.add_argument('--mqtt-username', type=str, default=None, help='MQTT username (optional)')
    parser.add_argument('--mqtt-password', type=str, default=None, help='MQTT password (optional)')
    parser.add_argument('--services', type=str, default='', help='Comma-separated list of systemd services to monitor (optional)')
    parser.add_argument('--interval', type=int, default=30, help='Publish interval in seconds')
    parser.add_argument('--discovery-prefix', type=str, default='homeassistant', help='Home Assistant MQTT discovery prefix')
    parser.add_argument('--device-name', type=str, default=socket.gethostname(), help='Device name for Home Assistant')
    return parser.parse_args()


def setup_mqtt(broker, port):
    def on_connect(client, userdata, flags, rc):
        print(f"Connected to MQTT broker with result code {rc}")
    client = mqtt.Client()
    client.on_connect = on_connect
    return client

def publish_discovery_configs(client, device_name, discovery_prefix, metrics, services):
    device = {
        "identifiers": [device_name],
        "name": device_name,
        "manufacturer": "CustomLinuxMonitor",
        "model": "PythonScript"
    }
    # Metrics
    for metric in metrics:
        unique_id = f"{device_name}_{metric}"
        config_topic = f"{discovery_prefix}/sensor/{unique_id}/config"
        state_topic = f"{discovery_prefix}/sensor/{device_name}/{metric}/state"
        config_payload = {
            "name": f"{device_name} {metric}",
            "state_topic": state_topic,
            "unique_id": unique_id,
            "device": device,
            "force_update": True,
            "unit_of_measurement": "%",
            "state_class": "measurement"
        }
        if metric == "cpu_percent":
            config_payload["device_class"] = "temperature"  # closest match, or omit for generic
        elif metric == "ram_percent":
            config_payload["device_class"] = "battery"  # closest match, or omit for generic
        elif metric == "disk_percent":
            config_payload["device_class"] = "battery"  # closest match, or omit for generic
        client.publish(config_topic, json.dumps(config_payload), retain=True)
    # Services
    if services:
        for service in services:
            unique_id = f"{device_name}_service_{service}"
            config_topic = f"{discovery_prefix}/binary_sensor/{unique_id}/config"
            state_topic = f"{discovery_prefix}/binary_sensor/{device_name}/service_{service}/state"
            config_payload = {
                "name": f"{device_name} {service} service",
                "state_topic": state_topic,
                "unique_id": unique_id,
                "device": device,
                "payload_on": "active",
                "payload_off": "inactive",
                "device_class": "running",
                "force_update": True
            }
            client.publish(config_topic, json.dumps(config_payload), retain=True)

# Metrics collection
def get_system_metrics():
    return {
        "cpu_percent": psutil.cpu_percent(),
        "ram_percent": psutil.virtual_memory().percent,
        "disk_percent": psutil.disk_usage("/").percent,
        "net_io": psutil.net_io_counters()._asdict(),
    }

def get_service_status(service):
    try:
        bus = dbus.SystemBus()
        systemd = bus.get_object('org.freedesktop.systemd1', '/org/freedesktop/systemd1')
        manager = dbus.Interface(systemd, 'org.freedesktop.systemd1.Manager')
        unit_name = f"{service}.service"
        unit_path = manager.GetUnit(unit_name)
        unit = bus.get_object('org.freedesktop.systemd1', unit_path)
        props = dbus.Interface(unit, 'org.freedesktop.DBus.Properties')
        active_state = props.Get('org.freedesktop.systemd1.Unit', 'ActiveState')
        return str(active_state)
    except Exception as e:
        return f"error: {e}"

def collect_metrics():
    metrics = get_system_metrics()
    service_status = {s: get_service_status(s) for s in SERVICES}
    metrics["services"] = service_status
    return metrics


if __name__ == "__main__":
    args = parse_args()
    mqtt_broker = args.mqtt_broker
    mqtt_port = args.mqtt_port
    services = [s.strip() for s in args.services.split(",") if s.strip()]
    publish_interval = args.interval

    discovery_prefix = args.discovery_prefix
    device_name = args.device_name

    client = setup_mqtt(mqtt_broker, mqtt_port)
    if args.mqtt_username and args.mqtt_password:
        client.username_pw_set(args.mqtt_username, args.mqtt_password)
    client.connect(mqtt_broker, mqtt_port, 60)
    client.loop_start()

    # Publish discovery configs
    metric_keys = ["cpu_percent", "ram_percent", "disk_percent"]
    publish_discovery_configs(client, device_name, discovery_prefix, metric_keys, services)

    def collect_metrics_arg():
        metrics = get_system_metrics()
        if services:
            service_status = {s: get_service_status(s) for s in services}
            metrics["services"] = service_status
        return metrics

    while True:
        metrics = collect_metrics_arg()
        # Publish metrics to individual state topics for discovery
        for metric in metric_keys:
            state_topic = f"{discovery_prefix}/sensor/{device_name}/{metric}/state"
            value = metrics.get(metric)
            client.publish(state_topic, value)
        # Publish service states if any
        if services and "services" in metrics:
            for service, status in metrics["services"].items():
                state_topic = f"{discovery_prefix}/binary_sensor/{device_name}/service_{service}/state"
                # Home Assistant expects 'active' or 'inactive' for binary_sensor
                payload = "active" if status == "active" else "inactive"
                client.publish(state_topic, payload)
        time.sleep(publish_interval)
