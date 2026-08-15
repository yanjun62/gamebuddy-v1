// GameBuddyOverlay — Game Buddy 的 macOS 原生悬浮气泡
//
// 为什么不用原来那个 tkinter 气泡：macOS 自带的 Tk 是 8.5（Apple 2010 年之后就没更新，
// 官方文档自己标了 deprecated）。在 macOS 26 上它连背景色都画不出来，整个窗口一片白，
// 输入框和文字全部不可见。装 python.org 的 Python 能绕过去，但那是为一个死掉的 GUI 库
// 再养一套运行时。这里用系统自带的 Swift + AppKit/SwiftUI 重写，零安装。
//
// 桥协议跟 Windows 版完全一致，所以后端（Codex 直连桥 / 别的接管者）不用改一行：
//   写 message_queue.jsonl  ← 玩家说的话（JSONL 追加，一行一条）
//   读 danmaku.txt          ← 陪玩的回复（改动 mtime 即触发显示）
//
// 编译：
//   swiftc -O GameBuddyOverlay.swift -o GameBuddyOverlay
// 运行（BASE_DIR 默认取可执行文件的上一级，也可以用参数指定）：
//   ./GameBuddyOverlay [项目目录]

import AppKit
import CoreAudio
import SwiftUI

// MARK: - 配置

/// 读写 config.json。改动只覆盖自己认识的键，其余原样写回——
/// 这个文件是两个平台共用的，不能因为 macOS 端不认识某个键就把它吃掉。
final class ConfigStore: ObservableObject {
    @Published var spoilerMode: String = "safe"
    @Published var gameProfile: String = ""
    @Published var knowledgeEnabled: Bool = true
    /// 跟 Tk 前端共用同一个键，两边选的主题是同一个
    @Published var overlayTheme: String = "dopamine-sunset"
    /// 气泡上显示的名字，两个平台共用同一组键
    @Published var playerName: String = "我"
    @Published var buddyName: String = "陪玩"

    private let url: URL
    private var raw: [String: Any] = [:]

    init(baseDir: URL) {
        url = baseDir.appendingPathComponent("config.json")
        reload()
    }

    func reload() {
        guard
            let data = try? Data(contentsOf: url),
            let dict = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
        else { return }
        raw = dict
        spoilerMode = dict["spoiler_mode"] as? String ?? "safe"
        gameProfile = dict["game_profile"] as? String ?? ""
        knowledgeEnabled = dict["knowledge_enabled"] as? Bool ?? true
        overlayTheme = dict["overlay_theme"] as? String ?? "dopamine-sunset"
        playerName = (dict["player_name"] as? String)?.trimmed ?? "我"
        buddyName = (dict["buddy_name"] as? String)?.trimmed ?? "陪玩"
    }

    func save() {
        raw["spoiler_mode"] = spoilerMode
        raw["game_profile"] = gameProfile
        raw["knowledge_enabled"] = knowledgeEnabled
        raw["overlay_theme"] = overlayTheme
        raw["player_name"] = playerName
        raw["buddy_name"] = buddyName
        guard
            let data = try? JSONSerialization.data(
                withJSONObject: raw, options: [.prettyPrinted, .withoutEscapingSlashes]
            )
        else { return }
        try? data.write(to: url, options: .atomic)
    }
}

/// 剧透档位，标签跟 game_knowledge.py 里的 SPOILER_LABELS 一字不差。
enum Spoiler {
    static let order = ["safe", "current-game", "full"]
    static let labels = [
        "safe": "安全（不剧透）",
        "current-game": "当前进度攻略",
        "full": "完整剧透攻略",
    ]
    static func label(_ key: String) -> String { labels[key] ?? labels["safe"]! }
}

// MARK: - 麦克风

/// 有没有可用的输入设备。走 CoreAudio 直接问，不碰 AVCaptureDevice——
/// 后者会弹麦克风权限请求，而我们只是想知道按钮该不该点亮。
func hasAudioInput() -> Bool {
    var address = AudioObjectPropertyAddress(
        mSelector: kAudioHardwarePropertyDevices,
        mScope: kAudioObjectPropertyScopeGlobal,
        mElement: kAudioObjectPropertyElementMain
    )
    var size: UInt32 = 0
    guard
        AudioObjectGetPropertyDataSize(AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size) == noErr,
        size > 0
    else { return false }

    var devices = [AudioDeviceID](repeating: 0, count: Int(size) / MemoryLayout<AudioDeviceID>.size)
    guard
        AudioObjectGetPropertyData(AudioObjectID(kAudioObjectSystemObject), &address, 0, nil, &size, &devices) == noErr
    else { return false }

    for device in devices {
        var streams = AudioObjectPropertyAddress(
            mSelector: kAudioDevicePropertyStreamConfiguration,
            mScope: kAudioDevicePropertyScopeInput,
            mElement: kAudioObjectPropertyElementMain
        )
        var listSize: UInt32 = 0
        guard AudioObjectGetPropertyDataSize(device, &streams, 0, nil, &listSize) == noErr, listSize > 0 else { continue }
        let buffer = UnsafeMutableRawPointer.allocate(byteCount: Int(listSize), alignment: 16)
        defer { buffer.deallocate() }
        guard AudioObjectGetPropertyData(device, &streams, 0, nil, &listSize, buffer) == noErr else { continue }
        let list = UnsafeMutableAudioBufferListPointer(buffer.assumingMemoryBound(to: AudioBufferList.self))
        if list.contains(where: { $0.mNumberChannels > 0 }) { return true }
    }
    return false
}

// MARK: - 桥协议

/// 与 bridge_protocol.py 对应：同样的文件名、同样的 JSONL 记录格式。
final class Bridge: ObservableObject {
    struct Line: Identifiable {
        let id = UUID()
        let text: String
        let fromBuddy: Bool
    }

    @Published var lines: [Line] = []

    private let baseDir: URL
    private var queueURL: URL { baseDir.appendingPathComponent("message_queue.jsonl") }
    private var danmakuURL: URL { baseDir.appendingPathComponent("danmaku.txt") }
    private var legacyURL: URL { baseDir.appendingPathComponent("message.txt") }

    private var historyURL: URL { baseDir.appendingPathComponent("chat_history.txt") }

    private var lastDanmakuStamp: Date?
    private var timer: Timer?

    init(baseDir: URL) {
        self.baseDir = baseDir
        // 启动时先记下当前 mtime，免得把上一局的旧回复当成新的弹出来
        lastDanmakuStamp = Self.modified(danmakuURL)
        loadHistory()
    }

    /// 读回上次的聊天记录，格式跟 Windows 版一致：`[Buddy] [12:54] 内容`
    private func loadHistory() {
        guard let text = try? String(contentsOf: historyURL, encoding: .utf8) else { return }
        for line in text.split(separator: "\n", omittingEmptySubsequences: true).suffix(40) {
            let s = String(line)
            guard let close = s.range(of: "] ["), let end = s.range(of: "] ", range: close.upperBound..<s.endIndex)
            else { continue }
            let who = String(s[s.index(after: s.startIndex)..<close.lowerBound])
            let body = String(s[end.upperBound...])
            guard !body.isEmpty else { continue }
            lines.append(Line(text: body, fromBuddy: who == "Buddy"))
        }
    }

    private func appendHistory(_ text: String, fromBuddy: Bool) {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm"
        let entry = "[\(fromBuddy ? "Buddy" : "Player")] [\(formatter.string(from: Date()))] \(text)\n"
        if let handle = try? FileHandle(forWritingTo: historyURL) {
            defer { try? handle.close() }
            try? handle.seekToEnd()
            try? handle.write(contentsOf: Data(entry.utf8))
        } else {
            try? Data(entry.utf8).write(to: historyURL, options: .atomic)
        }
    }

    func startWatching() {
        timer = Timer.scheduledTimer(withTimeInterval: 0.75, repeats: true) { [weak self] _ in
            self?.pollDanmaku()
        }
    }

    private static func modified(_ url: URL) -> Date? {
        try? FileManager.default.attributesOfItem(atPath: url.path)[.modificationDate] as? Date
    }

    private func pollDanmaku() {
        guard let stamp = Self.modified(danmakuURL) else { return }
        if let last = lastDanmakuStamp, stamp <= last { return }
        lastDanmakuStamp = stamp
        guard let raw = try? String(contentsOf: danmakuURL, encoding: .utf8) else { return }
        let text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        append(text, fromBuddy: true)
    }

    /// 玩家发言：先上屏，再落盘。落盘失败要说出来，不能默默吞掉。
    func send(_ raw: String) {
        let text = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        append(text, fromBuddy: false)

        let record: [String: Any] = [
            "id": UUID().uuidString.lowercased(),
            "created_at": ISO8601DateFormatter().string(from: Date()),
            "text": text,
        ]
        guard
            let data = try? JSONSerialization.data(withJSONObject: record, options: [.withoutEscapingSlashes]),
            var line = String(data: data, encoding: .utf8)
        else {
            append("（这句没能写进队列，后端收不到）", fromBuddy: true)
            return
        }
        line += "\n"

        do {
            if !FileManager.default.fileExists(atPath: queueURL.path) {
                FileManager.default.createFile(atPath: queueURL.path, contents: nil)
            }
            let handle = try FileHandle(forWritingTo: queueURL)
            defer { try? handle.close() }
            try handle.seekToEnd()
            try handle.write(contentsOf: Data(line.utf8))
            try? Data(text.utf8).write(to: legacyURL, options: .atomic)  // 兼容旧的单条文件
        } catch {
            append("（写队列失败：\(error.localizedDescription)）", fromBuddy: true)
        }
    }

    private func append(_ text: String, fromBuddy: Bool) {
        lines.append(Line(text: text, fromBuddy: fromBuddy))
        if lines.count > 60 { lines.removeFirst(lines.count - 60) }
        appendHistory(text, fromBuddy: fromBuddy)
    }

    /// helper 的结果。不用 Result 是因为失败信息就是一句人话，
    /// 为它单造一个 Error 类型没意义。
    enum HelperOutcome {
        case ok(String)
        case failed(String)
    }

    /// 调 gb_helper.py。逻辑全在 Python 那边，这里只负责起进程收结果，
    /// 保证 macOS 端和 Windows 端用的是同一份词库／语音代码。
    func runHelper(_ command: String) -> HelperOutcome {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        process.arguments = [baseDir.appendingPathComponent("gb_helper.py").path, command]
        process.currentDirectoryURL = baseDir
        let out = Pipe(), err = Pipe()
        process.standardOutput = out
        process.standardError = err
        do {
            try process.run()
        } catch {
            return .failed("起不来 gb_helper.py：\(error.localizedDescription)")
        }
        let outData = out.fileHandleForReading.readDataToEndOfFile()
        let errData = err.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        let stdout = String(data: outData, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let stderr = String(data: errData, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if process.terminationStatus != 0 {
            return .failed(stderr.isEmpty ? "helper 退出码 \(process.terminationStatus)" : stderr)
        }
        return .ok(stdout)
    }

    /// 直接把一句话放进气泡，不写队列——用于状态提示、致谢正文这类本地内容。
    func note(_ text: String) {
        append(text, fromBuddy: true)
    }
}

// MARK: - 配色

/// 相对亮度（WCAG）。用来判断某个底色上该配深字还是浅字。
private func relativeLuminance(_ hex: String) -> Double {
    let raw = hex.trimmingCharacters(in: CharacterSet(charactersIn: "#")).uppercased()
    var v: UInt64 = 0
    guard raw.count == 6, Scanner(string: raw).scanHexInt64(&v) else { return 0.5 }
    func chan(_ c: Double) -> Double { c <= 0.03928 ? c / 12.92 : pow((c + 0.055) / 1.055, 2.4) }
    let r = chan(Double((v >> 16) & 0xFF) / 255.0)
    let g = chan(Double((v >> 8) & 0xFF) / 255.0)
    let b = chan(Double(v & 0xFF) / 255.0)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

/// 底色与字色的对比度（1…21）。低于 4.5 就算读不清。
private func contrastRatio(_ a: String, _ b: String) -> Double {
    let l1 = relativeLuminance(a), l2 = relativeLuminance(b)
    let hi = max(l1, l2), lo = min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)
}

/// 字色读不清时的兜底：暗底给浅字，亮底给深字。
///
/// 某些深色主题若把 buddy_text 填成近黑色，对比度会接近 1:1。
/// 调色数据也供 Tk 前端使用，因此在渲染层统一兜底，避免新主题填错后文字隐形。
private func readableText(on background: String, preferred: String) -> Color {
    if contrastRatio(background, preferred) >= 4.5 { return Color(hex: preferred) }
    return relativeLuminance(background) < 0.45
        ? Color(hex: "#F6F8FC")   // 暗底 → 近白
        : Color(hex: "#1B1620")   // 亮底 → 近黑
}

extension String {
    /// 去空白；全空白当成没填，交给调用方走默认值
    var trimmed: String? {
        let t = trimmingCharacters(in: .whitespacesAndNewlines)
        return t.isEmpty ? nil : t
    }
}

extension Color {
    /// #RRGGBB → Color。解析不了就退回灰色，不崩。
    init(hex: String) {
        let raw = hex.trimmingCharacters(in: CharacterSet(charactersIn: "#")).uppercased()
        var value: UInt64 = 0
        guard raw.count == 6, Scanner(string: raw).scanHexInt64(&value) else {
            self = Color(red: 0.5, green: 0.5, blue: 0.5); return
        }
        self = Color(
            red: Double((value >> 16) & 0xFF) / 255.0,
            green: Double((value >> 8) & 0xFF) / 255.0,
            blue: Double(value & 0xFF) / 255.0
        )
    }
}

/// 主题调色板。所有配色只在 overlay_themes.py 里定义一次，
/// Tk 前端和这个 AppKit 前端读同一份——改主题不用改两遍。
/// 这里通过 macos/theme_bridge.py 取，取不到就退回内置的粉白（原「小花仙」配色）。
final class Palette: ObservableObject {
    @Published private(set) var id = "petal"
    @Published private(set) var displayName = "花瓣"
    @Published private(set) var badge = ""
    /// 该主题的背景图（assets/themes/<id>/）。没有素材的主题就是 nil。
    @Published private(set) var background: NSImage?
    @Published private(set) var frame: NSImage?
    /// 标题字样：像素风给田园/像素主题，复古给历史/奇幻，科幻给 HUD 主题
    @Published private(set) var wordmark: NSImage?

    @Published var deep = Color(red: 0.93, green: 0.55, blue: 0.72)
    @Published var mid = Color(red: 0.98, green: 0.78, blue: 0.87)
    @Published var pale = Color(red: 1.00, green: 0.94, blue: 0.97)
    @Published var ink = Color(red: 0.40, green: 0.24, blue: 0.33)
    @Published var lilac = Color(red: 0.83, green: 0.76, blue: 0.95)
    @Published var accent = Color(red: 0.93, green: 0.55, blue: 0.72)

    // 每处文字都有自己的底色和字色，不能共用一个 ink——
    // 深色主题上白底黑字混深底会整片糊掉（2026-08-11 Kate 报的）
    @Published var buddyFill = Color(red: 0.83, green: 0.76, blue: 0.95)
    @Published var buddyText = Color(red: 0.40, green: 0.24, blue: 0.33)
    @Published var buddyBorder = Color(red: 0.83, green: 0.76, blue: 0.95)
    @Published var playerFill = Color.white
    @Published var playerText = Color(red: 0.40, green: 0.24, blue: 0.33)
    @Published var playerBorder = Color(red: 0.98, green: 0.78, blue: 0.87)
    @Published var systemText = Color(red: 0.40, green: 0.24, blue: 0.33).opacity(0.7)
    @Published var entryFill = Color.white
    @Published var entryText = Color(red: 0.40, green: 0.24, blue: 0.33)

    private let projectURL: URL
    init(projectURL: URL) { self.projectURL = projectURL }

    struct Choice: Identifiable, Hashable {
        let id: String
        let displayName: String
        let badge: String
    }
    @Published private(set) var choices: [Choice] = []

    func loadChoices() {
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self, let obj = self.runBridge(["list"]),
                  let list = obj["themes"] as? [[String: Any]] else { return }
            let parsed: [Choice] = list.compactMap {
                guard let id = $0["id"] as? String else { return nil }
                return Choice(id: id,
                              displayName: $0["display_name"] as? String ?? id,
                              badge: $0["badge"] as? String ?? "")
            }
            DispatchQueue.main.async { self.choices = parsed }
        }
    }

    /// 换主题。
    ///
    /// ⚠ runBridge 会 spawn python 并阻塞等它退出——绝对不能在主线程调用，
    /// 在 runloop 回调里等子进程会撞 UpdateCycle 直接段错误（2026-08-11 实测）。
    /// 所以线程处理收在这里：子进程在后台跑，@Published 赋值回主线程。
    /// 调用方任何线程都能直接调，不用自己包 dispatch。
    func apply(_ themeId: String?) {
        DispatchQueue.global(qos: .userInitiated).async { [weak self] in
            guard let self, let obj = self.runBridge(["resolve", themeId ?? ""]),
                  let theme = obj["theme"] as? [String: Any] else { return }
            DispatchQueue.main.async { self.assign(theme) }
        }
    }

    /// 只在主线程调用：这里全是 @Published 赋值。
    private func assign(_ t: [String: Any]) {
        func c(_ key: String, _ fallback: Color) -> Color {
            guard let hex = t[key] as? String else { return fallback }
            return Color(hex: hex)
        }
        id = t["id"] as? String ?? id
        displayName = t["display_name"] as? String ?? displayName
        badge = t["badge"] as? String ?? ""
        // 映射：surface→面，chat→底，accent→强调，气泡各自取自己的填充色
        pale = c("chat_bg", pale)
        mid = c("surface_bg", mid)
        deep = c("accent", deep)
        accent = c("accent", accent)
        // ink 只用于「画在 surface 上的」小标题和图标，所以取 entry_fg 那档亮度
        ink = c("entry_fg", ink)
        lilac = c("buddy_fill", lilac)
        buddyFill = c("buddy_fill", buddyFill)
        if let bg = t["buddy_fill"] as? String, let fg = t["buddy_text"] as? String {
            buddyText = readableText(on: bg, preferred: fg)
        } else { buddyText = c("buddy_text", buddyText) }
        buddyBorder = c("buddy_border", buddyBorder)
        playerFill = c("player_fill", playerFill)
        if let bg = t["player_fill"] as? String, let fg = t["player_text"] as? String {
            playerText = readableText(on: bg, preferred: fg)
        } else { playerText = c("player_text", playerText) }
        playerBorder = c("player_border", playerBorder)
        if let bg = t["chat_bg"] as? String, let fg = t["system_fg"] as? String {
            systemText = readableText(on: bg, preferred: fg)
        } else { systemText = c("system_fg", systemText) }
        loadAssets(for: id)
        entryFill = c("entry_bg", entryFill)
        if let bg = t["entry_bg"] as? String, let fg = t["entry_fg"] as? String {
            entryText = readableText(on: bg, preferred: fg)
        } else { entryText = c("entry_fg", entryText) }
    }

    /// 载入该主题的图片素材。
    ///
    /// assets/themes/<id>/ 下优先读取 background-v2.png，再回退到 background-v1.png。
    /// 三套多巴胺主题没有素材目录，本来就是纯色渐变风，缺图不是错误。
    private func loadAssets(for themeId: String) {
        let dir = projectURL
            .appendingPathComponent("assets/themes", isDirectory: true)
            .appendingPathComponent(themeId, isDirectory: true)
        func image(_ name: String) -> NSImage? {
            let url = dir.appendingPathComponent(name)
            guard FileManager.default.fileExists(atPath: url.path) else { return nil }
            return NSImage(contentsOf: url)
        }
        background = image("background-v2.png") ?? image("background-v1.png")
        frame = nil  // 主题只使用背景和标题字标，不再显示任何聊天边框

        // 标题字样按主题气质挑，README 里给的建议：
        // 像素→田园/像素，复古→历史/奇幻，科幻→HUD
        let pick: String
        switch themeId {
        case "pixel-farm": pick = "gamebuddy-pixel-v1.png"
        case "candlelit-codex", "crimson-memory", "gilded-court", "elysian-world": pick = "gamebuddy-retro-v1.png"
        case "synthetic-detective", "holographic-star-map", "crystal-fantasy": pick = "gamebuddy-scifi-v1.png"
        default: pick = ""   // 多巴胺三套用文字标题，不套字样
        }
        if pick.isEmpty {
            wordmark = nil
        } else {
            let url = projectURL
                .appendingPathComponent("assets/wordmarks", isDirectory: true)
                .appendingPathComponent(pick)
            wordmark = FileManager.default.fileExists(atPath: url.path) ? NSImage(contentsOf: url) : nil
        }
    }

    private func runBridge(_ args: [String]) -> [String: Any]? {
        let script = projectURL.appendingPathComponent("macos/theme_bridge.py")
        guard FileManager.default.fileExists(atPath: script.path) else { return nil }
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/python3")
        process.arguments = [script.path] + args
        process.currentDirectoryURL = projectURL
        let pipe = Pipe()
        process.standardOutput = pipe
        process.standardError = FileHandle.nullDevice
        do { try process.run() } catch { return nil }
        let data = pipe.fileHandleForReading.readDataToEndOfFile()
        process.waitUntilExit()
        return (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
    }
}

// MARK: - 飘落的装饰

// 飘落的花瓣蝴蝶小精灵已按 Kate 2026-08-11 的要求移除。

// MARK: - 主界面

private struct OverlayView: View {
    @ObservedObject var bridge: Bridge
    @ObservedObject var config: ConfigStore
    @ObservedObject var palette: Palette
    @State private var draft = ""
    @State private var showMenu = false
    @State private var recording = false
    @State private var confirmingFullSpoiler = false
    @State private var profiles: [(String, String)] = []
    @FocusState private var inputFocused: Bool

    private let micAvailable = hasAudioInput()

    var body: some View {
        ZStack {
            // 有素材的主题铺场景图，没有的用纯色渐变（多巴胺三套）。
            // 图上压一层同色薄纱：素材中段本来就留空，但字压在画上还是要托一下。
            if let bg = palette.background {
                Image(nsImage: bg)
                    .resizable()
                    .aspectRatio(contentMode: .fill)
                    .overlay(palette.pale.opacity(palette.id == "synthetic-detective" ? 0.20 : palette.id == "elysian-world" ? 0.28 : 0.62))
            } else {
                LinearGradient(
                    colors: [palette.pale, palette.mid.opacity(0.55), palette.pale],
                    startPoint: .top, endPoint: .bottom
                )
            }

            VStack(spacing: 0) {
                header
                Divider().background(palette.mid.opacity(0.6))
                transcript
                composer
            }
        }
        .background(.ultraThinMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .strokeBorder(palette.mid, lineWidth: 1.5)
        )
        .onAppear { inputFocused = true }
    }

    private var header: some View {
        HStack(spacing: 6) {
            // 有字样素材就用图，没有就用文字。
            // 两种情况都带 accessibilityLabel，读屏和本地化不受影响。
            if let mark = palette.wordmark {
                Image(nsImage: mark)
                    .resizable()
                    .scaledToFill()
                    .frame(width: 142, height: 28, alignment: .leading)
                    .accessibilityLabel("Game Buddy")
            } else {
                Text("Game Buddy")
                    .font(.system(size: 15, weight: .bold, design: .rounded))
                    .foregroundStyle(palette.deep)
            }
            Spacer()
            Button {
                NSApp.terminate(nil)
            } label: {
                Image(systemName: "xmark")
                    .font(.system(size: 9, weight: .bold))
                    .foregroundStyle(palette.deep.opacity(0.7))
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(WindowDragArea())  // 没有标题栏，整条头部都能拖
    }

    private var transcript: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 8) {
                    if bridge.lines.isEmpty {
                        Text("在的。说点什么吧～")
                            .font(.system(size: 12, design: .rounded))
                            .foregroundStyle(palette.systemText)
                            .padding(.top, 12)
                    }
                    ForEach(bridge.lines) { line in
                        bubble(for: line)
                            .frame(maxWidth: .infinity, alignment: line.fromBuddy ? .leading : .trailing)
                            .id(line.id)
                    }
                }
                // 默认尺寸下左右留白一致，避免气泡贴边。
                .padding(.horizontal, 16)
                .padding(.vertical, 10)
            }
            .scrollIndicators(.hidden)
            .onChange(of: bridge.lines.count) {
                if let last = bridge.lines.last {
                    withAnimation(.easeOut(duration: 0.25)) { proxy.scrollTo(last.id, anchor: .bottom) }
                }
            }
        }
    }

    private func bubble(for line: Bridge.Line) -> some View {
        // 名字压在气泡内部顶上一行，跟正文同一块底色，
        // 所以不用另算对比度——照抄这条气泡自己的字色，压淡一档当次要信息。
        VStack(alignment: line.fromBuddy ? .leading : .trailing, spacing: 2) {
            Text(line.fromBuddy ? config.buddyName : config.playerName)
                .font(.system(size: 9.5, weight: .semibold, design: .rounded))
                .foregroundStyle((line.fromBuddy ? palette.buddyText : palette.playerText).opacity(0.62))
            Text(line.text)
                .font(.system(size: 12.5, design: .rounded))
                .foregroundStyle(line.fromBuddy ? palette.buddyText : palette.playerText)
                .textSelection(.enabled)
        }
            .padding(.horizontal, 10)
            .padding(.vertical, 7)
            .background(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .fill(line.fromBuddy ? palette.buddyFill : palette.playerFill)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 12, style: .continuous)
                    .strokeBorder(line.fromBuddy ? palette.buddyBorder : palette.playerBorder, lineWidth: 1)
            )
    }

    /// 小圆按钮，麦克风和菜单共用一个样子。
    private func roundButton(_ symbol: String, enabled: Bool = true, help: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: symbol)
                .font(.system(size: 12, weight: .semibold))
                .foregroundStyle(enabled ? palette.deep : palette.deep.opacity(0.3))
                .frame(width: 28, height: 28)
                .background(Circle().fill(palette.entryFill.opacity(enabled ? 1.0 : 0.5)))
                .overlay(Circle().strokeBorder(palette.mid, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
        .help(help)
    }

    private var composer: some View {
        HStack(spacing: 8) {
            TextField("说点什么…", text: $draft)
                .textFieldStyle(.plain)
                .font(.system(size: 12.5, design: .rounded))
                .foregroundStyle(palette.entryText)
                .focused($inputFocused)
                .onSubmit(send)
                .padding(.horizontal, 10)
                .padding(.vertical, 7)
                .background(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .fill(palette.entryFill)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .strokeBorder(palette.mid, lineWidth: 1.2)
                )

            roundButton(
                recording ? "waveform" : "mic.fill",
                enabled: micAvailable && !recording,
                help: micAvailable ? "按一下说话，本机转文字，音频不上传" : "这台机器没有可用的麦克风输入设备"
            ) { startVoice() }

            roundButton("line.3.horizontal", help: "游戏 / 词库 / 剧透档位 / 致谢") { showMenu.toggle() }
                .popover(isPresented: $showMenu, arrowEdge: .top) {
                    menu
                        .onAppear { loadProfiles() }
                        // 改完名字直接点外面关掉不会触发 onSubmit，关的时候补存一次
                        .onDisappear { config.save() }
                }

            Button(action: send) {
                Image(systemName: "paperplane.fill")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(.white)
                    .frame(width: 30, height: 30)
                    .background(Circle().fill(palette.deep))
            }
            .buttonStyle(.plain)
            .disabled(draft.trimmingCharacters(in: .whitespaces).isEmpty)
            .opacity(draft.trimmingCharacters(in: .whitespaces).isEmpty ? 0.45 : 1)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 10)
    }

    // MARK: 菜单

    private var menu: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("陪玩设置")
                .font(.system(size: 15, weight: .bold, design: .rounded))
                .foregroundStyle(palette.deep)

            // 名字：改完立刻写回 config.json，两个平台共用同一组键。
            // 留空不报错，重新读的时候会退回默认（我 / 陪玩）。
            VStack(alignment: .leading, spacing: 5) {
                Text("称呼").font(.system(size: 11)).foregroundStyle(palette.ink.opacity(0.6))
                HStack(spacing: 8) {
                    VStack(alignment: .leading, spacing: 3) {
                        Text("你").font(.system(size: 9.5)).foregroundStyle(palette.ink.opacity(0.45))
                        TextField("我", text: $config.playerName)
                            .textFieldStyle(.roundedBorder)
                            .font(.system(size: 11.5))
                            .frame(width: 112)
                            .onSubmit { config.save() }
                    }
                    VStack(alignment: .leading, spacing: 3) {
                        Text("陪玩").font(.system(size: 9.5)).foregroundStyle(palette.ink.opacity(0.45))
                        TextField("陪玩", text: $config.buddyName)
                            .textFieldStyle(.roundedBorder)
                            .font(.system(size: 11.5))
                            .frame(width: 112)
                            .onSubmit { config.save() }
                    }
                }
            }

            // 主题：选项来自 overlay_themes.py，跟 Tk 前端同一份定义。
            // 选完立刻重算调色板并写回 config.json，两个前端下次打开都是这套。
            VStack(alignment: .leading, spacing: 5) {
                HStack(spacing: 6) {
                    Text("外观主题").font(.system(size: 11)).foregroundStyle(palette.ink.opacity(0.6))
                    if !palette.badge.isEmpty {
                        Text(palette.badge)
                            .font(.system(size: 9, weight: .semibold, design: .rounded))
                            .padding(.horizontal, 5).padding(.vertical, 1)
                            .background(Capsule().fill(palette.accent.opacity(0.22)))
                            .foregroundStyle(palette.accent)
                    }
                }
                Picker("", selection: $config.overlayTheme) {
                    ForEach(palette.choices) { choice in
                        Text(choice.displayName).tag(choice.id)
                    }
                }
                .labelsHidden()
                .frame(width: 240)
                .onChange(of: config.overlayTheme) {
                    // apply 内部要 spawn python 解析配色，同样不能在主线程等
                    config.save()
                    palette.apply(config.overlayTheme)   // apply 内部自己切线程
                }
            }

            VStack(alignment: .leading, spacing: 5) {
                Text("游戏词库").font(.system(size: 11)).foregroundStyle(palette.ink.opacity(0.6))
                Picker("", selection: $config.gameProfile) {
                    Text("不使用词库").tag("")
                    ForEach(profiles, id: \.0) { Text($0.1).tag($0.0) }
                }
                .labelsHidden()
                .frame(width: 240)
                .onChange(of: config.gameProfile) { config.save() }
            }

            Toggle("启用术语检索", isOn: $config.knowledgeEnabled)
                .font(.system(size: 12))
                .onChange(of: config.knowledgeEnabled) { config.save() }

            VStack(alignment: .leading, spacing: 5) {
                Text("攻略 / 剧透").font(.system(size: 11)).foregroundStyle(palette.ink.opacity(0.6))
                ForEach(Spoiler.order, id: \.self) { key in
                    Button {
                        // 开全剧透前再问一次——这是不可逆的体验损失
                        if key == "full" && config.spoilerMode != "full" {
                            confirmingFullSpoiler = true
                        } else {
                            config.spoilerMode = key
                            config.save()
                        }
                    } label: {
                        HStack(spacing: 6) {
                            Image(systemName: config.spoilerMode == key ? "largecircle.fill.circle" : "circle")
                                .foregroundStyle(palette.deep)
                            Text(Spoiler.label(key)).font(.system(size: 12))
                            Spacer()
                        }
                    }
                    .buttonStyle(.plain)
                }
            }

            Divider()

            Button("查看致谢与来源") {
                showMenu = false
                // 同样不能在主线程等子进程，见 loadProfiles 上面那段注释
                DispatchQueue.global(qos: .userInitiated).async {
                    let outcome = bridge.runHelper("credits")
                    DispatchQueue.main.async {
                        switch outcome {
                        case .ok(let text): bridge.note(text)
                        case .failed(let why): bridge.note("读不到致谢：\(why)")
                        }
                    }
                }
            }
            .font(.system(size: 12))
        }
        .padding(16)
        .frame(width: 280)
        .alert("要开完整剧透吗？", isPresented: $confirmingFullSpoiler) {
            Button("取消", role: .cancel) {}
            Button("开", role: .destructive) {
                config.spoilerMode = "full"
                config.save()
            }
        } message: {
            Text("开了之后我会知道后面所有剧情，可能顺嘴说出来。这个看不回去。")
        }
    }

    /// 词库列表来自 gb_helper.py，跟 Windows 版同一份发现逻辑。
    /// ⚠ 这个曾经是计算属性，每次 SwiftUI 重算视图就同步 spawn 一次 python 并
    /// waitUntilExit —— 在 runloop 回调里阻塞等子进程，改主题触发菜单重绘时
    /// 会撞上 UpdateCycle 直接 SIGSEGV（2026-08-11 实测崩溃栈：
    /// OverlayView.profiles.getter → Bridge.runHelper → NSConcreteTask.waitUntilExit）。
    /// 现在只在菜单打开时后台拉一次，结果缓存在 @State 里。
    /// 别改回计算属性。
    private func loadProfiles() {
        guard profiles.isEmpty else { return }
        DispatchQueue.global(qos: .userInitiated).async {
            guard
                case .ok(let json) = bridge.runHelper("profiles"),
                let data = json.data(using: .utf8),
                let root = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                let rows = root["profiles"] as? [[String: Any]]
            else { return }
            let parsed: [(String, String)] = rows.compactMap { row in
                guard let id = row["id"] as? String, let name = row["name"] as? String else { return nil }
                return (id, name)
            }
            DispatchQueue.main.async { profiles = parsed }
        }
    }

    // MARK: 语音

    private func startVoice() {
        recording = true
        bridge.note("🎤 在听…")
        DispatchQueue.global(qos: .userInitiated).async {
            let result = bridge.runHelper("voice")
            DispatchQueue.main.async {
                recording = false
                switch result {
                case .ok(let text):
                    draft = text          // 填进输入框，让她能改完再发
                    inputFocused = true
                case .failed(let why):
                    bridge.note("语音没成：\(why)")
                }
            }
        }
    }

    private func send() {
        bridge.send(draft)
        draft = ""
        inputFocused = true
    }
}

/// 让没有标题栏的窗口也能拖动。
private struct WindowDragArea: NSViewRepresentable {
    final class DragView: NSView {
        override func mouseDown(with event: NSEvent) {
            window?.performDrag(with: event)
        }
    }
    func makeNSView(context: Context) -> NSView { DragView() }
    func updateNSView(_ nsView: NSView, context: Context) {}
}

// MARK: - 窗口

/// 悬浮面板：置顶、不抢焦点、跟着切 Space 走。
/// 不抢焦点这件事对陪玩很关键——点气泡不能把游戏从前台踢下去。
final class OverlayPanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }
}

/// 建面板。
///
/// 刻意不走 NSApplicationDelegate：`NSApplication.delegate` 是 weak 引用，
/// 在 .app bundle 里跑的时候 delegate 会被提前释放，
/// `applicationDidFinishLaunching` 压根不触发 —— 表现是进程起来、退出码 0、一个窗口都没有，
/// 而同一个二进制放在 bundle 外面直接跑却完全正常。改成顶层直接建窗，两种启动方式都稳。
///
/// ⚠ 另一个同类坑（2026-08-11 实测）：在 didFinishLaunching 里一次性铺 50 条聊天记录时，
/// 换行标签（wrappingLabel）如果没给 preferredMaxLayoutWidth，窗口还没显示、容器宽度未定，
/// Auto Layout 会一直重算解不出换行点，卡在那儿永不返回 —— 后面的 makeKeyAndOrderFront
/// 就永远轮不到，症状同样是「进程活着但没有窗口」。SwiftUI 这版不走那条路，但别改回去。
func makePanel(bridge: Bridge, config: ConfigStore, palette: Palette) -> OverlayPanel {
        let content = OverlayView(bridge: bridge, config: config, palette: palette)

        let panel = OverlayPanel(
            contentRect: NSRect(x: 0, y: 0, width: 345, height: 520),
            styleMask: [.nonactivatingPanel, .titled, .fullSizeContentView, .resizable],
            backing: .buffered,
            defer: false
        )
        panel.titleVisibility = .hidden
        panel.titlebarAppearsTransparent = true
        panel.isMovableByWindowBackground = true
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = true
        panel.level = .floating
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.standardWindowButton(.closeButton)?.isHidden = true
        panel.standardWindowButton(.miniaturizeButton)?.isHidden = true
        panel.standardWindowButton(.zoomButton)?.isHidden = true
        panel.contentView = NSHostingView(rootView: content)
        panel.title = "Game Buddy"  // 靠标题被 mac_window.py 找到

        // 默认停在右下角，离屏幕边留一点缝
        if let screen = NSScreen.main {
            let frame = screen.visibleFrame
            panel.setFrameOrigin(NSPoint(x: frame.maxX - 345 - 24, y: frame.minY + 24))
        }

        return panel
}

// MARK: - 入口

let baseDir: URL = {
    if CommandLine.arguments.count > 1 {
        return URL(fileURLWithPath: CommandLine.arguments[1]).standardizedFileURL
    }
    // 可执行文件放在 <项目>/macos-overlay/ 下，项目目录是它的上一级
    return URL(fileURLWithPath: CommandLine.arguments[0])
        .resolvingSymlinksInPath()
        .deletingLastPathComponent()
        .deletingLastPathComponent()
}()

/// 入口。
///
/// 构建命令带 `-parse-as-library`，所以不能写顶层语句，得包成 @main。
///
/// ⚠ 这几个引用一律用 `static let`，不要改成 `main()` 里的局部变量：
/// Swift 的 ARC 不保证局部变量活到作用域结束，最后一次使用之后就可能被释放。
/// panel 一旦被回收，窗口跟着消失；delegate 那种 weak 引用更是直接失联
/// —— 症状都是「进程活着、退出码 0、桌面上什么都没有」，极难查。
/// static 存储活到进程结束，从根上避掉。
@main
@MainActor
struct GameBuddyMacApp {
    static let app = NSApplication.shared
    static let bridge = Bridge(baseDir: baseDir)
    static let config = ConfigStore(baseDir: baseDir)
    static let palette = Palette(projectURL: baseDir)
    static var panel: OverlayPanel?

    static func main() {
        app.setActivationPolicy(.accessory)  // 不进 Dock、不抢菜单栏，就是个挂件

        // 主题：从 config.json 的 overlay_theme 取，跟 Tk 前端同一套定义。
        // 取不到就用内置的粉白，不影响启动。
        palette.loadChoices()
        palette.apply(config.overlayTheme)

        let created = makePanel(bridge: bridge, config: config, palette: palette)
        panel = created
        created.orderFrontRegardless()
        bridge.startWatching()

        // ⚠ 必须在 runloop 起来之后再 order 一次（2026-08-11 实测）。
        // 直接跑二进制时，上面那次 orderFrontRegardless 就够了；
        // 但经 `open -n` 由 LaunchServices 拉起时，LSUIElement 应用不会被激活，
        // app.run() 开始处理事件时会把这次 order 吃掉 —— 症状是同一个二进制
        // 手动跑有窗口、双击 .app 或 open 就没有。放到下一个 runloop 回合就稳。
        DispatchQueue.main.async {
            created.orderFrontRegardless()
            created.makeKeyAndOrderFront(nil)
        }

        app.run()
    }
}
