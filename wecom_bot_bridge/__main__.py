from __future__ import annotations

import argparse

import uvicorn


def build_uvicorn_kwargs(*, host: str, port: int, log_level: str) -> dict[str, object]:
    return {
        'app': 'wecom_bot_bridge.app:create_app',
        'factory': True,
        'host': host,
        'port': port,
        'log_level': log_level,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='Run the WeCom bot bridge service.')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=9001)
    parser.add_argument('--log-level', default='info')
    args = parser.parse_args()
    uvicorn.run(**build_uvicorn_kwargs(host=args.host, port=args.port, log_level=args.log_level))


if __name__ == '__main__':
    main()
