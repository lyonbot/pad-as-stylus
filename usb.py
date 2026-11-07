"""Manage the USB transport without requiring an Android app."""
import shutil
import subprocess
import threading


class USBConnection:
    CHROME_PACKAGES = (
        ('com.android.chrome', 'Chrome'),
        ('com.chrome.beta', 'Chrome Beta'),
        ('com.chrome.dev', 'Chrome Dev'),
        ('com.chrome.canary', 'Chrome Canary'),
    )
    def __init__(self, port, serial=None, open_tablet=True):
        self.port = port
        self.serial = serial
        self.open_tablet = open_tablet
        self.stop_event = threading.Event()
        self.adb = shutil.which('adb')
        self.status = '等待设备'
        self.connected_serial = None
        self.opened_serials = set()
        self.thread = threading.Thread(target=self.watch, daemon=True)

    def run(self, *args):
        return subprocess.run([self.adb, *args], capture_output=True, text=True, timeout=8, check=True).stdout

    def report(self, message):
        if message != self.status:
            self.status = message
            print('USB: ' + message, flush=True)

    def start(self):
        if not self.adb:
            self.report('未找到 adb，请安装 Android SDK Platform Tools 并重启服务，或手动配置转发。')
            return
        self.thread.start()

    def open_page(self, serial):
        installed = set()
        for prefix in ('com.android.chrome', 'com.chrome'):
            listing = self.run('-s', serial, 'shell', 'pm', 'list', 'packages', '-e', prefix)
            installed.update(line.removeprefix('package:').strip() for line in listing.splitlines())
        for package, name in self.CHROME_PACKAGES:
            if package not in installed:
                continue
            result = self.run('-s', serial, 'shell', 'am', 'start', '-W', '-a',
                              'android.intent.action.VIEW', '-d', f'http://127.0.0.1:{self.port}/',
                              '-p', package)
            if 'Error:' in result:
                self.report(f'{name} 打开失败：{result.strip()}')
                return False
            self.report(f'{serial} 已连接，已用 {name} 打开输入页面')
            return True
        self.report('USB 已连接，但未找到已启用的 Chrome。请安装或启用 Android Chrome 后重新连接；Edge 在此平板上无法接收悬停。')
        return False

    def watch(self):
        while not self.stop_event.is_set():
            try:
                devices = {}
                for line in self.run('devices').splitlines()[1:]:
                    parts = line.split()
                    if len(parts) >= 2: devices[parts[0]] = parts[1]
                serial = self.serial
                if not serial:
                    if len(devices) > 1:
                        self.connected_serial = None
                        self.report('检测到多个 Android 设备，请使用 --serial 指定设备。')
                        self.stop_event.wait(2)
                        continue
                    serial = next(iter(devices), None)
                if not serial or devices.get(serial) != 'device':
                    self.connected_serial = None
                    state = devices.get(serial, '未连接')
                    self.report(f'等待平板（{state}）；请检查 USB 调试授权。')
                else:
                    # Recheck the mapping too: an adb server restart may drop it.
                    mapping = self.run('-s', serial, 'reverse', '--list')
                    endpoint = f'tcp:{self.port}'
                    valid = any(line.split()[-2:] == [endpoint, endpoint] for line in mapping.splitlines())
                    if not valid:
                        self.run('-s', serial, 'reverse', endpoint, endpoint)
                    if self.connected_serial != serial or not valid:
                        self.connected_serial = serial
                        self.report(f'{serial} 已连接，{endpoint} → Mac {endpoint}')
                        if self.open_tablet and serial not in self.opened_serials:
                            if self.open_page(serial):
                                self.opened_serials.add(serial)
            except (subprocess.SubprocessError, OSError) as error:
                self.connected_serial = None
                self.report(f'连接失败，将自动重试：{error}')
            self.stop_event.wait(2)

    def close(self):
        self.stop_event.set()
