from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


ENV_URLS = {
    "PRU": {
        "token": "https://pid-pru.segittur.es/auth/realms/onesaitplatform/protocol/openid-connect/token",
        "destinations": "https://pid-pru.segittur.es/gravitee/gateway/c6_api_destinations/v1/destinationByUser",
    },
    "PRE": {
        "token": "https://pid-pre.segittur.es/auth/realms/onesaitplatform/protocol/openid-connect/token",
        "destinations": "https://pid-pre.segittur.es/gravitee/gateway/c6_api_destinations/v1/destinationByUser",
    },
    "PRO": {
        "token": "https://pid.segittur.es/auth/realms/onesaitplatform/protocol/openid-connect/token",
        "destinations": "https://pid.segittur.es/gravitee/gateway/c6_api_destinations/v1/destinationByUser",
    },
}


def main() -> int:
    env = os.getenv("PID_ENV", "PRE").upper()
    if env not in ENV_URLS:
        raise SystemExit(f"PID_ENV invalido: {env}. Usa PRU, PRE o PRO.")
    access_token = os.getenv("PID_ACCESS_TOKEN")
    username = os.getenv("PID_USERNAME")
    password = os.getenv("PID_PASSWORD")
    client_id = os.getenv("PID_CLIENT_ID", "CMS_SEMANTICO")
    if access_token:
        token = access_token
    elif not username or not password:
        raise SystemExit("Faltan PID_USERNAME y/o PID_PASSWORD.")
    else:
        try:
            token = get_token(ENV_URLS[env]["token"], username, password, client_id)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            print(f"Error obteniendo token: HTTP {exc.code}")
            print(body)
            print(f"client_id usado: {client_id}")
            return 1
    print(f"Entorno: {env}")
    req = urllib.request.Request(
        ENV_URLS[env]["destinations"],
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        print(f"HTTP {exc.code}")
        print(body)
        return 1

    try:
        print(json.dumps(json.loads(body), ensure_ascii=False, indent=2))
    except json.JSONDecodeError:
        print(body)
    return 0


def get_token(token_url: str, username: str, password: str, client_id: str) -> str:
    body = urllib.parse.urlencode(
        {
            "username": username,
            "password": password,
            "grant_type": "password",
            "client_id": client_id,
            "scope": "openid",
        }
    ).encode()
    req = urllib.request.Request(
        token_url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        payload = json.loads(response.read().decode("utf-8"))
    token = payload.get("access_token")
    if not token:
        raise SystemExit(f"No se ha recibido access_token: {payload}")
    return token


if __name__ == "__main__":
    sys.exit(main())
