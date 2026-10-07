#!/usr/bin/env python3
"""Fault-inject real Chromium; prove rediscovery without restarting CloakServe."""
import asyncio
import json
import os
import signal
import time
from pathlib import Path

import aiohttp

BASE = 'http://127.0.0.1:9222'
SEED = '18929'


async def version(client):
    async with client.get(BASE + '/json/version', timeout=aiohttp.ClientTimeout(total=15)) as response:
        response.raise_for_status()
        return (await response.json())['webSocketDebuggerUrl']


async def status(client):
    async with client.get(BASE + '/') as response:
        return await response.json()


async def rpc(ws, method, params=None, id=1):
    await ws.send_json({'id': id, 'method': method, 'params': params or {}})
    while True:
        message = await ws.receive(timeout=5)
        assert message.type == aiohttp.WSMsgType.TEXT, message.type
        data = json.loads(message.data)
        if data.get('id') == id:
            assert 'error' not in data, data
            return data['result']


async def main():
    marker = Path(os.environ.get('CLOAKSERVE_DATA_DIR', '/root/.cloakbrowser/profiles/macos')) / SEED / '.cdp-recovery-sentinel'
    async with aiohttp.ClientSession() as client:
        for mode in ('graceful', 'crash', 'crash'):
            old_url = await version(client)
            before = await status(client)
            old_pid = before['processes'][SEED]['pid']
            marker.write_text('preserved')
            began = time.monotonic()
            if mode == 'graceful':
                async with client.ws_connect(old_url) as ws:
                    await ws.send_json({'id': 1, 'method': 'Browser.close'})
                    await ws.receive(timeout=5)
                for _ in range(100):
                    if SEED not in (await status(client))['processes']:
                        break
                    await asyncio.sleep(0.05)
            else:
                os.kill(old_pid, signal.SIGKILL)
                await asyncio.sleep(0.05)
            # Reconnection to the cached ID must fail before upgrade, not appear
            # connected and then close. The request also exercises pool respawn.
            try:
                async with client.ws_connect(old_url):
                    raise AssertionError('Obsolete CDP endpoint accepted its upgrade')
            except aiohttp.WSServerHandshakeError as error:
                assert error.status == 502, error.status
            fresh_url = await version(client)
            assert fresh_url != old_url

            async def reconnect(index):
                async with client.ws_connect(fresh_url) as ws:
                    browser = await rpc(ws, 'Browser.getVersion', id=index * 3 + 1)
                    assert browser.get('product')
                    context = await rpc(ws, 'Target.createBrowserContext', id=index * 3 + 2)
                    await rpc(ws, 'Target.disposeBrowserContext', {'browserContextId': context['browserContextId']}, id=index * 3 + 3)

            await asyncio.gather(*(reconnect(i) for i in range(8)))
            after = await status(client)
            assert after['processes'][SEED]['pid'] != old_pid
            assert marker.read_text() == 'preserved'
            print(json.dumps({'fault': mode, 'clients': 8, 'browser_pid_changed': True, 'profile_preserved': True, 'recovery_seconds': round(time.monotonic() - began, 3)}), flush=True)
        marker.unlink()


if __name__ == '__main__':
    asyncio.run(main())
