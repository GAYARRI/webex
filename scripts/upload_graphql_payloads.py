from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ENV_URLS = {
    "PRU": {
        "token": "https://pid-pru.segittur.es/auth/realms/onesaitplatform/protocol/openid-connect/token",
        "graphql": "https://pid-pru.segittur.es/graphql",
    },
    "PRE": {
        "token": "https://pid-pre.segittur.es/auth/realms/onesaitplatform/protocol/openid-connect/token",
        "graphql": "https://pid-pre.segittur.es/graphql",
    },
    "PRO": {
        "token": "https://pid.segittur.es/auth/realms/onesaitplatform/protocol/openid-connect/token",
        "graphql": "https://pid.segittur.es/graphql",
    },
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Carga payloads GraphQL en la PID.")
    parser.add_argument("input", nargs="?", help="JSON con items [{query, variables}].")
    parser.add_argument("--env", choices=ENV_URLS, default=os.getenv("PID_ENV", "PRE"))
    parser.add_argument("--client-id", default=os.getenv("PID_CLIENT_ID", "CMS_SEMANTICO"))
    parser.add_argument("--username", default=os.getenv("PID_USERNAME"))
    parser.add_argument("--password", default=os.getenv("PID_PASSWORD"))
    parser.add_argument("--access-token", default=os.getenv("PID_ACCESS_TOKEN"))
    parser.add_argument("--token-url", default=os.getenv("PID_TOKEN_URL"))
    parser.add_argument("--graphql-url", default=os.getenv("PID_GRAPHQL_URL"))
    parser.add_argument("--output-log", default="", help="Ruta del log JSONL.")
    parser.add_argument("--dti", default="", help="Sobrescribe variables.dti antes de enviar.")
    parser.add_argument("--limit", type=int, default=0, help="Maximo de items a enviar.")
    parser.add_argument("--sleep", type=float, default=0.0, help="Pausa entre peticiones, en segundos.")
    parser.add_argument("--dry-run", action="store_true", help="Valida el archivo sin enviar nada.")
    parser.add_argument("--auth-only", action="store_true", help="Obtiene token y termina sin cargar datos.")
    parser.add_argument(
        "--inline-objects",
        action="store_true",
        help="En RefInput con object, elimina uri/externalId del wrapper para forzar creacion anidada.",
    )
    parser.add_argument(
        "--drop-related-to",
        action="store_true",
        help="Elimina relatedTo para evitar validacion de URIs externas no existentes en Virtuoso.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.input and not args.auth_only:
        raise SystemExit("Falta el archivo de entrada, salvo que uses --auth-only.")

    if args.auth_only:
        if args.access_token:
            print(f"Token recibido por parametro/env. Entorno={args.env}")
            print(f"Access token preview: {args.access_token[:24]}...")
            return 0
        if not args.username or not args.password:
            raise SystemExit("Faltan PID_USERNAME y/o PID_PASSWORD.")
        token_url = args.token_url or ENV_URLS[args.env]["token"]
        response = get_token_response(token_url, args.username, args.password, args.client_id)
        token = response.get("access_token", "")
        print(f"Token OK. Entorno={args.env} Client ID={args.client_id}")
        print(f"Token type: {response.get('token_type', 'n/d')}")
        print(f"Expires in: {response.get('expires_in', 'n/d')}")
        print(f"Scope: {response.get('scope', 'n/d')}")
        print(f"Access token preview: {token[:24]}...")
        return 0

    input_path = Path(args.input)
    data = json.loads(input_path.read_text(encoding="utf-8"))
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise SystemExit("El archivo debe contener una lista o un objeto con clave 'items'.")
    if args.limit:
        items = items[: args.limit]
    if args.dti:
        for item in items:
            item.setdefault("variables", {})["dti"] = args.dti
    if args.inline_objects:
        items = [inline_ref_objects(item) for item in items]
    if args.drop_related_to:
        items = [drop_key_recursive(item, "relatedTo") for item in items]

    invalid = [idx for idx, item in enumerate(items) if not item.get("query") or not item.get("variables")]
    if invalid:
        raise SystemExit(f"Items invalidos sin query/variables: {invalid[:10]}")

    print(f"Archivo: {input_path}")
    print(f"Items a cargar: {len(items)}")
    print(f"Entorno: {args.env}")
    print(f"GraphQL: {args.graphql_url or ENV_URLS[args.env]['graphql']}")
    if args.dry_run:
        print("Dry-run OK: no se ha enviado ninguna peticion.")
        return 0

    if args.access_token:
        token = args.access_token
    elif not args.username or not args.password:
        raise SystemExit("Faltan PID_USERNAME y/o PID_PASSWORD.")
    else:
        token_url = args.token_url or ENV_URLS[args.env]["token"]
        token = get_token(token_url, args.username, args.password, args.client_id)
    graphql_url = args.graphql_url or ENV_URLS[args.env]["graphql"]

    log_path = Path(args.output_log) if args.output_log else input_path.with_suffix(".upload.jsonl")
    ok_count = 0
    error_count = 0
    with log_path.open("w", encoding="utf-8") as log:
        for idx, item in enumerate(items, 1):
            result = send_graphql(graphql_url, token, item)
            result.update(
                {
                    "index": idx,
                    "entity": data.get("metadata", [{}] * len(items))[idx - 1].get("entity")
                    if isinstance(data, dict)
                    else None,
                }
            )
            log.write(json.dumps(result, ensure_ascii=False) + "\n")
            if result["ok"]:
                ok_count += 1
            else:
                error_count += 1
            print(f"{idx}/{len(items)} {'OK' if result['ok'] else 'ERROR'} {result.get('entity') or ''}")
            if args.sleep:
                time.sleep(args.sleep)

    print(f"Finalizado. OK={ok_count} ERROR={error_count} Log={log_path}")
    return 1 if error_count else 0


def get_token(token_url: str, username: str, password: str, client_id: str) -> str:
    response = get_token_response(token_url, username, password, client_id)
    token = response.get("access_token")
    if not token:
        raise SystemExit(f"No se ha recibido access_token: {response}")
    return token


def get_token_response(token_url: str, username: str, password: str, client_id: str) -> dict[str, Any]:
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
    try:
        response = request_json(req)
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(
            f"No se pudo obtener token. HTTP {exc.code}: {error_body}"
        ) from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"No se pudo conectar con el token endpoint: {exc}") from exc
    return response


def send_graphql(graphql_url: str, token: str, item: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps({"query": item["query"], "variables": item["variables"]}).encode()
    req = urllib.request.Request(
        graphql_url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        response = request_json(req)
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "status": exc.code, "error": error_body}
    except urllib.error.URLError as exc:
        return {"ok": False, "error": str(exc)}
    return {"ok": not response.get("errors"), "response": response}


def inline_ref_objects(value: Any) -> Any:
    if isinstance(value, list):
        return [inline_ref_objects(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: inline_ref_objects(item) for key, item in value.items()}
    if "object" in result:
        result.pop("uri", None)
        result.pop("externalId", None)
    return result


def drop_key_recursive(value: Any, key_to_drop: str) -> Any:
    if isinstance(value, list):
        return [drop_key_recursive(item, key_to_drop) for item in value]
    if not isinstance(value, dict):
        return value
    return {
        key: drop_key_recursive(item, key_to_drop)
        for key, item in value.items()
        if key != key_to_drop
    }


def request_json(req: urllib.request.Request) -> dict[str, Any]:
    with urllib.request.urlopen(req, timeout=60) as response:
        raw = response.read().decode("utf-8")
    return json.loads(raw)


if __name__ == "__main__":
    sys.exit(main())
