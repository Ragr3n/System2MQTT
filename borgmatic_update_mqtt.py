#!/usr/bin/env python3

import argparse
import json
import logging
import socket

import paho.mqtt.client as mqtt


def sanitize_repo(repo: str) -> str:
    return repo.replace('/', '_').replace('-', '_')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Update borgmatic_latest_state_* via MQTT'
    )
    parser.add_argument('--host', default='localhost', help='MQTT broker host')
    parser.add_argument('--port', type=int, default=1883, help='MQTT broker port')
    parser.add_argument('--user', default='', help='MQTT username')
    parser.add_argument('--pass', dest='password', default='', help='MQTT password')
    parser.add_argument(
        '--device-id',
        default=socket.gethostname().replace('.', '_').replace('-', '_'),
        help='Device id used by system2mqtt (default: sanitized hostname)',
    )
    parser.add_argument(
        '--base-topic',
        default='system2mqtt',
        help='Base MQTT topic namespace (default: system2mqtt)',
    )
    parser.add_argument('--repo', required=True, help='Borgmatic repo name/key')
    parser.add_argument(
        '--state',
        required=True,
        help='Latest borgmatic state (e.g. running, completed, error)',
    )
    parser.add_argument('--qos', type=int, choices=[0, 1, 2], default=1, help='MQTT QoS')
    parser.add_argument(
        '--retain',
        action='store_true',
        help='Retain published state payload',
    )
    parser.add_argument(
        '--log-level',
        default='INFO',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='Logging level',
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format='%(asctime)s - %(levelname)s - %(message)s',
    )

    repo_safe = sanitize_repo(args.repo)
    if not repo_safe:
        logging.error('Repo value is empty after sanitization')
        return 2

    state_topic = f"{args.base_topic}/{args.device_id}/borgmatic_state/{repo_safe}"
    payload = {
        f"borgmatic_latest_state_{repo_safe}": args.state,
    }

    client = mqtt.Client(client_id=f"borgmatic_update_{args.device_id}_{repo_safe}")
    if args.user:
        client.username_pw_set(args.user, args.password)

    try:
        logging.info('Connecting to MQTT broker %s:%s', args.host, args.port)
        client.connect(args.host, args.port, keepalive=30)
        client.publish(state_topic, json.dumps(payload), qos=args.qos, retain=args.retain)
        client.disconnect()
        logging.info('Published borgmatic update to %s: %s', state_topic, payload)
        return 0
    except Exception as exc:
        logging.error('Failed to publish borgmatic update: %s', exc)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
