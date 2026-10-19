"""Raw HTTP probe for ZTE router endpoints.

This script intentionally avoids importing the Home Assistant integration.
It performs the login flow with plain requests, then calls candidate
router endpoints directly and prints short summaries.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

import requests


REPO_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = REPO_ROOT / ".env.f670l.local"


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def parse_bool(values: dict[str, str], key: str, default: bool) -> bool:
    value = values.get(key)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def build_base_url(values: dict[str, str]) -> tuple[str, bool]:
    scheme = values.get("ZTE_SCHEME", "auto")
    host = values["ZTE_HOST"]
    if scheme == "auto":
        scheme = "https"
    verify_ssl = parse_bool(values, "ZTE_VERIFY_SSL", False) if scheme == "https" else False
    return f"{scheme}://{host}", verify_ssl


def parse_router_error(text: str) -> str | None:
    try:
        xml = ET.fromstring(text)
    except ET.ParseError:
        return None
    if xml.tag != "ajax_response_xml_root":
        return None
    error = xml.findtext("IF_ERRORSTR")
    if error and error not in {"SUCC", "SUCCESS", "OK"}:
        return error
    return None


def snippet(text: str, limit: int = 280) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact[:limit] + ("..." if len(compact) > limit else "")


def get(session: requests.Session, url: str, verify_ssl: bool) -> requests.Response:
    response = session.get(url, verify=verify_ssl, timeout=15)
    response.raise_for_status()
    return response


def login(values: dict[str, str]) -> tuple[requests.Session, str, bool]:
    base_url, verify_ssl = build_base_url(values)
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "DNT": "1",
        }
    )

    login_entry = get(session, f"{base_url}/?_type=loginData&_tag=login_entry", verify_ssl)
    login_entry_json = login_entry.json()
    session_token = login_entry_json.get("sess_token")
    if not session_token:
        raise RuntimeError(f"No session token in login_entry response: {login_entry.text}")

    login_token_resp = get(
        session,
        f"{base_url}/?_type=loginData&_tag=login_token&_={login_entry_json.get('time', '1')}",
        verify_ssl,
    )
    login_token_xml = ET.fromstring(login_token_resp.content)
    login_token = (login_token_xml.text or "").strip()
    if not login_token:
        raise RuntimeError(f"Empty login_token response: {login_token_resp.text}")

    password_hash = hashlib.sha256(
        f"{values['ZTE_PASSWORD']}{login_token}".encode("utf-8")
    ).hexdigest()
    login_resp = session.post(
        f"{base_url}/?_type=loginData&_tag=login_entry",
        verify=verify_ssl,
        timeout=15,
        data={
            "action": "login",
            "Username": values["ZTE_USERNAME"],
            "Password": password_hash,
            "_sessionTOKEN": session_token,
        },
    )
    login_resp.raise_for_status()
    return session, base_url, verify_ssl


def probe(session: requests.Session, base_url: str, verify_ssl: bool, title: str, view_tag: str | None, data_tag: str) -> None:
    print(f"\n[{title}]")
    if view_tag:
        view_url = f"{base_url}/?_type=menuView&_tag={view_tag}&_=1"
        try:
            view_resp = get(session, view_url, verify_ssl)
            print(f"view: {view_resp.status_code} {view_tag}")
        except Exception as exc:
            print(f"view_error: {exc}")
            return
    data_url = f"{base_url}/?_type=menuData&_tag={data_tag}&_=2"
    try:
        data_resp = get(session, data_url, verify_ssl)
        router_error = parse_router_error(data_resp.text)
        print(f"data: {data_resp.status_code} {data_tag}")
        print(f"router_error: {router_error or 'none'}")
        print(f"body: {snippet(data_resp.text)}")
    except Exception as exc:
        print(f"data_error: {exc}")


def main() -> int:
    if not ENV_FILE.exists():
        print(f"Missing env file: {ENV_FILE}")
        return 1
    values = load_env(ENV_FILE)
    required = ["ZTE_HOST", "ZTE_USERNAME", "ZTE_PASSWORD"]
    missing = [key for key in required if not values.get(key)]
    if missing:
        print(f"Missing required env keys: {', '.join(missing)}")
        return 1

    session = None
    try:
        session, base_url, verify_ssl = login(values)
        print("[login]")
        print(f"base_url: {base_url}")
        print("login: ok")

        probe(session, base_url, verify_ssl, "lan", "localNetStatus", "accessdev_landevs_lua.lua")
        probe(session, base_url, verify_ssl, "wifi", None, "wlan_client_stat_lua.lua")
        probe(session, base_url, verify_ssl, "wan_internetstatus", "ethWanStatus&Menu3Location=0", "wan_internetstatus_lua.lua&TypeUplink=2&pageType=1")
        probe(session, base_url, verify_ssl, "wan_internet", "ethWanStatus&Menu3Location=0", "wan_internet_lua.lua&TypeUplink=2&pageType=1")
        probe(session, base_url, verify_ssl, "pon_optical", "ponopticalinfo&Menu3Location=0", "optical_info_lua.lua")
        return 0
    finally:
        if session is not None:
            session.close()


if __name__ == "__main__":
    raise SystemExit(main())