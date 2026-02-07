import paho.mqtt.client as mqtt
import socket
import json
import psutil
import time

# Configuration
device_id = socket.gethostname().replace('.', '_').replace('-', '_')
sensor_name = "CPU Usage"
unique_id = f"{device_id}_cpu_usage"
discovery_prefix = "homeassistant"
state_topic = f"{discovery_prefix}/sensor/{unique_id}/state"
config_topic = f"{discovery_prefix}/sensor/{unique_id}/config"

# MQTT broker settings
mqtt_host = "vm-nixos-03"
mqtt_port = 1883
mqtt_user = "monitoring"  # Set to your username if needed
mqtt_pass = "Wrfb5A6DcyLXzGfh8DkzKv0EWCA5s2lG"  # Set to your password if needed

# Discovery config payload
config_payload = {
    "name": sensor_name,
    "state_topic": state_topic,
    "unique_id": unique_id,
    "device": {
        "identifiers": [device_id],
        "name": device_id
    },
    "unit_of_measurement": "%",
    "state_class": "measurement"
}

client = mqtt.Client()
if mqtt_user and mqtt_pass:
    client.username_pw_set(mqtt_user, mqtt_pass)
client.connect(mqtt_host, mqtt_port, 60)

# Publish discovery config (retain=True)
client.publish(config_topic, json.dumps(config_payload), retain=True)

# Publish state in a loop
client.loop_start()
try:
    while True:
        cpu = psutil.cpu_percent()
        client.publish(state_topic, cpu)
        print(f"Published CPU usage: {cpu}%")
        time.sleep(30)
except KeyboardInterrupt:
    pass
finally:
    client.loop_stop()
    client.disconnect()