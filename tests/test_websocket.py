import asyncio
import json
from pathlib import Path
import struct
import subprocess
import unittest

from aiohttp import ClientSession, WSMsgType, web
from protocol import HEADER, RECORD, decode_packet, acknowledgement
from server import Bridge, make_app

ROOT = Path(__file__).resolve().parents[1]


def packet(seq, *records):
    return HEADER.pack(1, 0, len(records), seq) + b''.join(RECORD.pack(*r) for r in records)


class BinaryProtocolTests(unittest.TestCase):
    def test_javascript_encoder_matches_python_decoder(self):
        code = """
const vm=require('node:vm'),fs=require('node:fs');
const ctx={window:{}};vm.createContext(ctx);
vm.runInContext(fs.readFileSync('web/transport.js','utf8'),ctx);
process.stdout.write(Buffer.from(ctx.window.encodePenPacket([{type:'move',x:.25,y:.75,pressure:.6,buttons:1,tiltX:-45.25,tiltY:89.99}],42)));
"""
        binary = subprocess.check_output(['node', '-e', code], cwd=ROOT)
        self.assertEqual(len(binary), 20)
        seq, events = decode_packet(binary)
        self.assertEqual(seq, 42)
        e = events[0]
        self.assertEqual(e['type'], 'move')
        self.assertAlmostEqual(e['x'], .25, delta=1/65535)
        self.assertAlmostEqual(e['pressure'], .6, delta=1/65535)
        self.assertEqual((e['tiltX'], e['tiltY']), (-45.25, 89.99))

    def test_truncated_and_unknown_packets_rejected(self):
        for binary in (b'', HEADER.pack(2, 0, 0, 1), HEADER.pack(1, 0, 1, 1),
                       packet(1, (99, 0, 0, 0, 0, 0, 0))):
            with self.assertRaises(ValueError): decode_packet(binary)


class WebSocketTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bridge = Bridge(dry_run=True, persist=False, screen_size=(1920, 1080))
        self.runner = web.AppRunner(make_app(self.bridge))
        await self.runner.setup()
        site = web.TCPSite(self.runner, '127.0.0.1', 0)
        await site.start()
        self.url = 'http://127.0.0.1:' + str(site._server.sockets[0].getsockname()[1])
        self.client = ClientSession()
        self.sockets = []

    async def asyncTearDown(self):
        for ws in self.sockets: await ws.close()
        await self.client.close()
        await self.runner.cleanup()

    async def connect(self):
        ws = await self.client.ws_connect(self.url+'/ws')
        self.sockets.append(ws)
        await ws.send_json(dict(type='hello', version=1, ratio=1.6))
        self.assertEqual((await ws.receive_json())['type'], 'ready')
        return ws

    async def test_binary_input_ack_and_close_releases_pen(self):
        ws = await self.connect()
        binary = packet(0, (2, 1, 16384, 32768, 40000, -2000, 3000))
        await ws.send_bytes(binary)
        reply = await ws.receive()
        self.assertEqual(reply.type, WSMsgType.BINARY)
        self.assertEqual(reply.data, acknowledgement(0))
        self.assertTrue(self.bridge.down)
        self.assertAlmostEqual(self.bridge.last['pressure'], 40000/65535)
        await ws.close()
        for _ in range(20):
            if self.bridge.session is None: break
            await asyncio.sleep(.01)
        self.assertFalse(self.bridge.down)
        self.assertIsNone(self.bridge.session)

    async def test_new_session_not_released_by_old_connection(self):
        old = await self.connect()
        await old.send_bytes(packet(0, (2, 1, 0, 0, 30000, 0, 0)))
        await old.receive()
        new = await self.connect()
        await new.send_bytes(packet(0, (2, 1, 60000, 50000, 50000, 0, 0)))
        await new.receive()
        await old.close()
        self.assertTrue(self.bridge.down)
        self.assertGreater(self.bridge.last['pressure'], .7)

    async def test_invalid_packet_closes_and_cleans_up(self):
        ws = await self.connect()
        await ws.send_bytes(packet(0, (2, 1, 0, 0, 30000, 0, 0)))
        await ws.receive()
        await ws.send_bytes(b'invalid')
        reply = await ws.receive()
        self.assertEqual(reply.type, WSMsgType.CLOSE)
        self.assertEqual(reply.data, 1008)
        await ws.close()
        self.assertFalse(self.bridge.down)

    async def test_http_and_websocket_share_port_and_origin_is_checked(self):
        response = await self.client.get(self.url+'/')
        self.assertIn('transport.js', await response.text())
        response = await self.client.get(self.url+'/ws', headers={'Origin': 'http://elsewhere.invalid'})
        self.assertEqual(response.status, 403)
