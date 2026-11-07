#!/usr/bin/env python3
"""USB tablet bridge with HTTP control and binary WebSocket input."""
import argparse
import asyncio
import json
import math
import os
import signal
import socket
from pathlib import Path
import secrets
import subprocess
import threading
import time
from aiohttp import web, WSMsgType
from protocol import decode_packet, acknowledgement
from usb import USBConnection

ROOT = Path(__file__).resolve().parent
GESTURE_DEFAULTS = dict(panEnabled=True, zoomEnabled=True, penRejection=False, panSpeed=1.0, zoomSpeed=1.0, panSlop=8.0, pinchSlop=24.0)
GESTURE_LIMITS = dict(panSpeed=(.1, 5), zoomSpeed=(.1, 5), panSlop=(1, 100), pinchSlop=(2, 200))
TOUCH_TYPES = ('touch_down', 'touch_move', 'touch_up', 'touch_cancel')


def number(value, low, high):
    value = float(value)
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError("数值超出范围")
    return value


class Bridge:
    def __init__(self, dry_run=False, screen_size=None, persist=True):
        self.lock = threading.RLock()
        self.dry_run = dry_run
        self.child = None
        self.screen = json.loads(subprocess.check_output([str(ROOT / '.build/PenBridge'), '--screen']))
        if screen_size:
            self.screen = dict(x=0, y=0, width=screen_size[0], height=screen_size[1])
        if self.screen['width'] <= 0 or self.screen['height'] <= 0:
            if not dry_run:
                raise SystemExit('无法读取屏幕尺寸，请在桌面终端运行，或添加 --screen-size 宽 高（Quartz 坐标单位）。')
            self.screen = dict(x=0, y=0, width=1920, height=1080)
            print('提示：当前无法读取显示器，dry-run 使用 1920×1080 预览。', flush=True)
        self.config = dict(x=self.screen['x'], y=self.screen['y'], width=self.screen['width'] * .75,
                           ratio=4 / 3, pen=True)
        self.gestures = dict(GESTURE_DEFAULTS)
        self.persist = persist
        self.config_path = ROOT / '.local/mapping.json'
        if persist and self.config_path.exists():
            try:
                saved = json.loads(self.config_path.read_text())
                for key in ('x', 'y', 'width', 'ratio'):
                    self.config[key] = number(saved[key], .1 if key in ('width', 'ratio') else -50000, 50000)
                self.config['pen'] = bool(saved['pen'])
                self.gestures = self.validated_gestures(saved.get('gestures', {}))
            except (ValueError, KeyError, TypeError):
                print('映射配置无效，使用默认值。', flush=True)
        self.session = None
        self.seq = -1
        self.last_seen = 0
        self.down = False
        self.last = None
        self.count = 0
        self.wire_bytes = 0
        self.wire_packets = 0
        self.suspended = False
        self.port = 18765
        self.usb = None
        if not dry_run:
            check = subprocess.run([str(ROOT / '.build/PenBridge'), '--check'])
            if check.returncode:
                raise SystemExit('请在系统设置 → 隐私与安全性 → 辅助功能中授权终端或 PenBridge，然后重新运行。')
            self.child = subprocess.Popen([str(ROOT / '.build/PenBridge')], stdin=subprocess.PIPE,
                                          stdout=subprocess.PIPE, text=True, bufsize=1)
            threading.Thread(target=self.native_messages, daemon=True).start()

    def validated_gestures(self, data):
        """Merge a partial update into the current gesture settings, rejecting bad values."""
        result = dict(self.gestures)
        for key in ('panEnabled', 'zoomEnabled', 'penRejection'):
            if key in data:
                if not isinstance(data[key], bool):
                    raise ValueError(key + ' 需要布尔值')
                result[key] = data[key]
        for key, (low, high) in GESTURE_LIMITS.items():
            if key in data:
                result[key] = number(data[key], low, high)
        return result

    def set_gestures(self, data):
        with self.lock:
            self.gestures = self.validated_gestures(data)
            self.send_config()
            self.save_config()
            return dict(self.gestures)

    def send_config(self):
        if self.child:
            self.child.stdin.write(json.dumps(dict(self.config, type='config', port=self.port,
                                                  connected=bool(self.session))) + '\n')
            self.child.stdin.write(json.dumps(dict(self.gestures, type='gestures')) + '\n')
            self.child.stdin.flush()

    def save_config(self):
        if self.persist:
            self.config_path.parent.mkdir(exist_ok=True)
            temporary = self.config_path.with_suffix('.tmp')
            temporary.write_text(json.dumps(dict(self.config, gestures=self.gestures)))
            temporary.replace(self.config_path)

    def native_messages(self):
        for line in self.child.stdout:
            try:
                data = json.loads(line)
                with self.lock:
                    if data['type'] == 'mapping':
                        self.release()
                        for k in ('x', 'y', 'width'):
                            self.config[k] = float(data[k])
                        self.save_config()
                    elif data['type'] == 'suspended':
                        self.release()
                        self.suspended = bool(data['value'])
                    elif data['type'] == 'quit':
                        os.kill(os.getpid(), signal.SIGINT)
            except (ValueError, KeyError, BrokenPipeError):
                pass

    def emit(self, event):
        if self.child:
            self.child.stdin.write(json.dumps(event) + '\n')
            self.child.stdin.flush()
        self.last = event
        self.count += 1

    def release(self):
        if self.last and self.last['type'] != 'reset':
            self.emit(dict(self.last, type='reset', pressure=0, buttons=0))
        self.down = False

    def connect(self, ratio):
        with self.lock:
            self.release()
            self.config['ratio'] = number(ratio, .1, 10)
            self.config['width'] = min(self.config['width'], self.screen['width'],
                                       self.screen['height'] * self.config['ratio'])
            self.config['x'] = max(0, min(self.config['x'], self.screen['width'] - self.config['width']))
            self.config['y'] = max(0, min(self.config['y'], self.screen['height'] - self.config['width']/self.config['ratio']))
            self.session = secrets.token_urlsafe(24)
            self.seq = -1
            self.last_seen = time.monotonic()
            self.send_config()
            self.save_config()
            return dict(session=self.session)

    def disconnect(self, session):
        with self.lock:
            if session and self.session == session:
                self.release()
                self.session = None
                self.send_config()

    def events(self, body):
        with self.lock:
            if not self.session or body.get('session') != self.session:
                raise ValueError('会话已失效，请重新开始')
            seq = int(body['seq'])
            if seq <= self.seq:
                return
            events = body['events']
            if not isinstance(events, list) or len(events) > 256:
                raise ValueError('事件批次过大')
            # Validate the entire batch before emitting any event.
            validated = []
            for e in events:
                if e['type'] in TOUCH_TYPES:
                    validated.append(dict(type=e['type'], x=number(e['x'], 0, 1), y=number(e['y'], 0, 1),
                                          slot=int(number(e.get('buttons', 0), 0, 9))))
                    continue
                if e['type'] not in ('enter', 'leave', 'down', 'move', 'up', 'cancel'):
                    raise ValueError('未知事件')
                validated.append(dict(type=e['type'], x=number(e['x'], 0, 1), y=number(e['y'], 0, 1),
                                      pressure=number(e.get('pressure', 0), 0, 1),
                                      buttons=int(number(e.get('buttons', 1 if e['type'] == 'down' else 0), 0, 63)),
                                      tiltX=number(e.get('tiltX', 0), -90, 90),
                                      tiltY=number(e.get('tiltY', 0), -90, 90)))
            self.seq = seq
            self.last_seen = time.monotonic()
            c = self.config
            for e in validated:
                if self.suspended:
                    continue
                is_touch = e['type'] in TOUCH_TYPES
                if not is_touch:
                    e['tabletX'], e['tabletY'] = e['x'] * 65535, e['y'] * 65535
                e['x'] = c['x'] + e['x'] * c['width']
                e['y'] = c['y'] + e['y'] * c['width'] / c['ratio']
                if is_touch:
                    self.emit(e)
                    continue
                e['pen'] = c['pen']
                e['stylus'] = True
                self.emit(e)
                if e['type'] in ('down', 'move', 'up'):
                    self.down = bool(e['buttons'] & (1 if c['pen'] else 31))
                if e['type'] in ('cancel', 'leave'): self.down = False

    def watchdog(self):
        while True:
            time.sleep(.2)
            with self.lock:
                if self.session and time.monotonic() - self.last_seen > 1.5:
                    self.release()
                    self.session = None
                    self.send_config()

    def status(self):
        with self.lock:
            return dict(config=dict(self.config, height=self.config['width'] / self.config['ratio']),
                        screen=self.screen, connected=bool(self.session), down=self.down,
                        last=self.last, count=self.count, dryRun=self.dry_run, suspended=self.suspended,
                        transport='websocket-binary-v1', wireBytes=self.wire_bytes, wirePackets=self.wire_packets,
                        usb=self.usb.status if self.usb else '未启用自动 ADB')


def make_app(bridge):
    sockets = set()

    @web.middleware
    async def guard(request, handler):
        if request.headers.get('Origin') not in (None, 'http://' + request.host):
            return web.json_response({'error': 'Origin rejected'}, status=403)
        try:
            response = await handler(request)
            if not isinstance(response, web.WebSocketResponse):
                response.headers['Cache-Control'] = 'no-store'
            return response
        except (ValueError, KeyError, TypeError, OverflowError) as error:
            return web.json_response({'error': str(error)}, status=400)
        except (BrokenPipeError, OSError):
            return web.json_response({'error': 'Mac 输入进程已停止，请重启服务'}, status=503)

    app = web.Application(middlewares=[guard], client_max_size=32768)

    async def status(request):
        return web.json_response(bridge.status())

    async def config(request):
        if request.content_type != 'application/json':
            raise ValueError('需要 application/json')
        data = await request.json()
        with bridge.lock:
            updated = dict(bridge.config)
            for k in ('x', 'y', 'width'):
                updated[k] = number(data[k], 1 if k == 'width' else -50000, 50000)
            if not isinstance(data['pen'], bool): raise ValueError('pen 需要布尔值')
            updated['pen'] = data['pen']
            bridge.release()
            bridge.config = updated
            bridge.send_config()
            bridge.save_config()
        return web.json_response({'ok': True})

    async def gestures(request):
        if request.method == 'POST':
            if request.content_type != 'application/json':
                raise ValueError('需要 application/json')
            data = await request.json()
            if not isinstance(data, dict):
                raise ValueError('需要 JSON 对象')
            return web.json_response(bridge.set_gestures(data))
        with bridge.lock:
            return web.json_response(dict(bridge.gestures))

    async def asset(request):
        files = {'/': 'index.html', '/settings': 'settings.html',
                 '/pen-input.js': 'pen-input.js', '/touch-input.js': 'touch-input.js', '/gesture-settings.js': 'gesture-settings.js', '/trail.js': 'trail.js',
                 '/transport.js': 'transport.js'}
        name = files.get(request.path)
        if not name: raise web.HTTPNotFound()
        return web.Response(body=(ROOT / 'web' / name).read_bytes(),
                            content_type='text/javascript' if name.endswith('.js') else 'text/html',
                            charset='utf-8')

    async def websocket(request):
        ws = web.WebSocketResponse(compress=False, timeout=.25, max_msg_size=8 + 12*256, receive_timeout=3)
        await ws.prepare(request)
        session = None
        sockets.add(ws)
        try:
            hello = await ws.receive(timeout=3)
            if hello.type != WSMsgType.TEXT: raise ValueError('需要连接握手')
            data = json.loads(hello.data)
            if data.get('type') != 'hello' or data.get('version') != 1:
                raise ValueError('不支持的连接协议')
            ratio = number(data['ratio'], .1, 10)
            for previous in list(sockets):
                if previous is not ws:
                    await previous.close(code=4001, message=b'Replaced by another input session')
            session = bridge.connect(ratio)['session']
            await ws.send_json({'type': 'ready', 'version': 1})
            async for message in ws:
                if message.type == WSMsgType.BINARY:
                    if bridge.session != session:
                        await ws.close(code=4001 if bridge.session else 4000, message=b'Session expired')
                        break
                    seq, events = decode_packet(message.data)
                    bridge.events(dict(session=session, seq=seq, events=events))
                    with bridge.lock:
                        bridge.wire_bytes += len(message.data)
                        bridge.wire_packets += 1
                    await ws.send_bytes(acknowledgement(seq))
                elif message.type == WSMsgType.TEXT:
                    raise ValueError('输入事件必须使用二进制包')
                elif message.type == WSMsgType.ERROR:
                    break
        except (ValueError, KeyError, TypeError, OverflowError):
            bridge.disconnect(session)
            await ws.close(code=1008, message=b'Invalid input packet')
        except (asyncio.TimeoutError, ConnectionError, OSError):
            bridge.disconnect(session)
            await ws.close(code=4000, message=b'Connection interrupted')
        finally:
            sockets.discard(ws)
            bridge.disconnect(session)
        return ws

    async def shutdown(app):
        bridge.disconnect(bridge.session)
        await asyncio.gather(*(ws.close(code=1001, message=b'Server shutdown') for ws in list(sockets)))

    app.on_shutdown.append(shutdown)
    app.router.add_get('/ws', websocket)
    app.router.add_get('/api/status', status)
    app.router.add_post('/api/config', config)
    app.router.add_get('/api/gestures', gestures)
    app.router.add_post('/api/gestures', gestures)
    app.router.add_get('/{path:.*}', asset)
    return app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=18765)
    parser.add_argument('--dry-run', action='store_true', help='只接收和映射，不控制鼠标')
    parser.add_argument('--screen-size', nargs=2, type=int, metavar=('WIDTH', 'HEIGHT'))
    parser.add_argument('--serial', help='指定 Android 设备序列号')
    parser.add_argument('--no-adb', action='store_true', help='不自动配置 USB/ADB')
    parser.add_argument('--no-open-tablet', action='store_true', help='配置转发但不自动打开平板网页')
    args = parser.parse_args()
    if args.screen_size and min(args.screen_size) <= 0: parser.error('屏幕尺寸必须为正数')
    try:
        listener = socket.socket()
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(('127.0.0.1', args.port))
        listener.listen(64)
        listener.setblocking(False)
    except OSError as error:
        raise SystemExit(f'端口 {args.port} 无法使用，服务可能已经启动。请从菜单栏操作，或用 --port 指定其他端口。\n{error}')
    try:
        bridge = Bridge(args.dry_run, args.screen_size, persist=not args.dry_run)
    except BaseException:
        listener.close()
        raise
    bridge.port = args.port
    bridge.send_config()
    usb = USBConnection(args.port, args.serial, not args.no_open_tablet)
    bridge.usb = usb
    if not args.no_adb: usb.start()
    threading.Thread(target=bridge.watchdog, daemon=True).start()
    print(f'平板：http://localhost:{args.port}  Mac 设置：http://localhost:{args.port}/settings', flush=True)
    print(f'USB: adb reverse tcp:{args.port} tcp:{args.port}', flush=True)
    try:
        web.run_app(make_app(bridge), sock=listener, print=None, access_log=None, shutdown_timeout=2)
    except KeyboardInterrupt:
        pass
    finally:
        usb.close()
        with bridge.lock:
            try:
                bridge.release()
            except (BrokenPipeError, OSError):
                pass
            if bridge.child:
                try: bridge.child.stdin.close()
                except BrokenPipeError: pass
                bridge.child.wait(timeout=3)
        listener.close()


if __name__ == '__main__': main()
