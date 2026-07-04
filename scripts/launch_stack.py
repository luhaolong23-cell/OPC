from __future__ import annotations

import argparse
import os
import subprocess

from scripts.preflight_stack import collect_missing_env_vars



def build_commands(*, main_host: str, main_port: int, bridge_host: str, bridge_port: int) -> dict[str, list[str]]:
    return {
        'main': ['python3', '-m', 'uvicorn', 'main:create_app', '--factory', '--host', main_host, '--port', str(main_port)],
        'bridge': ['python3', '-m', 'wecom_bot_bridge', '--host', bridge_host, '--port', str(bridge_port)],
    }



def main() -> None:
    parser = argparse.ArgumentParser(description='Launch the OPC main service and WeCom bridge after env preflight.')
    parser.add_argument('--main-host', default='0.0.0.0')
    parser.add_argument('--main-port', type=int, default=8000)
    parser.add_argument('--bridge-host', default='0.0.0.0')
    parser.add_argument('--bridge-port', type=int, default=9001)
    parser.add_argument('--print-only', action='store_true')
    args = parser.parse_args()

    missing = collect_missing_env_vars(dict(os.environ))
    if missing:
        raise SystemExit('Missing required environment variables: ' + ', '.join(missing))

    commands = build_commands(
        main_host=args.main_host,
        main_port=args.main_port,
        bridge_host=args.bridge_host,
        bridge_port=args.bridge_port,
    )
    if args.print_only:
        for name, command in commands.items():
            print(name + ': ' + ' '.join(command))
        return

    main_proc = subprocess.Popen(commands['main'])
    try:
        bridge_proc = subprocess.Popen(commands['bridge'])
    except Exception:
        main_proc.terminate()
        raise

    print(f'main pid={main_proc.pid}')
    print(f'bridge pid={bridge_proc.pid}')
