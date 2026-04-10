import socket
import platform
import paho.mqtt.client as mqtt
import json
import psutil
import time
import argparse
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Dict, Any

class SystemMonitor:
    def __init__(self, mqtt_host: str, mqtt_port: int, mqtt_user: str, mqtt_pass: str, use_defaults: bool = True, update_interval: int = 30, mountpoints: list | None = None, interfaces: list | None = None, services: list | None = None, borgmatic: list | None = None, state_file: str | None = None, borgmatic_interval: int | None = None) -> None:
        # Initialize logger
        self.logger = logging.getLogger("SystemMonitor")
        
        # Args
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.mqtt_user = mqtt_user
        self.mqtt_pass = mqtt_pass
        self.use_defaults = use_defaults
        self.update_interval = update_interval
        self.mountpoints = mountpoints
        self.interfaces = interfaces
        self.services = services
        self.borgmatic = borgmatic
        self.state_file = Path(state_file) if state_file else None
        self.borgmatic_interval = None
        if self.borgmatic:
            configured_borgmatic_interval = borgmatic_interval if borgmatic_interval is not None else 3600
            self.borgmatic_interval = max(1, configured_borgmatic_interval)

        # Device info
        self.hostname = socket.gethostname()
        self.device_id = self.hostname.replace('.', '_').replace('-', '_')
        self.distro = self._get_distro_name()
        self.virtualization = self._get_virtualization_type()
        self.sw_version = f"{platform.system()} {platform.release()}"
        self.hw_version = self._get_hw_version()

        # Check if CPU temperature sensor is available
        self.cpu_temp_available = self._get_cpu_temperature() is not None

        # MQTT topics and discovery config
        self.discovery_prefix = "homeassistant"
        self.base_topic = f"system2mqtt/{self.device_id}"
        self.availability_topic = f"{self.base_topic}/availability"
        self.state_topic = f"{self.base_topic}/state"
        self.discovery_payload = self._generate_discovery_payload()

        # Network I/O tracking for rate calculations
        self.prev_net_io: Dict[str, Any] = {}
        self.prev_net_time: float | None = None
        
        # Initialize CPU percent to avoid blocking on first call
        if self.use_defaults:
            psutil.cpu_percent(interval=1)

    @staticmethod
    def _sanitize_borgmatic_repo(repo: str) -> str:
        return repo.replace('/', '_').replace('-', '_')

    @staticmethod
    def _bytes_to_megabytes(value: int | float) -> float:
        return round(value / (1024**2), 2)

    @staticmethod
    def _parse_iso_datetime(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def _get_cpu_temperature(self) -> float | None:
        try:
            temps = psutil.sensors_temperatures()
            if not temps:
                return None
            for entries in temps.values():
                if entries:
                    return round(entries[0].current, 1)
        except (AttributeError, KeyError, IndexError):
            return None
        return None

    def _get_distro_name(self) -> str:
        try:
            data = platform.freedesktop_os_release()
            if data.get("PRETTY_NAME"):
                return data["PRETTY_NAME"]
            if data.get("NAME"):
                return data["NAME"]
        except (OSError, AttributeError):
            pass
        return f"{platform.system()} {platform.release()}"

    def _get_virtualization_type(self) -> str | None:
        try:
            result = subprocess.run(
                ["systemd-detect-virt"],
                capture_output=True,
                text=True,
                timeout=3
            )
            if result.returncode == 0:
                virt = result.stdout.strip()
                return virt if virt else None
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

        dmi_paths = [
            "/sys/class/dmi/id/product_name",
            "/sys/class/dmi/id/sys_vendor",
            "/sys/class/dmi/id/board_vendor",
        ]
        for path in dmi_paths:
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    value = handle.read().strip().lower()
                if any(token in value for token in [
                    "kvm",
                    "qemu",
                    "vmware",
                    "virtualbox",
                    "xen",
                    "hyper-v",
                    "openstack",
                    "bhyve",
                ]):
                    return value
            except OSError:
                continue

        return None

    def _get_hw_version(self) -> str:
        if self.virtualization:
            return f"{platform.machine()} (virtual: {self.virtualization})"
        return platform.machine()

    def _generate_discovery_payload(self) -> Dict[str, Dict[str, Any]]:
        # Build cmps dynamically based on configuration
        cmps: Dict[str, Dict[str, Any]] = {}
    
        if self.use_defaults:
            cmps.update({
                "cpu_usage": {
                    "p": "sensor",
                    "name": "CPU Usage",
                    "unique_id": f"{self.device_id}_cpu_usage",
                    "unit_of_measurement": "%",
                    "state_class": "measurement",
                    "icon": "mdi:cpu-64-bit",
                    "value_template": "{{ value_json.cpu_usage }}"
                },
                "memory_usage": {
                    "p": "sensor",
                    "name": "Memory Usage",
                    "unique_id": f"{self.device_id}_memory_usage",
                    "unit_of_measurement": "%",
                    "state_class": "measurement",
                    "icon": "mdi:memory",
                    "value_template": "{{ value_json.memory_usage }}"
                },
                "memory_used": {
                    "p": "sensor",
                    "name": "Memory Used",
                    "unique_id": f"{self.device_id}_memory_used",
                    "unit_of_measurement": "GB",
                    "state_class": "measurement",
                    "icon": "mdi:memory",
                    "value_template": "{{ value_json.memory_used }}"
                },
                "memory_total": {
                    "p": "sensor",
                    "name": "Memory Total",
                    "unique_id": f"{self.device_id}_memory_total",
                    "unit_of_measurement": "GB",
                    "state_class": "measurement",
                    "icon": "mdi:memory",
                    "value_template": "{{ value_json.memory_total }}"
                },
                "uptime": {
                    "p": "sensor",
                    "name": "Uptime",
                    "unique_id": f"{self.device_id}_uptime",
                    "unit_of_measurement": "s",
                    "state_class": "total_increasing",
                    "icon": "mdi:clock-outline",
                    "value_template": "{{ value_json.uptime_seconds }}"
                },
            })

            if self.cpu_temp_available:
                self.logger.debug("CPU temperature sensor is available, adding to discovery")
                cmps.update({
                    "cpu_temp": {
                        "p": "sensor",
                        "name": "CPU Temperature",
                        "unique_id": f"{self.device_id}_cpu_temp",
                        "unit_of_measurement": "°C",
                        "device_class": "temperature",
                        "state_class": "measurement",
                        "icon": "mdi:thermometer",
                        "value_template": "{{ value_json.cpu_temperature }}"
                    }
                })
            else:
                self.logger.debug("CPU temperature sensor is not available, adding to discovery but disabled by default")
                cmps.update({
                    "cpu_temp": {
                        "p": "sensor",
                        "name": "CPU Temperature",
                        "unique_id": f"{self.device_id}_cpu_temp",
                        "unit_of_measurement": "°C",
                        "device_class": "temperature",
                        "state_class": "measurement",
                        "icon": "mdi:thermometer",
                        "value_template": "{{ value_json.cpu_temperature }}",
                        "enabled_by_default": False
                    }
                })        
        if self.mountpoints:
            self.logger.debug(f"Adding disk sensors for mountpoints: {self.mountpoints}")
            cmps.update(self._generate_disk_sensors())

        if self.interfaces:
            self.logger.debug(f"Adding network sensors for interfaces: {self.interfaces}")
            cmps.update(self._generate_network_sensors())
        
        if self.services:
            self.logger.debug(f"Adding service sensors for: {self.services}")
            cmps.update(self._generate_service_sensors())
        
        if self.borgmatic:
            self.logger.debug(f"Adding borgmatic sensors for: {self.borgmatic}")
            cmps.update(self._generate_borgmatic_sensors())
        
        discovery_payload = {
            "dev": {
                "identifiers": [self.device_id],
                "name": self.hostname,
                "model": self.distro,
                "manufacturer": "System2MQTT",
                "sw_version": self.sw_version,
                "hw_version": self.hw_version
            },
            "o": {
                "name": "System2MQTT",
                "sw": "1.0",
                "url": "https://github.com/Ragr3n/System2MQTT"
            },
            "cmps": cmps,
            "state_topic": self.state_topic,
            "availability_topic": self.availability_topic,
            "qos": 1
        }
        return discovery_payload

    def _generate_network_sensors(self) -> Dict[str, Dict[str, Any]]:
        """Generate network sensors for each configured interface."""
        sensors: Dict[str, Dict[str, Any]] = {}
        for iface in self.interfaces:
            iface_safe = iface.replace('/', '_').replace('-', '_')
            if not iface_safe:
                continue

            sensors[f"net_upload_{iface_safe}"] = {
                "p": "sensor",
                "name": f"Network {iface} Upload",
                "unique_id": f"{self.device_id}_net_upload_{iface_safe}",
                "unit_of_measurement": "Mbps",
                "state_class": "measurement",
                "icon": "mdi:upload-network",
                "value_template": f"{{{{ value_json.net_upload_{iface_safe} }}}}"
            }
            sensors[f"net_download_{iface_safe}"] = {
                "p": "sensor",
                "name": f"Network {iface} Download",
                "unique_id": f"{self.device_id}_net_download_{iface_safe}",
                "unit_of_measurement": "Mbps",
                "state_class": "measurement",
                "icon": "mdi:download-network",
                "value_template": f"{{{{ value_json.net_download_{iface_safe} }}}}"
            }
            sensors[f"net_sent_{iface_safe}"] = {
                "p": "sensor",
                "name": f"Network {iface} Sent",
                "unique_id": f"{self.device_id}_net_sent_{iface_safe}",
                "unit_of_measurement": "GB",
                "state_class": "total_increasing",
                "icon": "mdi:upload",
                "value_template": f"{{{{ value_json.net_sent_{iface_safe} }}}}"
            }
            sensors[f"net_recv_{iface_safe}"] = {
                "p": "sensor",
                "name": f"Network {iface} Received",
                "unique_id": f"{self.device_id}_net_recv_{iface_safe}",
                "unit_of_measurement": "GB",
                "state_class": "total_increasing",
                "icon": "mdi:download",
                "value_template": f"{{{{ value_json.net_recv_{iface_safe} }}}}"
            }

        return sensors
    
    def _generate_service_sensors(self) -> Dict[str, Dict[str, Any]]:
        """Generate binary sensors for each configured systemd service."""
        sensors: Dict[str, Dict[str, Any]] = {}
        for service in self.services:
            service_safe = service.replace('.', '_').replace('-', '_').replace('@', '_')
            if not service_safe:
                continue

            sensors[f"service_{service_safe}"] = {
                "p": "binary_sensor",
                "name": f"Service {service}",
                "unique_id": f"{self.device_id}_service_{service_safe}",
                "device_class": "running",
                "icon": "mdi:cog",
                "value_template": f"{{{{ value_json.service_{service_safe} }}}}",
                "payload_on": "active",
                "payload_off": "inactive"
            }

        return sensors
    
    def _generate_disk_sensors(self) -> Dict[str, Dict[str, Any]]:
        """Generate disk sensors for each configured mountpoint."""
        sensors = {}
        for mountpoint in self.mountpoints:
            # Sanitize mountpoint name for unique_id
            mount_safe = mountpoint.replace('/', '_').strip('_')
            if not mount_safe:
                mount_safe = "root"
            
            sensors[f"disk_usage_{mount_safe}"] = {
                "p": "sensor",
                "name": f"Disk {mountpoint} Usage",
                "unique_id": f"{self.device_id}_disk_usage_{mount_safe}",
                "unit_of_measurement": "%",
                "state_class": "measurement",
                "icon": "mdi:harddisk",
                "value_template": f"{{{{ value_json.disk_usage_{mount_safe} }}}}"
            }
            sensors[f"disk_used_{mount_safe}"] = {
                "p": "sensor",
                "name": f"Disk {mountpoint} Used",
                "unique_id": f"{self.device_id}_disk_used_{mount_safe}",
                "unit_of_measurement": "GB",
                "state_class": "measurement",
                "icon": "mdi:harddisk",
                "value_template": f"{{{{ value_json.disk_used_{mount_safe} }}}}"
            }
            sensors[f"disk_total_{mount_safe}"] = {
                "p": "sensor",
                "name": f"Disk {mountpoint} Total",
                "unique_id": f"{self.device_id}_disk_total_{mount_safe}",
                "unit_of_measurement": "GB",
                "state_class": "measurement",
                "icon": "mdi:harddisk",
                "value_template": f"{{{{ value_json.disk_total_{mount_safe} }}}}"
            }
        return sensors

    def _generate_borgmatic_sensors(self) -> Dict[str, Dict[str, Any]]:
        """Generate borgmatic sensors for each configured backup."""
        sensors: Dict[str, Dict[str, Any]] = {}
        for repo in self.borgmatic:
            # Sanitize backup name for unique_id
            repo_safe = self._sanitize_borgmatic_repo(repo)
            if not repo_safe:
                continue
            repo_label = repo.replace('_', ' ').title()
            repo_topic = f"{self.base_topic}/borgmatic_state/{repo_safe}"

            sensors[f"backup_state_{repo_safe}"] = {
                "p": "sensor",
                "name": f"Backup {repo_label}",
                "unique_id": f"{self.device_id}_backup_state_{repo_safe}",
                "icon": "mdi:cloud-upload",
                "state_topic": repo_topic,
                "value_template": "{{ value_json.backup_state }}"
            }
            sensors[f"backup_last_success_{repo_safe}"] = {
                "p": "sensor",
                "name": f"Backup {repo_label} Last Success",
                "unique_id": f"{self.device_id}_backup_last_success_{repo_safe}",
                "icon": "mdi:calendar-check",
                "device_class": "timestamp",
                "state_topic": repo_topic,
                "value_template": "{{ value_json.last_success }}"
            }
            sensors[f"backup_age_hours_{repo_safe}"] = {
                "p": "sensor",
                "name": f"Backup {repo_label} Age",
                "unique_id": f"{self.device_id}_backup_age_hours_{repo_safe}",
                "unit_of_measurement": "h",
                "state_class": "measurement",
                "icon": "mdi:clock-alert-outline",
                "state_topic": repo_topic,
                "value_template": "{{ value_json.backup_age_hours }}"
            }
            sensors[f"backup_duration_seconds_{repo_safe}"] = {
                "p": "sensor",
                "name": f"Backup {repo_label} Duration",
                "unique_id": f"{self.device_id}_backup_duration_seconds_{repo_safe}",
                "unit_of_measurement": "s",
                "state_class": "measurement",
                "icon": "mdi:timer-outline",
                "state_topic": repo_topic,
                "value_template": "{{ value_json.duration_seconds }}"
            }
            sensors[f"backup_files_count_{repo_safe}"] = {
                "p": "sensor",
                "name": f"Backup {repo_label} Files",
                "unique_id": f"{self.device_id}_backup_files_count_{repo_safe}",
                "state_class": "measurement",
                "icon": "mdi:file-multiple",
                "state_topic": repo_topic,
                "value_template": "{{ value_json.files_count }}"
            }
            sensors[f"backup_original_size_mb_{repo_safe}"] = {
                "p": "sensor",
                "name": f"Backup {repo_label} Original Size",
                "unique_id": f"{self.device_id}_backup_original_size_mb_{repo_safe}",
                "unit_of_measurement": "MB",
                "state_class": "measurement",
                "icon": "mdi:database",
                "state_topic": repo_topic,
                "value_template": "{{ value_json.original_size_mb }}"
            }
            sensors[f"backup_compressed_size_mb_{repo_safe}"] = {
                "p": "sensor",
                "name": f"Backup {repo_label} Compressed Size",
                "unique_id": f"{self.device_id}_backup_compressed_size_mb_{repo_safe}",
                "unit_of_measurement": "MB",
                "state_class": "measurement",
                "icon": "mdi:archive-arrow-down",
                "state_topic": repo_topic,
                "value_template": "{{ value_json.compressed_size_mb }}"
            }
            sensors[f"backup_deduplicated_size_mb_{repo_safe}"] = {
                "p": "sensor",
                "name": f"Backup {repo_label} Deduplicated Size",
                "unique_id": f"{self.device_id}_backup_deduplicated_size_mb_{repo_safe}",
                "unit_of_measurement": "MB",
                "state_class": "measurement",
                "icon": "mdi:content-duplicate",
                "state_topic": repo_topic,
                "value_template": "{{ value_json.deduplicated_size_mb }}"
            }
            sensors[f"backup_repo_last_modified_{repo_safe}"] = {
                "p": "sensor",
                "name": f"Backup {repo_label} Repo Last Modified",
                "unique_id": f"{self.device_id}_backup_repo_last_modified_{repo_safe}",
                "icon": "mdi:calendar-clock",
                "device_class": "timestamp",
                "state_topic": repo_topic,
                "value_template": "{{ value_json.repo_last_modified }}"
            }
        return sensors

    def _get_borgmatic_state(self, repo: str) -> Dict[str, Any]:
        try:
            result = subprocess.run(
                ["borgmatic", "info", "--archive", "latest", "--repo", repo, "--json"],
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode != 0:
                self.logger.warning(
                    "borgmatic info failed for %s with code %s: %s",
                    repo,
                    result.returncode,
                    result.stderr.strip()
                )
                return {"backup_state": "failed"}

            borgmatic_data = json.loads(result.stdout)
            if not isinstance(borgmatic_data, list) or not borgmatic_data:
                self.logger.warning("Unexpected borgmatic payload for %s", repo)
                return {"backup_state": "unknown"}

            repository_data = borgmatic_data[0]
            archives = repository_data.get("archives") or []
            if not archives:
                return {"backup_state": "missing"}

            latest_archive = archives[-1]
            archive_stats = latest_archive.get("stats") or {}
            last_success = latest_archive.get("end") or latest_archive.get("start")
            last_success_datetime = self._parse_iso_datetime(last_success)
            backup_age_hours = None
            if last_success_datetime is not None:
                backup_age_hours = round((datetime.now() - last_success_datetime).total_seconds() / 3600, 2)

            payload: Dict[str, Any] = {
                "backup_state": "success",
            }
            if last_success:
                payload["last_success"] = last_success
            if backup_age_hours is not None:
                payload["backup_age_hours"] = backup_age_hours
            if latest_archive.get("duration") is not None:
                payload["duration_seconds"] = round(float(latest_archive["duration"]), 3)
            if archive_stats.get("nfiles") is not None:
                payload["files_count"] = archive_stats["nfiles"]
            if archive_stats.get("original_size") is not None:
                payload["original_size_mb"] = self._bytes_to_megabytes(archive_stats["original_size"])
            if archive_stats.get("compressed_size") is not None:
                payload["compressed_size_mb"] = self._bytes_to_megabytes(archive_stats["compressed_size"])
            if archive_stats.get("deduplicated_size") is not None:
                payload["deduplicated_size_mb"] = self._bytes_to_megabytes(archive_stats["deduplicated_size"])
            if latest_archive.get("name"):
                payload["archive_name"] = latest_archive["name"]

            repository_meta = repository_data.get("repository") or {}
            if repository_meta.get("last_modified"):
                payload["repo_last_modified"] = repository_meta["last_modified"]

            return payload
        except (json.JSONDecodeError, OSError, ValueError, subprocess.SubprocessError) as e:
            self.logger.warning(f"Could not collect borgmatic state for {repo}: {e}")
            return {"backup_state": "failed"}

    def publish_borgmatic_states(self) -> None:
        for repo in self.borgmatic or []:
            repo_safe = self._sanitize_borgmatic_repo(repo)
            if not repo_safe:
                continue

            repo_topic = f"{self.base_topic}/borgmatic_state/{repo_safe}"
            repo_payload = self._get_borgmatic_state(repo)
            self.logger.debug(f"Publishing borgmatic state to {repo_topic}: {repo_payload}")
            self.client.publish(repo_topic, json.dumps(repo_payload), qos=1, retain=True)

    def _get_component_platforms(self) -> Dict[str, str]:
        return {
            component_id: component.get("p", "sensor")
            for component_id, component in self.discovery_payload.get("cmps", {}).items()
        }

    def _load_previous_components(self) -> Dict[str, str]:
        if not self.state_file or not self.state_file.exists():
            return {}
        try:
            data = json.loads(self.state_file.read_text())
            return data.get("components", {})
        except (json.JSONDecodeError, OSError) as e:
            self.logger.warning(f"Could not read state file {self.state_file}: {e}")
            return {}

    def _save_current_components(self, components: Dict[str, str]) -> None:
        if not self.state_file:
            return
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            self.state_file.write_text(json.dumps({"components": components}, indent=2))
        except OSError as e:
            self.logger.warning(f"Could not write state file {self.state_file}: {e}")

    def _remove_components(self, components: Dict[str, str]) -> None:
        if not components:
            return

        config_topic = f"{self.discovery_prefix}/device/{self.device_id}/config"
        removal_payload = {
            "dev": self.discovery_payload.get("dev", {}),
            "o": self.discovery_payload.get("o", {}),
            "cmps": {component_id: {"p": platform} for component_id, platform in components.items()},
            "state_topic": self.state_topic,
            "availability_topic": self.availability_topic,
            "qos": 1
        }
        self.logger.info(f"Removing {len(components)} component(s) from discovery")
        self.client.publish(config_topic, json.dumps(removal_payload), retain=True)
        
    def publish_discovery(self) -> None:
        config_topic = f"{self.discovery_prefix}/device/{self.device_id}/config"
        current_components = self._get_component_platforms()
        previous_components = self._load_previous_components()
        removed_components = {
            component_id: platform
            for component_id, platform in previous_components.items()
            if component_id not in current_components
        }

        if removed_components:
            self._remove_components(removed_components)

        self.logger.info(f"Publishing discovery config to {config_topic}")
        self.client.publish(config_topic, json.dumps(self.discovery_payload), retain=True)
        self._save_current_components(current_components)

    def publish_states(self) -> None:
        state_payload: Dict[str, Any] = {}
        if self.use_defaults:
            # Use interval=0 to get non-blocking CPU measurement (already initialized in __init__)
            cpu_usage = psutil.cpu_percent(interval=0)
            memory = psutil.virtual_memory()
            memory_usage = round(memory.percent, 1)
            memory_used_gb = round(memory.used / (1024**3), 2)
            memory_total_gb = round(memory.total / (1024**3), 2)
            uptime_seconds = int(time.time() - psutil.boot_time())
            cpu_temperature = self._get_cpu_temperature()
            state_payload = state_payload | {
                "cpu_usage": cpu_usage,
                "memory_usage": memory_usage,
                "memory_used": memory_used_gb,
                "memory_total": memory_total_gb,
                "uptime_seconds": uptime_seconds
            }
            if cpu_temperature is not None:
                state_payload["cpu_temperature"] = cpu_temperature
        if self.mountpoints:    
            # Collect disk metrics for each mountpoint
            for mountpoint in self.mountpoints:
                try:
                    disk = psutil.disk_usage(mountpoint)
                    mount_safe = mountpoint.replace('/', '_').strip('_')
                    if not mount_safe:
                        mount_safe = "root"
                    
                    state_payload[f"disk_usage_{mount_safe}"] = round(disk.percent, 1)
                    state_payload[f"disk_used_{mount_safe}"] = round(disk.used / (1024**3), 2)
                    state_payload[f"disk_total_{mount_safe}"] = round(disk.total / (1024**3), 2)
                except (OSError, ValueError) as e:
                    self.logger.warning(f"Could not read disk usage for {mountpoint}: {e}")

        if self.interfaces:
            net_io = psutil.net_io_counters(pernic=True)
            current_time = time.time()
            time_delta = None
            if self.prev_net_time is not None:
                time_delta = current_time - self.prev_net_time

            for iface in self.interfaces:
                if iface not in net_io:
                    self.logger.warning(f"Network interface not found: {iface}")
                    continue

                iface_safe = iface.replace('/', '_').replace('-', '_')
                current = net_io[iface]
                prev = self.prev_net_io.get(iface)

                net_upload_mbps = 0.0
                net_download_mbps = 0.0
                if prev is not None and time_delta and time_delta > 0:
                    bytes_sent_delta = current.bytes_sent - prev.bytes_sent
                    bytes_recv_delta = current.bytes_recv - prev.bytes_recv
                    net_upload_mbps = round((bytes_sent_delta / time_delta) * 8 / (1024**2), 2)
                    net_download_mbps = round((bytes_recv_delta / time_delta) * 8 / (1024**2), 2)

                state_payload[f"net_upload_{iface_safe}"] = net_upload_mbps
                state_payload[f"net_download_{iface_safe}"] = net_download_mbps
                state_payload[f"net_sent_{iface_safe}"] = round(current.bytes_sent / (1024**3), 2)
                state_payload[f"net_recv_{iface_safe}"] = round(current.bytes_recv / (1024**3), 2)

                self.prev_net_io[iface] = current

            self.prev_net_time = current_time
        
        if self.services:
            for service in self.services:
                try:
                    result = subprocess.run(
                        ["systemctl", "is-active", service],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )
                    service_safe = service.replace('.', '_').replace('-', '_').replace('@', '_')
                    # systemctl returns "active", "inactive", "failed", etc.
                    status = result.stdout.strip()
                    state_payload[f"service_{service_safe}"] = status
                except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError) as e:
                    self.logger.warning(f"Could not check status for service {service}: {e}")
                    service_safe = service.replace('.', '_').replace('-', '_').replace('@', '_')
                    state_payload[f"service_{service_safe}"] = "unknown"
        
        self.logger.debug(f"Publishing state: {state_payload}")
        self.client.publish(self.state_topic, json.dumps(state_payload))

    def on_connect(self, client: mqtt.Client, userdata: Any, flags: Dict[str, int], rc: int) -> None:
        if rc == 0:
            self.logger.info("Connected to MQTT broker")
            self.client.subscribe("homeassistant/status")
            self.publish_discovery()
            self.publish_states()
            if self.borgmatic and self.borgmatic_interval is not None:
                self.publish_borgmatic_states()
        else:
            self.logger.error(f"Failed to connect to MQTT broker: code {rc}")

    def on_message(self, client: mqtt.Client, userdata: Any, msg: mqtt.MQTTMessage) -> None:
        if msg.topic == "homeassistant/status" and msg.payload == b"online":
            self.logger.info("Home Assistant restarted, resending discovery config")
            self.publish_discovery()

    def run(self) -> None:
        try:
            self.client = mqtt.Client(client_id=f"system2mqtt_{self.device_id}")
            self.client.will_set(self.availability_topic, "offline", retain=True)
            self.client.username_pw_set(self.mqtt_user, self.mqtt_pass)
            self.client.on_connect = self.on_connect
            self.client.on_message = self.on_message
            
            self.logger.info(f"Connecting to MQTT broker at {self.mqtt_host}:{self.mqtt_port}")
            self.client.connect(self.mqtt_host, self.mqtt_port, 60)
            self.client.loop_start()
            time.sleep(2)
            self.client.publish(self.availability_topic, "online", retain=True)
            
            self.logger.info(f"Starting monitoring loop with {self.update_interval}s interval")
            next_borgmatic_publish = time.time() + self.borgmatic_interval if self.borgmatic_interval is not None else 0.0
            while True:
                self.publish_states()
                if self.borgmatic and self.borgmatic_interval is not None:
                    now = time.time()
                    if now >= next_borgmatic_publish:
                        self.publish_borgmatic_states()
                        next_borgmatic_publish = now + self.borgmatic_interval
                time.sleep(self.update_interval)
        except KeyboardInterrupt:
            self.logger.info("Stopping System2MQTT...")
        except Exception as e:
            self.logger.error(f"Error in main loop: {e}")
        finally:
            self.client.publish(self.availability_topic, "offline", retain=True)
            self.client.loop_stop()
            self.client.disconnect()
            self.logger.info("Disconnected from MQTT broker")

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    parser = argparse.ArgumentParser(description="System2MQTT - MQTT publisher for Home Assistant")
    parser.add_argument("--host", default="localhost", help="MQTT broker host (default: localhost)")
    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port (default: 1883)")
    parser.add_argument("--user", default="", help="MQTT username")
    parser.add_argument("--pass", dest="password", default="", help="MQTT password")
    parser.add_argument("--pass-file", dest="password_file", default="", help="Read MQTT password from file")
    parser.add_argument("--interval", type=int, default=30, help="Update interval in seconds (default: 30)")
    parser.add_argument("--mountpoints", type=str, nargs="+", default=[], help="Disk mountpoints to monitor (default: /)")
    parser.add_argument("--interfaces", type=str, nargs="+", default=[], help="Network interfaces to monitor (e.g. eth0 wlan0)")
    parser.add_argument("--services", type=str, nargs="+", default=[], help="Systemd services to monitor (e.g. nginx.service docker.service)")
    parser.add_argument("--borgmatic", type=str, nargs="+", default=[], help="Borgmatic backups to monitor (e.g. backup1 backup2)")
    parser.add_argument("--borgmatic-interval", type=int, default=3600, help="Borgmatic update interval in seconds (default: 3600)")
    parser.add_argument("--state-file", default="/var/lib/system2mqtt/state.json", help="Path to discovery state file")
    parser.add_argument("--use-defaults", action="store_true", default=True, help="Enable defaults")
    args = parser.parse_args()
    
    password = args.password
    if args.password_file:
        try:
            password = Path(args.password_file).read_text(encoding='utf-8').strip()
        except OSError as exc:
            logging.error('Failed to read MQTT password file %s: %s', args.password_file, exc)
            raise SystemExit(2)
    
    monitor = SystemMonitor(
        mqtt_host=args.host,
        mqtt_port=args.port,
        mqtt_user=args.user,
        mqtt_pass=password,
        use_defaults=args.use_defaults,
        update_interval=args.interval,
        mountpoints=args.mountpoints,
        interfaces=args.interfaces,
        services=args.services,
        borgmatic=args.borgmatic,
        state_file=args.state_file,
        borgmatic_interval=args.borgmatic_interval
    )
    monitor.run()