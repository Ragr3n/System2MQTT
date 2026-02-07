import psutil
import paho.mqtt.client as mqtt
import socket
import json
import time

class SystemMonitor:
    def __init__(self):
        """Initialize the system monitor with configuration."""
        self.hostname = socket.gethostname()
        self.device_id = self.hostname.replace('.', '_').replace('-', '_')
        self.discovery_topic = f"homeassistant"
        self.base_topic = f"system_monitor/{self.device_id}"
        self.device_info = {
            "identifiers": [self.device_id],
            "name": self.hostname,
            "model": "System Monitor",
            "manufacturer": "Ragr3n",
            "sw_version": "1.0.1"
        }
        self.availability_topic = f"{self.base_topic}/availability"
        self.metrics = [
            {
                "name": "CPU Usage",
                "unique_id": f"{self.device_id}_cpu_percent",
                "discovery_topic": f"{self.discovery_topic}/sensor/{self.device_id}_cpu_percent/config",
                "state_topic": f"{self.base_topic}/sensor/{self.device_id}_cpu_percent/state",
                "device": self.device_info,
                "unit_of_measurement": "%",
                "icon": "mdi:cpu-64-bit",
                "state_class": "measurement",
                "availability_topic": self.availability_topic,
                "state": self.state_cpu_percent()
            },
            {
                "name": "SSH Service Running",
                "unique_id": f"{self.device_id}_ssh_running",
                "discovery_topic": f"{self.discovery_topic}/binary_sensor/{self.device_id}_ssh_running/config",
                "state_topic": f"{self.base_topic}/binary_sensor/{self.device_id}_ssh_running/state",
                "device": self.device_info,
                "payload_on": "ON",
                "payload_off": "OFF",
                "device_class": "running",
                "icon": "mdi:server",
                "availability_topic": self.availability_topic,
                "state": "ON"
            }
        ]
    def state_cpu_percent(self):
        return psutil.cpu_percent(interval=1)

    def publish_discovery(self):
        for metric in self.metrics:
            print(f"Publishing discovery for {metric['name']} to {metric['discovery_topic']}")
            self.client.publish(metric['discovery_topic'], json.dumps(metric), retain=True)

    def publish_states(self):
        for metric in self.metrics:
            self.client.publish(metric["state_topic"], metric["state"])

    def run(self):
        self.client = mqtt.Client()
        mqtt_host = "vm-nixos-03"
        mqtt_port = 1883
        mqtt_user = "monitoring"
        mqtt_pass = "Wrfb5A6DcyLXzGfh8DkzKv0EWCA5s2lG"
        # Set MQTT Last Will and Testament (LWT)
        self.client.will_set(self.availability_topic, "offline", retain=True)
        self.client.username_pw_set(mqtt_user, mqtt_pass)
        self.client.connect(mqtt_host, mqtt_port, 60)
        self.client.loop_start()
        time.sleep(2)
        # Publish 'online' to availability topic
        self.client.publish(self.availability_topic, "online", retain=True)
        self.publish_discovery()
        update_interval = 30
        try:
            while True:
                self.publish_states()
                time.sleep(update_interval)
        except KeyboardInterrupt:
            print("Stopping system monitor...")
        finally:
            self.client.publish(self.availability_topic, "offline", retain=True)
            self.client.loop_stop()
            self.client.disconnect()


if __name__ == "__main__":
    monitor = SystemMonitor()
    monitor.run()