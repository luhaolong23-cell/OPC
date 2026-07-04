from __future__ import annotations

import argparse
import os

REQUIRED_ENV_VARS = [
    'OPC_INTERNAL_TOKEN',
    'WECOM_BRIDGE_NOTIFY_TOKEN',
    'WECOM_BOT_ID',
    'WECOM_BOT_SECRET',
    'OPC_BASE_URL',
]
PLACEHOLDER_PREFIX = 'replace-with-'


def collect_missing_env_vars(env: dict[str, str | None]) -> list[str]:
    missing: list[str] = []
    for name in REQUIRED_ENV_VARS:
        value = env.get(name)
        if not value or value.startswith(PLACEHOLDER_PREFIX):
            missing.append(name)
    return missing


def main() -> None:
    parser = argparse.ArgumentParser(description='Preflight check for the OPC main service and WeCom bridge environment variables.')
    parser.parse_args()
    missing = collect_missing_env_vars(dict(os.environ))
    if missing:
        raise SystemExit('Missing required environment variables: ' + ', '.join(missing))
    print('Preflight OK')


if __name__ == '__main__':
    main()
