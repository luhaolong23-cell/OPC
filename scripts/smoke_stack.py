from __future__ import annotations

import argparse
import json

import httpx


def check_health_endpoint(client: httpx.Client, url: str) -> dict[str, object]:
    response = client.get(url, timeout=5.0)
    response.raise_for_status()
    payload = response.json()
    if payload.get('status') != 'ok':
        raise RuntimeError(f'unexpected health payload from {url}: {payload}')
    return payload


def run_smoke_check(*, main_base_url: str, bridge_base_url: str, client: httpx.Client | None = None) -> dict[str, dict[str, object]]:
    http_client = client or httpx.Client()
    return {
        'main': check_health_endpoint(http_client, f"{main_base_url.rstrip('/')}/healthz"),
        'bridge': check_health_endpoint(http_client, f"{bridge_base_url.rstrip('/')}/healthz"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='Smoke-check the OPC main service and WeCom bridge health endpoints.')
    parser.add_argument('--main-base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--bridge-base-url', default='http://127.0.0.1:9001')
    args = parser.parse_args()
    results = run_smoke_check(main_base_url=args.main_base_url, bridge_base_url=args.bridge_base_url)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
