import psutil
import socket
import paho.mqtt.client as mqtt
import json
import time

## Collect metrics
class SystemMonitor:
    def __init__(self):
        """Initialize the system monitor with configuration."""
        self.hostname = socket.gethostname()
        self.discovery_prefix = "homeassistant"
        self.device_id = self.hostname.replace('.', '_').replace('-', '_')
        self.base_topic = f"system_monitor/{self.device_id}"
        self.device_info = {
            "identifiers": [self.device_id],
            "name": self.hostname,
            "model": "System Monitor",
            "manufacturer": "Ragr3n",
            "sw_version": "1.0.0"
        }

        # Define metrics as a list of dicts for easy extension
        self.metrics = [
            {
                "name": "CPU Usage",
                "unique_id": f"{self.device_id}_disk_percent",
                "unit": "%",
                "icon": "mdi:cpu-64-bit",
                "getter": lambda: psutil.cpu_percent(interval=1),
                "state_class": "measurement"
            },
            {
                "name": "RAM Usage",
                "unique_id": f"{self.device_id}_ram_percent",
                "unit": "%",
                "icon": "mdi:memory",
                "getter": lambda: psutil.virtual_memory().percent,
                "state_class": "measurement"
            },
            {
                "name": "Disk Usage",
                "unique_id": f"{self.device_id}_t14_ssh_service",
                "unit": "%",
                "icon": "mdi:harddisk",
                "getter": lambda: psutil.disk_usage('/').percent,
                "state_class": "measurement"
            }
        ]

    def publish_discovery(self):
        for metric in self.metrics:
            config_topic = f"{self.discovery_prefix}/sensor/{metric['unique_id']}/config"
            state_topic = f"{self.discovery_prefix}/sensor/{metric['unique_id']}/state"
            config_payload = {
                "name": metric["name"],
                "unique_id": metric["unique_id"],
                "state_topic": state_topic,
                "device": self.device_info,
                "unit_of_measurement": metric["unit"],
                "icon": metric["icon"],
                "state_class":  metric["state_class"],
            }
            self.client.publish(config_topic, json.dumps(config_payload), retain=True)

    def publish_states(self):
        for metric in self.metrics:
            state_topic = f"{self.discovery_prefix}/sensor/{metric['unique_id']}/state"
            value = metric["getter"]()
            self.client.publish(state_topic, value)

    def run(self):
        self.client = mqtt.Client()
        mqtt_host = "vm-nixos-03"
        mqtt_port = 1883
        mqtt_user = "monitoring"
        mqtt_pass = "Wrfb5A6DcyLXzGfh8DkzKv0EWCA5s2lG"
        self.client.username_pw_set(mqtt_user, mqtt_pass)
        self.client.connect(mqtt_host, mqtt_port, 60)
        self.client.loop_start()
        time.sleep(2)
        self.publish_discovery()
        update_interval = 30
        try:
            while True:
                self.publish_states()
                time.sleep(update_interval)
        except KeyboardInterrupt:
            pass
        finally:
            self.client.publish(f"{self.base_topic}/availability", "offline", retain=True)
            self.client.loop_stop()
            self.client.disconnect()






if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Linux System Monitor MQTT for Home Assistant")
    parser.add_argument('--remove-device', action='store_true', help='Remove device and all sensors from Home Assistant')
    args = parser.parse_args()

    monitor = SystemMonitor()
    monitor.client = mqtt.Client()
    mqtt_host = "vm-nixos-03"
    mqtt_port = 1883
    mqtt_user = "monitoring"
    mqtt_pass = "Wrfb5A6DcyLXzGfh8DkzKv0EWCA5s2lG"
    monitor.client.username_pw_set(mqtt_user, mqtt_pass)
    monitor.client.connect(mqtt_host, mqtt_port, 60)
    monitor.client.loop_start()
    time.sleep(2)

    if args.remove_device:
        for metric in monitor.metrics:
            config_topic = f"{monitor.discovery_prefix}/sensor/{metric['unique_id']}/config"
            monitor.client.publish(config_topic, "", retain=True)
        monitor.client.publish(f"{monitor.base_topic}/availability", "", retain=True)
        print("Device and all sensors removed from Home Assistant.")
        monitor.client.loop_stop()
        monitor.client.disconnect()
    else:
        monitor.run()