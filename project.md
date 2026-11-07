# Pad as Stylus

通过 USB 将 Android 平板上的笔输入映射到 macOS。首版以坐标、点击和拖动可用为核心，同时传递压感和倾斜字段。平板无需安装 APK，浏览器全屏显示输入区。

## 阶段与验收

1. **最小输入链路（已实现，坐标接收已真机验证）**：平板网页 → ADB USB → Mac WebSocket 服务 → Swift CGEvent。支持光标位置、落笔点击、拖动和抬笔，同时附带压感与倾斜；用户已确认 Android Chrome 的悬停可用，Edge 在本平板上不可用。
2. **原生映射交互（已实现）**：Mac 菜单栏笔尖图标，桌面置顶的半透明映射框。拖动移动，右下角等比缩放，点框内“完成调整”隐藏并恢复输入；菜单提供显示/隐藏、暂停/恢复和退出。高度由平板实际全屏输入区比例计算，调整立即生效并保存。
3. **真机体验验证（待进行）**：真实平板书写、手掌触摸、快速连续笔画、横竖屏变化、拔线和重连；记录目标应用对压感的支持，不阻塞坐标功能验收。
4. **后续优化（未实现）**：增加多屏选择和独立 .app 打包。不做 Mac 画面回传。

## 模块

| 文件 | 职责 |
| --- | --- |
| `web/index.html` | 全屏输入区；采集笔的归一化坐标、压力、倾斜，手指交给 touch-input.js，按顺序小批量发送 |
| `web/pen-input.js` | 直接在全屏输入元素 `#pad` 上处理 over/enter/move/out/leave，独立管理悬停与笔尖按压状态 |
| `web/touch-input.js` | 手指触点采集（slot 0-9），可选的“笔在附近时忽略手指”（`penRejection`，默认关，由平板系统自行屏蔽触摸时无需开启）；只上报原始触点，不识别手势 |
| `web/gesture-settings.js` | 平板页面右上角的「平移」「缩放」开关与 ⚙ 设置面板（速度、触发阈值），经 `/api/gestures` 读写 |
| `web/trail.js` | Canvas 轨迹预览，落笔绿色实线、悬停蓝色虚线，约 1.5 秒自动淡出，支持清除 |
| `web/settings.html` | Mac 设置页：映射预览、拖动和等比缩放、事件状态、笔模式开关 |
| `server.py` | aiohttp HTTP/WebSocket 同端口服务、`/api/gestures` 手势设置（校验、持久化、转发给 Swift）、输入校验、会话隔离、坐标转换、断连自动抬笔 |
| `protocol.py` | 二进制数据包校验与解码，生成 ACK；`touch_*` 记录用 buttons 字节携带触点 slot |
| `web/transport.js` | 持久 WebSocket、二进制编码、心跳、ACK 检测、退避重连与丢弃旧输入队列 |
| `requirements.txt` | 固定 aiohttp 版本，启动时自动安装到项目 `.venv` |
| `native/PenBridge.swift` | 原生菜单栏、置顶映射框、双向 JSON 通信及 mouse/drag/up 注入，附加压感和倾斜字段；`TouchGestures` 将双指平移识别为带 phase 的触控板式滚动、双指捏合识别为 magnify 手势事件（私有 CGEvent 字段，暂无惯性） |
| `usb.py` | 自动检测 ADB 设备、配置 reverse、打开网页，拔插后重连 |
| `Start.command` | Finder 双击启动入口 |
| `run.sh` | 编译 Swift（源码未变化则复用），启动服务 |
| `tests/test_touch_input.cjs` | 触点 slot 分配、笔优先、忽略工具按钮 |
| `tests/test_bridge.py` | 验证坐标与压力映射、抬笔、去重、非法数据和会话更换 |

输入使用持久 WebSocket，HTTP 页面、设置 API 和 WebSocket 共用同一端口。握手使用一条 JSON，后续事件和心跳均为二进制。按顺序小批量发送，边界事件及时发送；空闲每 400ms 心跳保活。依赖仅 aiohttp，首次运行自动创建 `.venv` 并安装固定版本，无需手工 pip/npm 操作。

网页全屏、笔事件绑定和坐标基准统一为具体元素 `#pad`。`#trail` Canvas 和开始界面位于 `#pad` 内；Canvas 设置 `pointer-events:none`，不截获输入。页面显示落笔/悬停轨迹，并提供“清除轨迹”按钮；工具按钮不映射到 Mac。

## 环境

- macOS，Python 3.9+，Swift 编译器（Xcode Command Line Tools）。首次运行需联网从 PyPI 安装 aiohttp 到项目虚拟环境。
- Mac 上安装 Android SDK Platform Tools，能够执行 `adb`。
- Android 平板，Android Chrome（稳定版/Beta/Dev/Canary 均可），支持笔输入的硬件。此平板已确认 Chrome 可收到悬停，Edge 不可，因此自动启动显式指定 Chrome，不使用系统默认浏览器。
- USB 数据线；平板开启开发者选项和 USB 调试，接受 Mac 的调试授权。不需要 root。

## 运行

在本项目目录执行：

```bash
bash run.sh
```

首次会检查并请求输入注入权限。在「系统设置 → 隐私与安全性 → 辅助功能」中授权实际显示的终端宿主或 PenBridge，然后重启上面的命令。授权对象以系统提示为准。单独检查可执行：

```bash
.build/PenBridge --check
```

也可以在 Finder 中双击 `Start.command` 启动。请使用普通桌面终端运行，输入程序需要真实桌面会话。

日常流程：

1. 用 USB 连接平板，解锁并接受 USB 调试授权。
2. 双击 `Start.command` 或执行 `bash run.sh`。服务自动检测设备、配置 ADB reverse，在平板查找已启用的 Chrome 并显式指定包名打开 `http://127.0.0.1:18765/`。优先稳定版，其次 Beta、Dev、Canary；不修改系统默认浏览器。未安装 Chrome 时明确提示，不自动回退 Edge。
3. 平板点“开始书写”进入全屏。笔进入感应范围后，Mac 光标默认跟随；落笔点击/拖动，抬笔后继续悬停跟随。无需悬停启动参数或开关。
4. 需要调整映射时，从菜单栏打开绿色映射框，拖动位置、拉右下角等比缩放。点框内“完成调整”隐藏框并恢复输入。默认不显示映射框、不暂停输入。
5. 菜单栏笔尖图标提供显示/隐藏映射框、暂停/恢复、连接状态、查看高级设置、退出。
6. 拔插 USB 后自动恢复端口转发，保留原来的 Chrome 页面；页面保持全屏时自动重连，不另开标签页、不需要再次点“开始书写”。退出全屏、切后台或页面被系统销毁后，重新点开始。

映射位置、宽度、笔模式和手势设置保存在 `.local/mapping.json`，重启保留。浏览器入口无法越过锁屏，也无法自动点击网页全屏按钮，仍需用户解锁并点一次。

常用参数：

```bash
# 多台设备时指定序列号
bash run.sh --serial SERIAL
# 配置转发，但不自动打开浏览器
bash run.sh --no-open-tablet
# 自己管理 ADB
bash run.sh --no-adb
# 更换端口，ADB 会自动使用相同端口
bash run.sh --port 28765
# 桌面尺寸无法自动读取时显式指定（Quartz 单位）
bash run.sh --screen-size 2560 1440
```

高级状态页：`http://localhost:18765/settings`。服务只监听 `127.0.0.1`，不开放局域网；配置转发的命令由程序自动执行，相当于 `adb reverse tcp:18765 tcp:18765`。若端口已占用，会明确提示，不再启动重复的原生输入进程。

## 先验证接收，不控制鼠标

```bash
bash run.sh --dry-run
```

平板访问该端口，Mac 设置页可观察最近事件、映射后的 x/y、压力和计数。dry-run 不需要辅助功能权限，但仍需 Swift 编译器。没有显示器信息时使用 1920×1080 预览，真实模式不会使用虚构尺寸。

## 验证方法

```bash
.venv/bin/python -m unittest discover -s tests -v
node --test tests/test_pen_input.cjs tests/test_transport.cjs
```

人工验收：

- 在平板四角落笔，Mac 光标落到映射矩形对应四角；圆形运动不被横向/纵向拉伸。
- 连续点击、写字、拖动窗口，抬笔后不再拖动；手指只用于双指滚动和捏合缩放，不移动光标或点击。
- 双指在网页或文档上拖动：内容跟手滚动（方向如与预期相反，见 `native/PenBridge.swift` 的 `TouchGestures.post`）；在 Safari/预览等应用中双指捏合缩放（以光标为中心，一次手势内平移与缩放二选一）；三指以上无动作。
- 设置页拖动位置、拉角缩放后保存，比例保持为平板输入区比例。
- 按住笔时拔线，最迟约 1.5 秒内释放左键；重新插回后原全屏页面自动建立新会话。断线期间的数据不重放，旧连接不能释放新会话的笔。
- 退出全屏、切后台、旋转平板后输入暂停，重新开始会同步尺寸。
- 压感笔在设置页显示变化的 pressure；支持压感的 Mac 应用可进一步检查笔刷响应。关闭笔模式可比较普通鼠标兼容性。

## 当前边界

- 首版只映射主屏幕；坐标为 Quartz 全局坐标，原点在主屏幕左上，无需乘 Retina 缩放倍数。
- 映射按实际全屏输入区宽高比，不凭网页猜测屏幕物理毫米尺寸。
- 映射框是原生桌面置顶窗口，设置持久化到 `.local/mapping.json`；显示调整框期间暂停笔输入。
- 同时只允许一个平板会话；新连接会释放并替换旧会话。设置页不是输入客户端。
- 压力范围 0–1，倾斜从网页角度归一化后写入 tablet 字段。当前是合成事件，不是虚拟硬件驱动，应用对压感的识别需要真机确认。
- 无悬停能力的笔仅在接触时更新位置；传输延迟和浏览器手势兼容性仍需真实设备验收。
- 异常取消、断连和正常退出提供抬笔保护；进程被强制杀死等情况无法保证清理。

## 参考

- [ADB reverse 官方说明](https://developer.android.com/develop/ui/views/layout/webapps/access-local-server)
- [Core Graphics 笔压字段](https://developer.apple.com/documentation/coregraphics/cgeventfield/tableteventpointpressure)
- [Pointer Events](https://www.w3.org/TR/pointerevents/)

## 当前验证记录

- Swift 编译通过；31 项 Python/原生/二进制 WebSocket 测试、17 项网页输入/传输状态机测试通过。
- 浏览器验证：全屏入口、坐标/压感/倾斜数据传输、设置保存与映射预览。
- 已通过 USB 接收到实际平板的坐标、倾斜、落笔和抬笔事件（超过 100 个事件）。
- 沙箱外读取到 Mac 主屏幕 2560×1440，输入权限检查通过。
- 原生菜单栏、置顶映射框、自动 ADB 与持久化已实现；真实桌面控制手感与应用压感响应仍需用户在桌面试用。

## 输入生命周期

| 网页输入 | macOS 事件 |
| --- | --- |
| pointerenter / 第一个有效笔事件 | tabletProximity（进入），立即定位光标 |
| pointerover | 与 enter 合并去重，恢复新 pointerId 的感应状态 |
| 未按下时 pointermove | mouseMoved + tabletPoint 子类型，压力固定为 0 |
| pointerdown | leftMouseDown + tabletPoint，开始新笔画 |
| 按下时 pointermove | leftMouseDragged + tabletPoint，携带压力/倾斜 |
| 按住位置不变，仅压力/倾斜更新 | 原生 tabletPointer 事件 |
| pointerup | leftMouseUp，压力归零，保留 proximity，继续允许悬停 |
| pointerleave | 必要时先 leftMouseUp，再 tabletProximity（离开） |
| pointercancel / 异常丢失 capture | 在最后有效位置释放并退出 proximity，忽略残留 move，直到新的 enter/down |
| 切后台、退出全屏、断连、暂停、退出 | 清理按下及 proximity；断连超时为 1.5 秒 |

macOS 的鼠标/笔事件没有与 DOM pointercancel 一一对应的通用 cancel 类型；这里明确执行释放和离开清理，不伪造不存在的事件。正常抬笔不会被误当成离开感应范围。proximity 与 point 使用相同 device ID，附带设备能力及 0–65535 的数位板绝对坐标。原生状态机测试覆盖完整生命周期、取消后的残留移动、丢失 up 的恢复、定点变压和 EOF 清理。

网页悬停不受上一笔的 pointerId 限制。setPointerCapture 失败不影响事件发送，页面重连重置所有输入状态；旧 ID 迟到的 leave 不会取消新笔画。浏览器模块测试覆盖这些恢复场景。诊断对 hover 单独累计计数和样本，长笔画不会覆盖悬停证据；仅使用 Pointer Events，不启用 mousemove 兼容路径。Node 仅用于开发测试，正常运行不依赖 Node。

独立 agent 审查复现了旧版 capture 抛错后 active 残留、阻断新 ID 悬停的问题；新版已覆盖对应回归测试。该复现说明代码存在缺陷，但不能单凭它断定真实平板上此前每次悬停失败的具体原因。真实页面可通过 `penInput.diagnostics` 查看累计计数和悬停样本。


## 轨迹淡出与二进制传输

落笔和悬停的每段轨迹独立按年龄渐隐，约 1500ms 后移除；淡出由 requestAnimationFrame 驱动，全部消失后停止重绘。断连重置轨迹连接点，不把重连前后的点连成跳线。

协议为 network byte order（大端）：

| 部分 | 格式 | 字节数 |
| --- | --- | --- |
| 包头 | version u8、flags u8、count u16、sequence u32 | 8 |
| 每个事件 | kind u8、buttons u8、x/y/pressure 各 u16、tiltX/tiltY 各 i16 | 12 |
| ACK | 同包头，flags=1、count=0、原 sequence | 8 |

坐标与压力归一化到 0–65535，倾斜以 0.01 度编码，保留符号。每包最多 256 个采样点。与每点重复 JSON 字段相比，事件载荷固定为 12 字节；WebSocket 持久连接避免反复 HTTP 请求头。关闭 per-message 压缩，减少这类小包的额外 CPU/延迟。

客户端检测 1.2 秒 ACK 超时或发送缓冲超过 32KiB 后主动重连；退避从 250ms 逐步增加到最多 5 秒。重连清空按下状态、未发送队列和待确认包，建立新会话。服务器在连接关闭时立即释放笔；遇到无法及时检测的断线，1.5 秒 watchdog 兜底。另一个页面接管时停止旧页面重试，避免两个页面争抢。

验证：实际浏览器中的轨迹像素 alpha 从 246 降到 65 再到 0；真实停止并重启测试服务后，页面保持 `#pad` 全屏，自动恢复 WebSocket，输入队列为空、服务器未收到旧笔画。`/api/status` 提供 transport、wireBytes、wirePackets 诊断值。


## 鼠标兼容与笔侧键

鼠标兼容模式使用独立状态机，生成明确的普通鼠标事件（subtype=default），不带 tablet proximity/point。支持左右中键及辅助键的 down/up/dragged、移动增量、匹配的事件编号、双击计数，并继承 Mac 当前键盘修饰键。普通鼠标的 enter/exit 由应用的 tracking area 根据位置处理，没有独立的对应 CGEventType；取消通过释放所有按键实现。

平板的来源始终是笔，侧键规则在笔模式和鼠标兼容模式均生效：

- 普通落笔：左键按下，移动为左键拖拽，抬笔释放左键。
- 按住侧键再落笔：右键按下，移动为右键拖拽，抬笔释放右键。
- 悬停时单独按侧键：只移动，不发鼠标点击。
- 以落笔瞬间的侧键状态选定按键，并保持到抬笔；拖动中按下/松开侧键不会切换当前鼠标按键。
- 浏览器采用 Pointer Events 标准 buttons 位：笔尖=1、侧键=2。侧键按住后再落笔可能只触发 pointermove（buttons 从 2 变 3），这条路径也会正确开始右键拖拽。
- 鼠标模式的取消、暂停和断连会释放所有已按按键；重连不会把仍压着的旧笔画重新按下。

回归测试覆盖真实 CGEvent 的类型、buttonNumber、clickState、delta、事件编号、组合按键释放，以及两种模式下的侧键+落笔右键映射。滚轮和触控板手势目前没有映射。
