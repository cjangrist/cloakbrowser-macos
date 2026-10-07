"""Real-loopback regressions for the source-built CDP gateway."""
import asyncio
import importlib.machinery
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer

SOURCE = Path(os.environ.get('UPSTREAM_CONTEXT', 'upstream')).resolve() / 'bin/cloakserve'
loader = importlib.machinery.SourceFileLoader('recovery_cloakserve', str(SOURCE))
spec = importlib.util.spec_from_loader(loader.name, loader)
assert spec is not None
module = importlib.util.module_from_spec(spec)
sys.modules[loader.name] = module
loader.exec_module(module)


@pytest.mark.parametrize('seed', [None, '18929'])
def test_stale_guid_rejects_upgrade_and_rediscovery_recovers(seed):
    async def exercise():
        current = 'before-crash'
        active = 0

        async def version(request):
            return web.json_response({'webSocketDebuggerUrl': f'ws://127.0.0.1:{backend.port}/devtools/browser/{current}'})

        async def cdp(request):
            nonlocal active
            if request.match_info['guid'] != current:
                raise web.HTTPNotFound()
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            active += 1
            try:
                async for message in ws:
                    request_body = json.loads(message.data)
                    await ws.send_json({'id': request_body['id'], 'result': {'product': 'Chrome/test'}})
            finally:
                active -= 1
            return ws

        backend_app = web.Application()
        backend_app.router.add_get('/json/version', version)
        backend_app.router.add_get('/devtools/browser/{guid}', cdp)
        async with TestServer(backend_app) as backend:
            pool = module.ChromePool('/unused', [], True, default_seed='18929')
            pool.get_or_launch = AsyncMock(return_value=SimpleNamespace(cdp_port=backend.port))
            gateway_app = web.Application()
            gateway_app['pool'] = pool
            gateway_app['port'] = 9222
            gateway_app.router.add_get('/json/version', module.handle_json_version)
            gateway_app.router.add_get('/devtools/{path:.*}', module.handle_ws_default)
            gateway_app.router.add_get('/fingerprint/{seed}/devtools/{path:.*}', module.handle_ws_seed)
            async with TestServer(gateway_app) as gateway, aiohttp.ClientSession() as client:
                suffix = '' if seed is None else '?fingerprint=' + seed

                async def discover():
                    async with client.get(gateway.make_url('/json/version' + suffix)) as response:
                        return (await response.json())['webSocketDebuggerUrl']

                stale = await discover()
                current = 'after-crash'

                async def reconnect(index):
                    # Mirror CRW's retry boundary: only a failed handshake clears cache.
                    with pytest.raises(aiohttp.WSServerHandshakeError) as error:
                        await client.ws_connect(stale)
                    assert error.value.status == 502
                    fresh = await discover()
                    assert fresh != stale
                    async with client.ws_connect(fresh) as ws:
                        await ws.send_json({'id': index, 'method': 'Browser.getVersion'})
                        message = await ws.receive(timeout=2)
                        assert json.loads(message.data)['result']['product'] == 'Chrome/test'

                await asyncio.gather(*(reconnect(i) for i in range(8)))
                pumps = []
                for _ in range(50):
                    pumps = [t for t in asyncio.all_tasks() if t.get_name() in ('c2d', 'd2c') and not t.done()]
                    if not pumps and active == 0:
                        break
                    await asyncio.sleep(0.01)
                assert not pumps and active == 0
                assert not pool._connections
    asyncio.run(exercise())


def test_dead_process_cleanup_keeps_canonical_lock_and_profile(tmp_path):
    async def exercise():
        pool = module.ChromePool('/unused', [], True, data_dir=str(tmp_path), preserve_profiles=True)
        key = '18929'
        lock = pool._get_lock(key)
        profile = tmp_path / key
        profile.mkdir()
        marker = profile / 'sentinel'
        marker.write_text('preserve')
        pool._processes[key] = SimpleNamespace(process=SimpleNamespace(poll=lambda: 1), user_data_dir=str(profile))
        async with lock:
            await pool._cleanup_process(key)
            assert pool._get_lock(key) is lock
        assert marker.read_text() == 'preserve'
    asyncio.run(exercise())


def test_cancelled_launch_reaps_unregistered_process(tmp_path):
    async def exercise():
        pool = module.ChromePool('/unused', [], True, data_dir=str(tmp_path), preserve_profiles=True)
        killed = []
        waited = []
        process = SimpleNamespace(poll=lambda: None, kill=lambda: killed.append(True), wait=lambda timeout: waited.append(timeout))
        waiting = asyncio.Event()

        async def blocked(port):
            waiting.set()
            await asyncio.Event().wait()

        with patch.object(module.subprocess, 'Popen', return_value=process), patch.object(pool, '_wait_for_cdp', side_effect=blocked), patch.object(module, 'seed_widevine_hint'):
            task = asyncio.create_task(pool.get_or_launch('18929'))
            await waiting.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert killed == [True] and waited == [5]
        assert not pool._processes
    asyncio.run(exercise())
