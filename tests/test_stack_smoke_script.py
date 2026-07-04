from __future__ import annotations

import httpx

from scripts.smoke_stack import check_health_endpoint, run_smoke_check


def test_check_health_endpoint_returns_ok_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={'status': 'ok'})

    client = httpx.Client(transport=httpx.MockTransport(handler))

    result = check_health_endpoint(client, 'http://main.test/healthz')

    assert result == {'status': 'ok'}


def test_run_smoke_check_validates_main_and_bridge_health() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url) in {'http://main.test/healthz', 'http://bridge.test/healthz'}:
            return httpx.Response(200, json={'status': 'ok'})
        return httpx.Response(404, json={'detail': 'missing'})

    client = httpx.Client(transport=httpx.MockTransport(handler))

    results = run_smoke_check(
        main_base_url='http://main.test',
        bridge_base_url='http://bridge.test',
        client=client,
    )

    assert results['main'] == {'status': 'ok'}
    assert results['bridge'] == {'status': 'ok'}
