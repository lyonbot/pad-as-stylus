import Foundation
import CoreGraphics
import AppKit

func output(_ value: Any) {
    let data = try! JSONSerialization.data(withJSONObject: value, options: [.sortedKeys])
    print(String(data: data, encoding: .utf8)!)
    fflush(stdout)
}
if CommandLine.arguments.contains("--screen") {
    let r = CGDisplayBounds(CGMainDisplayID())
    output(["x": r.minX, "y": r.minY, "width": r.width, "height": r.height])
    exit(0)
}
if CommandLine.arguments.contains("--check") {
    let allowed = CGPreflightPostEventAccess()
    if !allowed { _ = CGRequestPostEventAccess() }
    output(["allowed": allowed])
    exit(allowed ? 0 : 2)
}
let tracing = CommandLine.arguments.contains("--trace")
if !tracing && !CGPreflightPostEventAccess() {
    fputs("需要辅助功能权限：请先运行 .build/PenBridge --check，授权后重启。\n", stderr)
    exit(2)
}
class MouseInput {
    let source = tracing ? nil : CGEventSource(stateID: .hidSystemState)
    // DOM buttons bits differ from CGMouseButton numbers (right=2, middle=4).
    let buttons: [(bit: Int, number: UInt32)] = [(1, 0), (2, 1), (4, 2), (8, 3), (16, 4)]
    var held = 0
    var point = CGPoint.zero
    var postedPoint: CGPoint?
    var blocked = false
    var number: Int64 = 0
    var eventNumbers: [UInt32: Int64] = [:]
    var clickCounts: [UInt32: Int64] = [:]
    var clicks: [UInt32: (time: TimeInterval, point: CGPoint, count: Int64)] = [:]
    var dragOrigins: [UInt32: CGPoint] = [:]
    var stylusTipDown = false
    var stylusButton = 1
    var needsTipUp = false

    func emit(_ action: String, button: UInt32 = 0) {
        let type: CGEventType
        switch action {
        case "down": type = button == 0 ? .leftMouseDown : button == 1 ? .rightMouseDown : .otherMouseDown
        case "up": type = button == 0 ? .leftMouseUp : button == 1 ? .rightMouseUp : .otherMouseUp
        case "drag": type = button == 0 ? .leftMouseDragged : button == 1 ? .rightMouseDragged : .otherMouseDragged
        default: type = .mouseMoved
        }
        guard let event = CGEvent(mouseEventSource: source, mouseType: type, mouseCursorPosition: point,
                                  mouseButton: CGMouseButton(rawValue: button)!) else { return }
        let moving = action == "hover" || action == "drag"
        let dx = moving ? point.x - (postedPoint?.x ?? point.x) : 0
        let dy = moving ? point.y - (postedPoint?.y ?? point.y) : 0
        let count = action == "hover" ? 0 : clickCounts[button] ?? 1
        event.flags = CGEventSource.flagsState(.combinedSessionState)
        event.setIntegerValueField(.mouseEventSubtype, value: Int64(CGEventMouseSubtype.defaultType.rawValue))
        event.setIntegerValueField(.mouseEventButtonNumber, value: Int64(button))
        event.setIntegerValueField(.mouseEventNumber, value: eventNumbers[button] ?? 0)
        event.setIntegerValueField(.mouseEventClickState, value: count)
        event.setIntegerValueField(.mouseEventDeltaX, value: Int64(dx.rounded()))
        event.setIntegerValueField(.mouseEventDeltaY, value: Int64(dy.rounded()))
        event.setDoubleValueField(.mouseEventPressure, value: action == "up" || held == 0 ? 0 : 1)
        if tracing {
            output(["event": action, "cgType": event.type.rawValue, "button": event.getIntegerValueField(.mouseEventButtonNumber),
                    "clickCount": event.getIntegerValueField(.mouseEventClickState),
                    "deltaX": event.getIntegerValueField(.mouseEventDeltaX), "deltaY": event.getIntegerValueField(.mouseEventDeltaY),
                    "subtype": event.getIntegerValueField(.mouseEventSubtype),
                    "stroke": event.getIntegerValueField(.mouseEventNumber), "held": held,
                    "x": point.x, "y": point.y, "pen": false])
        } else { event.post(tap: .cghidEventTap) }
        postedPoint = point
    }
    func sync(_ desired: Int) {
        for b in buttons where held & b.bit != 0 && desired & b.bit == 0 {
            held &= ~b.bit; emit("up", button: b.number); dragOrigins[b.number] = nil
        }
        for b in buttons where held & b.bit == 0 && desired & b.bit != 0 {
            let now = ProcessInfo.processInfo.systemUptime
            let old = clicks[b.number]
            let interval = tracing ? 0.5 : NSEvent.doubleClickInterval
            let nearby = old.map { hypot(point.x-$0.point.x, point.y-$0.point.y) <= 4 } ?? false
            let count: Int64 = old != nil && now-old!.time <= interval && nearby ? old!.count+1 : 1
            clicks[b.number] = (now, point, count); clickCounts[b.number] = count
            number += 1; eventNumbers[b.number] = number
            dragOrigins[b.number] = point; held |= b.bit; emit("down", button: b.number)
        }
    }
    func reset(blockMoves: Bool = false, clearClicks: Bool = true) {
        let hadHeld = held != 0
        if stylusTipDown { needsTipUp = true }
        stylusTipDown = false
        sync(0); blocked = blockMoves
        if clearClicks || hadHeld { clicks.removeAll() }
    }
    func handle(_ data: [String: Any]) {
        guard let kind = data["type"] as? String else { return }
        if kind == "reset" || kind == "cancel" || kind == "leave" {
            reset(blockMoves: kind == "cancel", clearClicks: kind != "leave"); return
        }
        if kind == "move" && blocked { return }
        if kind == "enter" || kind == "down" { blocked = false }
        point = CGPoint(x: data["x"] as? Double ?? point.x, y: data["y"] as? Double ?? point.y)
        let defaultButtons = kind == "down" ? 1 : kind == "up" ? 0 : held
        let raw = (data["buttons"] as? Int ?? defaultButtons) & 31
        var desired = raw
        var tipBegan = false
        if data["stylus"] as? Bool == true {
            let tip = raw & 1 != 0
            if !tip || kind == "down" { needsTipUp = false }
            if tip && !needsTipUp && kind != "enter" {
                tipBegan = !stylusTipDown
                if tipBegan { stylusButton = raw & 2 != 0 ? 2 : 1 }
                stylusTipDown = true; desired = stylusButton
            } else {
                stylusTipDown = false; desired = 0
            }
        }
        switch kind {
        case "enter": if held == 0 { emit("hover") }
        case "down", "up": sync(desired)
        case "move":
            // Don't reconstruct a missing down after a reconnect or cancellation.
            if held == 0 && desired != 0 && !tipBegan { return }
            sync(desired)
            for b in buttons where held & b.bit != 0 {
                if let origin = dragOrigins[b.number], hypot(point.x-origin.x, point.y-origin.y) > 4 {
                    clicks[b.number] = nil
                }
            }
            if let b = buttons.first(where: { held & $0.bit != 0 }) { emit("drag", button: b.number) }
            else { emit("hover") }
        default: break
        }
    }
}

/// Two-finger gestures posted as trackpad events: pan as phased pixel scroll (content follows the
/// fingers), pinch as magnify. The first clear motion picks one for the rest of the gesture.
/// Three or more fingers cancel it until all lift. Both act at the cursor, like a trackpad.
class TouchGestures {
    enum Mode { case idle, undecided, pan, zoom, ignored }
    let source = tracing ? nil : CGEventSource(stateID: .hidSystemState)
    // Tunable from the tablet page; defaults mirror GESTURE_DEFAULTS in server.py.
    var panEnabled = true, zoomEnabled = true
    var panSlop: CGFloat = 8, pinchSlop: CGFloat = 24
    var panGain: CGFloat = 1
    /// Magnification per unit of relative finger-distance change.
    var zoomGain = 1.0
    var touches: [Int: CGPoint] = [:]
    var mode = Mode.idle
    var origin = CGPoint.zero
    var previous = CGPoint.zero
    var startDistance: CGFloat = 0
    var lastDistance: CGFloat = 0
    var dead = false
    var remainder = CGPoint.zero

    var centroid: CGPoint {
        let sum = touches.values.reduce(CGPoint.zero) { CGPoint(x: $0.x + $1.x, y: $0.y + $1.y) }
        return CGPoint(x: sum.x / CGFloat(touches.count), y: sum.y / CGFloat(touches.count))
    }
    var distance: CGFloat {
        let p = Array(touches.values)
        return p.count == 2 ? hypot(p[0].x - p[1].x, p[0].y - p[1].y) : 0
    }
    func post(_ phase: Int64, dx: CGFloat, dy: CGFloat) {
        remainder.x += dx; remainder.y += dy
        let ix = Int32(remainder.x.rounded(.towardZero)), iy = Int32(remainder.y.rounded(.towardZero))
        remainder.x -= CGFloat(ix); remainder.y -= CGFloat(iy)
        if phase == 4 { remainder = .zero }
        if tracing {
            output(["event": "scroll", "phase": phase, "dx": Int(ix), "dy": Int(iy)]); return
        }
        // Positive wheel1 moves content down, matching a finger moving down.
        guard let event = CGEvent(scrollWheelEvent2Source: source, units: .pixel, wheelCount: 2,
                                  wheel1: iy, wheel2: ix, wheel3: 0) else { return }
        event.setIntegerValueField(.scrollWheelEventIsContinuous, value: 1)
        event.setIntegerValueField(.scrollWheelEventScrollPhase, value: phase)
        event.setIntegerValueField(.scrollWheelEventPointDeltaAxis1, value: Int64(iy))
        event.setIntegerValueField(.scrollWheelEventPointDeltaAxis2, value: Int64(ix))
        if let here = CGEvent(source: nil)?.location { event.location = here }
        event.post(tap: .cghidEventTap)
    }
    /// NSEventTypeGesture (29) carrying kIOHIDEventTypeZoom (8). Fields 110 (HID event type),
    /// 113 (magnification delta) and 132 (phase: 1 began, 2 changed, 4 ended) are private CGEvent
    /// fields with no public API; the same technique is used by Mac Mouse Fix and MacTouch.
    func magnify(_ amount: Double, phase: Int64) {
        if tracing {
            output(["event": "magnify", "phase": phase, "magnification": amount]); return
        }
        func field(_ n: UInt32) -> CGEventField { unsafeBitCast(n, to: CGEventField.self) }
        guard let event = CGEvent(source: nil) else { return }
        event.type = unsafeBitCast(UInt32(29), to: CGEventType.self)
        event.setIntegerValueField(field(110), value: 8)
        event.setIntegerValueField(field(132), value: phase)
        event.setDoubleValueField(field(113), value: amount)
        event.post(tap: .cghidEventTap)
    }
    func endGesture() {
        if mode == .pan { post(4, dx: 0, dy: 0) }
        if mode == .zoom { magnify(0, phase: 4) }
        mode = .idle
    }
    func rebase() {
        origin = centroid; previous = origin; startDistance = distance; lastDistance = startDistance
        mode = .undecided; remainder = .zero
    }
    func decide() {
        let c = centroid
        let moved = hypot(c.x - origin.x, c.y - origin.y), spread = abs(distance - startDistance)
        // Panning needs the finger spacing to stay nearly constant; in-between spacing keeps waiting.
        // A gesture whose kind is switched off is swallowed, not reinterpreted as the other kind.
        if spread > pinchSlop && spread > moved {
            if zoomEnabled { mode = .zoom; magnify(0, phase: 1) } else { mode = .ignored }
        } else if moved > panSlop && spread <= pinchSlop / 2 {
            if panEnabled {
                mode = .pan; post(1, dx: (c.x - origin.x) * panGain, dy: (c.y - origin.y) * panGain); previous = c
            } else { mode = .ignored }
        }
    }
    func handle(_ data: [String: Any]) {
        guard let kind = data["type"] as? String, let slot = data["slot"] as? Int else { return }
        let point = CGPoint(x: data["x"] as? Double ?? 0, y: data["y"] as? Double ?? 0)
        switch kind {
        case "touch_down":
            touches[slot] = point
            if touches.count > 2 { endGesture(); dead = true }
            else if touches.count == 2 && !dead { rebase() }
        case "touch_move":
            guard touches[slot] != nil else { return }
            touches[slot] = point
            guard touches.count == 2 && !dead else { return }
            if mode == .undecided { decide() }
            switch mode {
            case .pan:
                // The deciding move already posted the "began" phase.
                let c = centroid
                if c != previous { post(2, dx: (c.x - previous.x) * panGain, dy: (c.y - previous.y) * panGain); previous = c }
            case .zoom:
                let d = distance
                if lastDistance > 0 && d > 0 { magnify((d / lastDistance - 1) * zoomGain, phase: 2) }
                lastDistance = d
            default: break
            }
        case "touch_up", "touch_cancel":
            if touches[slot] != nil { endGesture(); touches[slot] = nil }
            if touches.isEmpty { dead = false }
        default: break
        }
    }
    func reset() { endGesture(); touches.removeAll(); dead = false }
    func configure(_ data: [String: Any]) {
        panEnabled = data["panEnabled"] as? Bool ?? panEnabled
        zoomEnabled = data["zoomEnabled"] as? Bool ?? zoomEnabled
        if let v = data["panSpeed"] as? Double { panGain = CGFloat(v) }
        if let v = data["zoomSpeed"] as? Double { zoomGain = v }
        if let v = data["panSlop"] as? Double { panSlop = CGFloat(v) }
        if let v = data["pinchSlop"] as? Double { pinchSlop = CGFloat(v) }
    }
}

class PenInput {
    let mouse = MouseInput()
    var mouseMode = false
    let source = tracing ? nil : CGEventSource(stateID: .hidSystemState)
    var pressed = false
    var inRange = false
    var cancelled = false
    var point = CGPoint.zero
    var last: [String: Any] = [:]
    var strokeNumber: Int64 = 0
    var activeButton: CGMouseButton = .left

    var downType: CGEventType { activeButton == .right ? .rightMouseDown : .leftMouseDown }
    var upType: CGEventType { activeButton == .right ? .rightMouseUp : .leftMouseUp }
    var dragType: CGEventType { activeButton == .right ? .rightMouseDragged : .leftMouseDragged }
    func chooseButton(_ data: [String: Any]) {
        activeButton = (data["buttons"] as? Int ?? 0) & 2 != 0 ? .right : .left
    }

    func emit(_ type: CGEventType, _ name: String, _ data: [String: Any], entering: Bool? = nil) {
        let pen = data["pen"] as? Bool ?? true
        let pressure = pressed ? min(1, max(0, data["pressure"] as? Double ?? 0)) : 0
        let event: CGEvent?
        if type == .tabletProximity || type == .tabletPointer {
            event = CGEvent(source: source); event?.type = type; event?.location = point
        } else {
            event = CGEvent(mouseEventSource: source, mouseType: type, mouseCursorPosition: point, mouseButton: activeButton)
        }
        guard let event = event else { return }
        if let entering = entering {
            event.setIntegerValueField(.tabletProximityEventEnterProximity, value: entering ? 1 : 0)
            event.setIntegerValueField(.tabletProximityEventPointerType, value: 1) // NX_TABLET_POINTER_PEN
            event.setIntegerValueField(.tabletProximityEventVendorPointerType, value: 1)
            event.setIntegerValueField(.tabletProximityEventDeviceID, value: 1)
            event.setIntegerValueField(.tabletProximityEventPointerID, value: 1)
            event.setIntegerValueField(.tabletProximityEventSystemTabletID, value: 1)
            event.setIntegerValueField(.tabletProximityEventVendorUniqueID, value: 1)
            // IOLLEvent.h: device ID, absolute X/Y, buttons, tilt X/Y, pressure.
            event.setIntegerValueField(.tabletProximityEventCapabilityMask, value: 0x5c7)
        } else {
            event.setIntegerValueField(.mouseEventNumber, value: strokeNumber)
            event.setIntegerValueField(.mouseEventClickState, value: 1)
            event.setDoubleValueField(.mouseEventPressure, value: pressure)
            if pen {
                event.setIntegerValueField(.mouseEventSubtype, value: Int64(CGEventMouseSubtype.tabletPoint.rawValue))
                event.setDoubleValueField(.tabletEventPointPressure, value: pressure)
                event.setDoubleValueField(.tabletEventTiltX, value: (data["tiltX"] as? Double ?? 0) / 90)
                event.setDoubleValueField(.tabletEventTiltY, value: (data["tiltY"] as? Double ?? 0) / 90)
                event.setIntegerValueField(.tabletEventDeviceID, value: 1)
                event.setIntegerValueField(.tabletEventPointButtons, value: pressed ? (activeButton == .right ? 2 : 1) : 0)
                event.setIntegerValueField(.tabletEventPointX, value: Int64(data["tabletX"] as? Double ?? 0))
                event.setIntegerValueField(.tabletEventPointY, value: Int64(data["tabletY"] as? Double ?? 0))
            }
        }
        if tracing {
            output(["event": name, "x": point.x, "y": point.y, "pressure": pressure,
                    "pressed": pressed, "pen": pen, "deviceID": 1, "stroke": strokeNumber,
                    "cgType": event.type.rawValue, "button": event.getIntegerValueField(.mouseEventButtonNumber)])
        } else { event.post(tap: .cghidEventTap) }
    }
    func enter(_ data: [String: Any]) {
        if data["pen"] as? Bool != false && !inRange {
            inRange = true; emit(.tabletProximity, "proximityEnter", data, entering: true)
        }
    }
    func lift(_ data: [String: Any]) {
        if pressed { pressed = false; emit(upType, "up", data); activeButton = .left }
    }
    func reset(blockMoves: Bool = false) {
        mouse.reset(blockMoves: blockMoves)
        lift(last)
        if inRange { emit(.tabletProximity, "proximityLeave", last, entering: false); inRange = false }
        cancelled = blockMoves
    }
    func handle(_ data: [String: Any]) {
        guard let kind = data["type"] as? String else { return }
        let plain = data["pen"] as? Bool == false || (data["pen"] == nil && mouseMode)
        if plain {
            if !mouseMode { reset(); mouseMode = true }
            mouse.handle(data); return
        }
        if mouseMode { mouse.reset(); mouseMode = false }
        // Cancellation/reset must release at the last accepted position, never jump.
        if kind == "cancel" || kind == "reset" { reset(blockMoves: kind == "cancel"); return }
        if kind == "leave" { reset(); return }
        if kind == "move" && cancelled { return }
        if kind == "enter" || kind == "down" { cancelled = false }
        if kind == "down" && pressed { lift(last) }
        if (last["pen"] as? Bool ?? true) != (data["pen"] as? Bool ?? true) { reset() }
        let previous = point
        point = CGPoint(x: data["x"] as? Double ?? point.x, y: data["y"] as? Double ?? point.y)
        last = data
        switch kind {
        case "enter":
            enter(data)
            if !pressed { emit(.mouseMoved, "hover", data) }
        case "down":
            if (data["buttons"] as? Int ?? 1) & 1 == 0 {
                enter(data); emit(.mouseMoved, "hover", data); return
            }
            lift(data); enter(data); strokeNumber += 1
            chooseButton(data); pressed = true; emit(downType, "down", data)
        case "move":
            enter(data)
            if let buttons = data["buttons"] as? Int {
                if pressed && buttons & 1 == 0 { lift(data) }
                else if !pressed && buttons & 1 != 0 {
                    strokeNumber += 1; chooseButton(data); pressed = true; emit(downType, "down", data)
                }
            }
            if pressed && previous == point && data["pen"] as? Bool != false {
                emit(.tabletPointer, "tabletPoint", data)
            } else {
                emit(pressed ? dragType : .mouseMoved, pressed ? "drag" : "hover", data)
            }
        case "up": lift(data) // Still in proximity: hovering after up is valid.
        default: break
        }
    }
}
let input = PenInput()
let touchGestures = TouchGestures()

class MappingView: NSView {
    weak var owner: DesktopController?
    override func draw(_ dirtyRect: NSRect) {
        NSColor.systemMint.withAlphaComponent(0.12).setFill()
        bounds.fill()
        NSColor.systemMint.setStroke()
        let border = NSBezierPath(rect: bounds.insetBy(dx: 2, dy: 2))
        border.lineWidth = 3; border.stroke()
        let text = "平板映射区域\n拖动移动 · 右下角等比缩放"
        NSColor.black.withAlphaComponent(0.65).setFill()
        NSBezierPath(roundedRect: NSRect(x: 12, y: bounds.height - 84, width: min(360, bounds.width - 160), height: 72),
                     xRadius: 10, yRadius: 10).fill()
        let attrs: [NSAttributedString.Key: Any] = [.font: NSFont.systemFont(ofSize: 17, weight: .semibold),
                                                   .foregroundColor: NSColor.white]
        (text as NSString).draw(in: NSRect(x: 24, y: bounds.height - 76, width: max(1, min(330, bounds.width - 184)), height: 54), withAttributes: attrs)
        NSColor.systemMint.setFill()
        NSBezierPath(roundedRect: NSRect(x: bounds.width - 132, y: bounds.height - 48, width: 116, height: 32),
                     xRadius: 8, yRadius: 8).fill()
        ("完成调整" as NSString).draw(at: NSPoint(x: bounds.width - 112, y: bounds.height - 42),
                                   withAttributes: [.font: NSFont.systemFont(ofSize: 16, weight: .semibold), .foregroundColor: NSColor.black])
        NSColor.systemMint.setFill()
        NSRect(x: bounds.width - 24, y: 0, width: 24, height: 24).fill()
    }
    override func mouseDown(with event: NSEvent) {
        guard let window = window, let owner = owner else { return }
        let p = convert(event.locationInWindow, from: nil)
        if p.x > bounds.width - 132 && p.y > bounds.height - 48 { owner.toggleOverlay(); return }
        let resize = p.x > bounds.width - 36 && p.y < 36
        let origin = NSEvent.mouseLocation, initial = window.frame
        while let e = NSApp.nextEvent(matching: [.leftMouseDragged, .leftMouseUp], until: .distantFuture,
                                     inMode: .eventTracking, dequeue: true) {
            if e.type == .leftMouseUp { break }
            let m = NSEvent.mouseLocation
            var rect = initial
            if resize {
                rect.size.width = max(360, initial.width + m.x - origin.x)
                rect.size.height = rect.width / owner.ratio
                rect.origin.y = initial.maxY - rect.height
            } else {
                rect.origin.x += m.x - origin.x; rect.origin.y += m.y - origin.y
            }
            window.setFrame(rect, display: true)
            owner.publishFrame()
        }
    }
}

class DesktopController: NSObject {
    let panel = NSPanel(contentRect: .zero, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
    let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
    let toggleItem = NSMenuItem(title: "显示映射框（调整位置与大小）", action: #selector(toggleOverlay), keyEquivalent: "")
    let pauseItem = NSMenuItem(title: "暂停输入", action: #selector(togglePause), keyEquivalent: "")
    let connectionItem = NSMenuItem(title: "等待平板连接…", action: nil, keyEquivalent: "")
    var ratio = 4.0 / 3.0
    var paused = false
    var configured = false
    var port = 18765
    override init() {
        super.init()
        item.button?.image = NSImage(systemSymbolName: "pencil.tip.crop.circle", accessibilityDescription: "Pad as Stylus")
        item.button?.toolTip = "Pad as Stylus · 平板输入"
        let menu = NSMenu()
        let title = NSMenuItem(title: "Pad as Stylus", action: nil, keyEquivalent: "")
        menu.addItem(title); menu.addItem(connectionItem); menu.addItem(.separator())
        toggleItem.target = self; pauseItem.target = self
        menu.addItem(toggleItem); menu.addItem(pauseItem)
        let settings = NSMenuItem(title: "查看连接状态与高级设置…", action: #selector(openSettings), keyEquivalent: "")
        settings.target = self; menu.addItem(settings)
        menu.addItem(.separator())
        let quit = NSMenuItem(title: "退出 Pad as Stylus", action: #selector(quitApp), keyEquivalent: "")
        quit.target = self; menu.addItem(quit)
        item.menu = menu
        panel.level = .floating
        panel.isOpaque = false; panel.backgroundColor = .clear; panel.hasShadow = true
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.hidesOnDeactivate = false
        let view = MappingView(); view.owner = self; panel.contentView = view
    }
    func apply(_ data: [String: Any]) {
        ratio = data["ratio"] as? Double ?? ratio
        port = data["port"] as? Int ?? port
        connectionItem.title = data["connected"] as? Bool == true ? "● 平板已连接" : "○ 等待平板开始书写"
        let w = data["width"] as? Double ?? 800
        let top = CGDisplayBounds(CGMainDisplayID()).height
        panel.setFrame(NSRect(x: data["x"] as? Double ?? 0,
                              y: top - (data["y"] as? Double ?? 0) - w / ratio,
                              width: w, height: w / ratio), display: true)
        panel.contentView?.needsDisplay = true
        if !configured {
            configured = true; publishState()
            // Optional QA capture renders this view only, never the user's desktop.
            if let path = ProcessInfo.processInfo.environment["PAD_STYLUS_UI_PREVIEW"],
               let view = panel.contentView,
               let bitmap = view.bitmapImageRepForCachingDisplay(in: view.bounds) {
                view.cacheDisplay(in: view.bounds, to: bitmap)
                try? bitmap.representation(using: .png, properties: [:])?.write(to: URL(fileURLWithPath: path))
            }
        }
    }
    func publishFrame() {
        let r = panel.frame, top = CGDisplayBounds(CGMainDisplayID()).height
        output(["type": "mapping", "x": r.minX, "y": top - r.maxY, "width": r.width])
    }
    func publishState() {
        output(["type": "suspended", "value": paused || panel.isVisible])
    }
    @objc func toggleOverlay() {
        if panel.isVisible { panel.orderOut(nil) } else { panel.orderFrontRegardless() }
        toggleItem.title = panel.isVisible ? "隐藏映射框并开始输入" : "显示映射框（调整位置与大小）"
        publishState()
    }
    @objc func togglePause() {
        paused.toggle(); pauseItem.state = paused ? .on : .off
        pauseItem.title = paused ? "恢复输入" : "暂停输入"
        publishState()
    }
    @objc func openSettings() { NSWorkspace.shared.open(URL(string: "http://localhost:\(port)/settings")!) }
    @objc func quitApp() {
        input.reset(); touchGestures.reset()
        output(["type": "quit"]); NSApp.terminate(nil)
    }
}

let app: NSApplication? = tracing ? nil : NSApplication.shared
app?.setActivationPolicy(.accessory)
let desktop: DesktopController? = tracing ? nil : DesktopController()
func handle(_ data: [String: Any]) {
    guard let kind = data["type"] as? String else { return }
    if kind == "config" { desktop?.apply(data); return }
    if kind == "gestures" { touchGestures.configure(data); return }
    if kind.hasPrefix("touch_") { touchGestures.handle(data); return }
    if kind == "reset" { touchGestures.reset() }
    input.handle(data)
}
if tracing {
    while let line = readLine() {
        if let bytes = line.data(using: .utf8), let data = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any] { handle(data) }
    }
    input.reset(); touchGestures.reset(); exit(0)
}
DispatchQueue.global(qos: .userInteractive).async {
 while let line = readLine() {
    guard let bytes = line.data(using: .utf8),
          let data = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any],
          data["type"] as? String != nil else { continue }
    DispatchQueue.main.async { handle(data) }
 }
 DispatchQueue.main.async {
    input.reset(); touchGestures.reset()
    NSApp.terminate(nil)
 }
}
app?.run()
