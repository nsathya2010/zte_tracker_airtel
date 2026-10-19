"""Local endpoint probe for ZTE router profiles.

Usage:
    python tools/probe_router_endpoints.py

Configuration is loaded from `.env.f670l.local` in the repository root.
Only simple KEY=VALUE pairs are supported.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import types
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / ".env.f670l.local"


def _install_homeassistant_stub() -> None:
    """Install the minimum Home Assistant stub needed for const imports."""
    if "homeassistant.const" in sys.modules:
        return

    package = types.ModuleType("homeassistant")
    package.__path__ = []

    const_module = types.ModuleType("homeassistant.const")

    class Platform:
        SENSOR = "sensor"
        BINARY_SENSOR = "binary_sensor"
        DEVICE_TRACKER = "device_tracker"
        SWITCH = "switch"
        BUTTON = "button"

    const_module.Platform = Platform
    sys.modules["homeassistant"] = package
    sys.modules["homeassistant.const"] = const_module


def _load_zte_client_class():
    """Load zteClient directly from its file without importing the HA package."""
    package_name = "custom_components.zte_tracker"
    zteclient_package = f"{package_name}.zteclient"
    module_name = f"{zteclient_package}.zte_client"

    if package_name not in sys.modules:
        package = types.ModuleType(package_name)
        package.__path__ = [str(REPO_ROOT / "custom_components" / "zte_tracker")]
        sys.modules[package_name] = package

    if zteclient_package not in sys.modules:
        package = types.ModuleType(zteclient_package)
        package.__path__ = [
            str(REPO_ROOT / "custom_components" / "zte_tracker" / "zteclient")
        ]
        sys.modules[zteclient_package] = package

    if module_name not in sys.modules:
        file_path = (
            REPO_ROOT
            / "custom_components"
            / "zte_tracker"
            / "zteclient"
            / "zte_client.py"
        )
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        assert spec.loader is not None
        spec.loader.exec_module(module)

    return sys.modules[module_name].zteClient


def _load_env(path: Path) -> dict[str, str]:
    """Parse a simple local env file."""
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _env_bool(values: dict[str, str], key: str, default: bool) -> bool:
    value = values.get(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _print_block(title: str, payload: Any) -> None:
    print(f"\n[{title}]")
    if isinstance(payload, (dict, list)):
        print(json.dumps(payload, indent=2, sort_keys=True, default=str))
    else:
        print(payload)


def main() -> int:
    if not ENV_FILE.exists():
        print(f"Missing env file: {ENV_FILE}")
        print("Create it from .env.f670l.local.example and fill in your router credentials.")
        return 1

    env = _load_env(ENV_FILE)
    required = ["ZTE_HOST", "ZTE_USERNAME", "ZTE_PASSWORD", "ZTE_MODEL"]
    missing = [key for key in required if not env.get(key)]
    if missing:
        print(f"Missing required env keys: {', '.join(missing)}")
        return 1

    _install_homeassistant_stub()
    sys.path.insert(0, str(REPO_ROOT))
    zteClient = _load_zte_client_class()

    client = zteClient(
        env["ZTE_HOST"],
        env["ZTE_USERNAME"],
        env["ZTE_PASSWORD"],
        env["ZTE_MODEL"],
        verify_ssl=_env_bool(env, "ZTE_VERIFY_SSL", False),
        query_wan_status=_env_bool(env, "ZTE_QUERY_WAN_STATUS", True),
        query_router_details=_env_bool(env, "ZTE_QUERY_ROUTER_DETAILS", True),
        scheme=env.get("ZTE_SCHEME", "auto"),
        mesh_topology=_env_bool(env, "ZTE_MESH_TOPOLOGY", False),
    )

    _print_block(
        "config",
        {
            "host": client.host,
            "model": client.model,
            "scheme": client.scheme,
            "base_url": client.base_url,
            "query_wan_status": client.query_wan_status,
            "query_router_details": client.query_router_details,
            "mesh_topology": client.mesh_topology,
            "paths": client.paths,
        },
    )

    try:
        logged_in = client.login()
        _print_block("login", {"ok": logged_in, "statusmsg": client.statusmsg})
        if not logged_in:
            return 2

        probes = {
            "lan_devices": client.get_lan_devices,
            "wifi_devices": client.get_wifi_devices,
            "devices": client.get_devices_response,
            "wan_status": client.get_wan_status,
            "router_details": client.get_router_details,
            "pon_optical_info": client.get_pon_optical_info,
        }

        for name, probe in probes.items():
            try:
                result = probe()
                _print_block(name, result)
            except Exception as exc:  # pragma: no cover - local probe path
                _print_block(name, {"error": str(exc)})

        return 0
    finally:
        try:
            client.logout()
        except Exception as exc:  # pragma: no cover - local probe path
            _print_block("logout", {"error": str(exc)})


if __name__ == "__main__":
    raise SystemExit(main())