#!/usr/bin/env python3
"""
Raxus Agent — agent léger installable sur n'importe quel serveur Linux.
Dépendances minimales : psutil, requests, cryptography
Usage : python raxus_agent.py [--config /etc/raxus/agent.yaml]
"""
import argparse
import hashlib
import hmac
import json
import logging
import os
import platform
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List

import psutil
import requests
import yaml

# ── Logging ───────────────────────────────────────────────────
logging.basicConfig(
    filename="/var/log/raxus-agent.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
log = logging.getLogger("raxus-agent")

# ── Config ────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "server_id": platform.node(),
    "raxus_url": "http://localhost:8000",
    "secret_key": "change-me",
    "interval_seconds": 30,
    "command_poll_seconds": 10,
}

# ── Allowed commands whitelist ────────────────────────────────
ALLOWED_COMMANDS = {
    "disk_usage": lambda: {
        m.mountpoint: {"total": psutil.disk_usage(m.mountpoint).total,
                       "used": psutil.disk_usage(m.mountpoint).used,
                       "free": psutil.disk_usage(m.mountpoint).free,
                       "percent": psutil.disk_usage(m.mountpoint).percent}
        for m in psutil.disk_partitions() if m.fstype
    },
    "top_processes": lambda: [
        {"pid": p.pid, "name": p.name(), "cpu": p.cpu_percent(), "mem": p.memory_percent()}
        for p in sorted(psutil.process_iter(["pid","name","cpu_percent","memory_percent"]),
                        key=lambda x: x.cpu_percent() or 0, reverse=True)[:10]
    ],
    "read_log": lambda: _read_system_log(),
    "uptime": lambda: {"uptime_seconds": int(time.time() - psutil.boot_time())},
}


def _read_system_log() -> List[str]:
    log_paths = ["/var/log/syslog", "/var/log/messages", "/var/log/system.log"]
    for path in log_paths:
        if Path(path).exists():
            try:
                with open(path) as f:
                    return f.readlines()[-50:]
            except Exception:
                pass
    return ["Log file not accessible"]


# ── HMAC Auth ─────────────────────────────────────────────────
def _sign_request(secret_key: str, body: str) -> Dict[str, str]:
    ts = str(int(time.time()))
    sig = hmac.new(
        secret_key.encode(),
        (ts + body).encode(),
        hashlib.sha256,
    ).hexdigest()
    return {"X-Raxus-Signature": sig, "X-Raxus-Timestamp": ts}


def _post(url: str, data: Dict, config: Dict) -> bool:
    body = json.dumps(data, default=str)
    headers = {
        "Content-Type": "application/json",
        "X-Raxus-Agent-ID": config["server_id"],
        **_sign_request(config["secret_key"], body),
    }
    for attempt in range(3):
        try:
            r = requests.post(url, data=body, headers=headers, timeout=10)
            return r.status_code < 400
        except Exception as e:
            log.warning(f"POST failed (attempt {attempt+1}): {e}")
            time.sleep(2 ** attempt)
    return False


def _get(url: str, config: Dict) -> Any:
    ts = str(int(time.time()))
    sig = hmac.new(config["secret_key"].encode(), ts.encode(), hashlib.sha256).hexdigest()
    headers = {
        "X-Raxus-Agent-ID": config["server_id"],
        "X-Raxus-Signature": sig,
        "X-Raxus-Timestamp": ts,
    }
    try:
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        log.warning(f"GET failed: {e}")
    return None


# ── Metrics collection ────────────────────────────────────────
def collect_metrics(config: Dict) -> Dict:
    cpu = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory()
    disks = []
    for part in psutil.disk_partitions():
        if not part.fstype:
            continue
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append({
                "mount": part.mountpoint,
                "total_gb": round(usage.total / 1e9, 2),
                "used_gb": round(usage.used / 1e9, 2),
                "free_gb": round(usage.free / 1e9, 2),
                "percent": usage.percent,
            })
        except PermissionError:
            pass
    net = psutil.net_io_counters()
    load = os.getloadavg() if hasattr(os, "getloadavg") else [0, 0, 0]
    procs = len(psutil.pids())

    return {
        "server_id": config["server_id"],
        "hostname": platform.node(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cpu": {
            "percent": cpu,
            "count": psutil.cpu_count(),
            "freq_mhz": round(psutil.cpu_freq().current, 1) if psutil.cpu_freq() else 0,
        },
        "memory": {
            "total_mb": round(mem.total / 1e6),
            "used_mb": round(mem.used / 1e6),
            "available_mb": round(mem.available / 1e6),
            "percent": mem.percent,
        },
        "disk": disks,
        "network": {
            "bytes_sent": net.bytes_sent,
            "bytes_recv": net.bytes_recv,
            "packets_sent": net.packets_sent,
            "packets_recv": net.packets_recv,
        },
        "load_average": [round(l, 2) for l in load],
        "processes": {"total": procs},
        "uptime_seconds": int(time.time() - psutil.boot_time()),
    }


# ── Command polling ───────────────────────────────────────────
_executed_commands = set()  # Idempotency

def poll_commands(config: Dict):
    url = f"{config['raxus_url']}/agents/{config['server_id']}/commands"
    commands = _get(url, config)
    if not isinstance(commands, list):
        return
    for cmd in commands:
        cmd_id = cmd.get("command_id")
        cmd_name = cmd.get("command")
        if not cmd_id or cmd_id in _executed_commands:
            continue
        if cmd_name not in ALLOWED_COMMANDS:
            log.warning(f"Command not allowed: {cmd_name}")
            continue
        _executed_commands.add(cmd_id)
        try:
            result = ALLOWED_COMMANDS[cmd_name]()
            status = "success"
        except Exception as e:
            result = str(e)
            status = "error"
        _post(
            f"{config['raxus_url']}/agents/{config['server_id']}/results",
            {"command_id": cmd_id, "command": cmd_name, "status": status, "result": result},
            config,
        )


# ── Main loop ─────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="/etc/raxus/agent.yaml")
    args = parser.parse_args()

    config = {**DEFAULT_CONFIG}
    config_path = Path(args.config)
    if config_path.exists():
        with open(config_path) as f:
            config.update(yaml.safe_load(f) or {})

    log.info(f"Raxus Agent starting | server_id={config['server_id']} | url={config['raxus_url']}")

    last_metrics = 0
    last_commands = 0

    while True:
        now = time.time()

        # Heartbeat + metrics every interval_seconds
        if now - last_metrics >= config["interval_seconds"]:
            try:
                metrics = collect_metrics(config)
                ok = _post(f"{config['raxus_url']}/agents/{config['server_id']}/metrics", metrics, config)
                _post(f"{config['raxus_url']}/agents/{config['server_id']}/heartbeat",
                      {"status": "ok", "version": "1.0.0", "uptime": metrics["uptime_seconds"]}, config)
                log.info(f"Metrics sent (ok={ok}) cpu={metrics['cpu']['percent']}%")
            except Exception as e:
                log.error(f"Metrics error: {e}")
            last_metrics = now

        # Command polling every command_poll_seconds
        if now - last_commands >= config.get("command_poll_seconds", 10):
            try:
                poll_commands(config)
            except Exception as e:
                log.error(f"Command poll error: {e}")
            last_commands = now

        time.sleep(1)


if __name__ == "__main__":
    main()
