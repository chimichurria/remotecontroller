import Foundation
import Network
import UIKit

struct Endpoint: Identifiable, Hashable {
    var id: String { "\(host):\(port)" }
    let name: String
    let host: String
    let port: Int
}

/// Conexión WebSocket con el receptor (Mac/Windows) + descubrimiento Bonjour.
@MainActor
final class Hub: ObservableObject {
    static let shared = Hub()

    enum Status: Equatable {
        case disconnected, connecting, connected(String), failed(String)
        var isConnected: Bool { if case .connected = self { return true } else { return false } }
    }

    @Published var status: Status = .disconnected
    @Published var discovered: [Endpoint] = []
    @Published var claudeOutput = ""
    @Published var claudeBusy = false

    @Published var host: String { didSet { UserDefaults.standard.set(host, forKey: "host") } }
    @Published var port: Int { didSet { UserDefaults.standard.set(port, forKey: "port") } }
    @Published var token: String { didSet { UserDefaults.standard.set(token, forKey: "token") } }
    /// Nombres de Atajos de iOS, separados por coma (se muestran en el Watch y los puede disparar la Mac).
    @Published var shortcutNames: String { didSet { UserDefaults.standard.set(shortcutNames, forKey: "shortcuts"); WatchBridge.shared.pushConfig() } }
    @Published var presetNames: String { didSet { UserDefaults.standard.set(presetNames, forKey: "presets") } }

    private var task: URLSessionWebSocketTask?
    private let session = URLSession(configuration: .default)
    private var browser: NWBrowser?
    private var wantConnected = false
    private var retry: Task<Void, Never>?

    var hasSaved: Bool { !host.isEmpty && !token.isEmpty }
    var presets: [String] { presetNames.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty } }
    var shortcuts: [String] { shortcutNames.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty } }

    private init() {
        let d = UserDefaults.standard
        host = d.string(forKey: "host") ?? ""
        port = d.object(forKey: "port") as? Int ?? 8765
        token = d.string(forKey: "token") ?? ""
        shortcutNames = d.string(forKey: "shortcuts") ?? ""
        presetNames = d.string(forKey: "presets") ?? "tests, status, review"
    }

    // MARK: Conexión

    func connect() {
        guard hasSaved else { status = .failed("Falta IP o token"); return }
        guard let url = URL(string: "ws://\(host):\(port)/ws") else { status = .failed("IP inválida"); return }
        wantConnected = true
        retry?.cancel()
        task?.cancel(with: .goingAway, reason: nil)
        status = .connecting
        let t = session.webSocketTask(with: url)
        task = t
        t.resume()
        send(["t": "hello", "token": token, "name": UIDevice.current.name, "role": "phone"])
        listen(t)
        WatchBridge.shared.pushConfig()
    }

    func disconnect() {
        wantConnected = false
        retry?.cancel()
        task?.cancel(with: .goingAway, reason: nil)
        task = nil
        status = .disconnected
    }

    func reconnectIfNeeded() {
        if wantConnected, !status.isConnected, status != .connecting { connect() }
    }

    func handle(url: URL) {
        guard url.scheme == "remotehub", let h = url.host else { return }  // remotehub://back (vuelta de Atajos) se ignora
        let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems
        guard let tk = items?.first(where: { $0.name == "token" })?.value else { return }
        host = h
        port = url.port ?? 8765
        token = tk
        connect()
    }

    // MARK: Envío

    func send(_ obj: [String: Any]) {
        guard let task, JSONSerialization.isValidJSONObject(obj),
              let data = try? JSONSerialization.data(withJSONObject: obj),
              let s = String(data: data, encoding: .utf8) else { return }
        task.send(.string(s)) { _ in }
    }

    func runClaude(_ text: String, continueLast: Bool = false) {
        beginClaude()
        send(["t": "claude.run", "text": text, "continue": continueLast])
    }

    func runPreset(_ name: String) {
        beginClaude()
        send(["t": "claude.preset", "name": name])
    }

    func beginClaude() { claudeOutput = ""; claudeBusy = true }

    // MARK: Recepción

    private func listen(_ t: URLSessionWebSocketTask) {
        t.receive { [weak self] result in
            Task { @MainActor in
                guard let self, self.task === t else { return }
                switch result {
                case .failure(let e):
                    self.dropped(e.localizedDescription)
                case .success(let msg):
                    if case .string(let s) = msg { self.handle(json: s) }
                    self.listen(t)
                }
            }
        }
    }

    private func dropped(_ why: String) {
        status = .failed(why)
        guard wantConnected else { return }
        retry?.cancel()
        retry = Task { [weak self] in
            try? await Task.sleep(nanoseconds: 2_000_000_000)
            guard !Task.isCancelled else { return }
            await self?.connect()
        }
    }

    private func handle(json: String) {
        guard let data = json.data(using: .utf8),
              let m = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let t = m["t"] as? String else { return }
        switch t {
        case "ready":
            status = .connected(m["platform"] as? String ?? "?")
        case "error":
            if let code = m["code"] as? String {
                wantConnected = false
                status = .failed(code == "auth" ? "Token inválido" : "Bloqueado por intentos fallidos (esperá 1 min)")
                task?.cancel(with: .goingAway, reason: nil)
            } else if let msg = m["msg"] as? String {
                claudeOutput += "\n⚠︎ \(msg)"
            }
        case "claude.output":
            claudeOutput += m["chunk"] as? String ?? ""
            WatchBridge.shared.forwardClaude(text: claudeOutput, done: false)
        case "claude.done":
            claudeBusy = false
            let text = m["text"] as? String ?? ""
            if !text.isEmpty { claudeOutput = text }
            WatchBridge.shared.forwardClaude(text: claudeOutput, done: true)
        case "phone.cmd":
            PhoneActions.shared.run(m)
        default:
            break
        }
    }

    // MARK: Bonjour

    func startBrowsing() {
        guard browser == nil else { return }
        let b = NWBrowser(for: .bonjourWithTXTRecord(type: "_remotehub._tcp", domain: nil), using: .tcp)
        b.browseResultsChangedHandler = { [weak self] results, _ in
            let eps: [Endpoint] = results.compactMap { r in
                guard case .service(let name, _, _, _) = r.endpoint,
                      case .bonjour(let txt) = r.metadata,
                      let ip = txt["ip"], let port = txt["port"].flatMap({ Int($0) }) else { return nil }
                return Endpoint(name: name, host: ip, port: port)
            }
            Task { @MainActor in self?.discovered = eps }
        }
        b.start(queue: .main)
        browser = b
    }
}
