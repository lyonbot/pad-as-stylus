# Pad as Stylus

把 Android 平板变成 Mac 的手写板：通过 USB 把平板上的笔输入映射为 Mac 光标，**平板无需安装 APK**，浏览器全屏即用。

## 功能

- **笔映射**：悬停移动光标，落笔点击/拖动，抬笔继续悬停；同时传递**压感**和**倾斜**
- **笔侧键**：按住侧键再落笔 = 右键
- **手指手势**：双指平移 = 触控板式滚动，双指捏合 = 缩放（可在平板页面开关、调速度）
- **映射框**：Mac 桌面上半透明置顶框，拖动位置、拉右下角等比缩放，决定平板对应桌面的哪块区域
- **菜单栏控制**：显示/隐藏映射框、暂停/恢复、查看连接状态
- **断线自愈**：拔插 USB 自动重连；按住笔时拔线会自动抬笔，不会卡住鼠标
- **仅本机监听**（`127.0.0.1`），通过 `adb reverse` 走 USB，不开放局域网

## 环境要求

| 项 | 要求 |
| --- | --- |
| Mac | macOS，Python 3.9+，Xcode Command Line Tools（`xcode-select --install`） |
| ADB | 已安装 Android SDK Platform Tools，终端可执行 `adb` |
| 平板 | 支持笔输入，已装 **Chrome**（Edge 在部分设备上收不到悬停），开启开发者选项与 USB 调试 |
| 其他 | USB 数据线；首次运行需联网安装依赖（aiohttp） |

## 快速开始

1. USB 连接平板，解锁并允许 USB 调试授权。
2. 在项目目录运行（或在 Finder 双击 `Start.command`）：

   ```bash
   bash run.sh
   ```

3. 首次运行按提示到「系统设置 → 隐私与安全性 → 辅助功能」授权终端（或 PenBridge），然后**重新运行**。
4. 平板上会自动用 Chrome 打开页面，点「开始书写」进入全屏，即可书写。
5. 需要调整映射区域时，点菜单栏笔尖图标显示映射框，拖动/缩放后点框内「完成调整」。

映射位置和手势设置保存在 `.local/mapping.json`，重启后保留。

## 常用参数

```bash
bash run.sh --dry-run                 # 只接收不控制鼠标，用于验证链路
bash run.sh --serial SERIAL           # 多台设备时指定序列号
bash run.sh --no-open-tablet          # 不自动在平板打开浏览器
bash run.sh --no-adb                  # 自己管理 ADB
bash run.sh --port 28765              # 更换端口
bash run.sh --screen-size 2560 1440   # 手动指定桌面尺寸
```

状态与设置页：<http://localhost:18765/settings>

## 常见问题

- **光标不动**：检查辅助功能授权，可运行 `.build/PenBridge --check`。
- **平板打不开页面**：确认 USB 调试已授权，`adb devices` 能看到设备；页面地址为 `http://127.0.0.1:18765/`。
- **没有悬停**：换用 Chrome；确认笔在感应范围内。
- **退出全屏/切后台后无输入**：重新点「开始书写」。
- **应用不响应压感**：本项目发送的是合成的数位板事件，是否识别压感取决于目标应用。

## 更多

设计、模块划分、协议、输入生命周期与验收方法见 [project.md](project.md)。
