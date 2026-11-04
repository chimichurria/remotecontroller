import SwiftUI

struct ContentView: View {
    @EnvironmentObject var hub: Hub

    var body: some View {
        VStack(spacing: 0) {
            StatusBar()
            TabView {
                TrackpadView().tabItem { Label("Mouse", systemImage: "rectangle.and.hand.point.up.left") }
                SlidesView().tabItem { Label("Slides", systemImage: "play.rectangle") }
                KeysView().tabItem { Label("Teclas", systemImage: "keyboard") }
                ClaudeView().tabItem { Label("Claude", systemImage: "sparkles") }
                PhoneView().tabItem { Label("iPhone", systemImage: "iphone") }
                SettingsView().tabItem { Label("Ajustes", systemImage: "gearshape") }
            }
        }
    }
}

struct StatusBar: View {
    @EnvironmentObject var hub: Hub

    var body: some View {
        HStack(spacing: 8) {
            Circle().fill(color).frame(width: 10, height: 10)
            Text(text).font(.footnote)
            Spacer()
        }
        .padding(.horizontal).padding(.vertical, 6)
        .background(.bar)
    }

    private var color: Color {
        switch hub.status {
        case .connected: return .green
        case .connecting: return .orange
        default: return .red
        }
    }

    private var text: String {
        switch hub.status {
        case .disconnected: return "Sin conexión"
        case .connecting: return "Conectando…"
        case .connected(let p): return "Conectado a \(p == "darwin" ? "Mac" : p == "win32" ? "Windows" : p)"
        case .failed(let why): return why
        }
    }
}

struct SlidesView: View {
    @EnvironmentObject var hub: Hub

    var body: some View {
        VStack(spacing: 14) {
            big("Siguiente", "chevron.right.circle.fill", .blue) { hub.send(["t": "slides", "action": "next"]) }
            big("Anterior", "chevron.left.circle.fill", .gray) { hub.send(["t": "slides", "action": "prev"]) }
            HStack(spacing: 10) {
                small("Iniciar", "play.fill") { hub.send(["t": "slides", "action": "start"]) }
                small("Pantalla negra", "moon.fill") { hub.send(["t": "slides", "action": "black"]) }
                small("Salir", "xmark") { hub.send(["t": "slides", "action": "end"]) }
            }
        }
        .padding()
    }

    private func big(_ t: String, _ i: String, _ c: Color, _ a: @escaping () -> Void) -> some View {
        Button(action: a) { Label(t, systemImage: i).font(.title2.bold()).frame(maxWidth: .infinity, maxHeight: .infinity) }
            .buttonStyle(.borderedProminent).tint(c)
    }

    private func small(_ t: String, _ i: String, _ a: @escaping () -> Void) -> some View {
        Button(action: a) { Label(t, systemImage: i).font(.footnote).frame(maxWidth: .infinity) }
            .buttonStyle(.bordered).controlSize(.large)
    }
}

struct KeysView: View {
    @EnvironmentObject var hub: Hub
    @State private var text = ""

    private let combos: [(String, [String])] = [
        ("Esc", ["esc"]), ("Enter", ["enter"]), ("Tab", ["tab"]), ("⌫", ["backspace"]),
        ("Copiar", ["mod", "c"]), ("Pegar", ["mod", "v"]), ("Deshacer", ["mod", "z"]), ("Guardar", ["mod", "s"]),
        // "appswitch" y "search" los traduce el receptor según Mac/Windows.
        ("Cambiar app", ["appswitch"]), ("Buscar", ["search"]), ("↑", ["up"]), ("↓", ["down"]),
    ]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                Text("Escribir en la compu").font(.headline)
                TextField("Tocá el micrófono del teclado para dictar", text: $text, axis: .vertical)
                    .textFieldStyle(.roundedBorder).lineLimit(1...4)
                HStack {
                    Button("Enviar") { sendText(enter: false) }.buttonStyle(.bordered)
                    Button("Enviar + Enter") { sendText(enter: true) }.buttonStyle(.borderedProminent)
                }

                Text("Atajos").font(.headline)
                LazyVGrid(columns: Array(repeating: GridItem(.flexible()), count: 4), spacing: 8) {
                    ForEach(combos, id: \.0) { c in
                        Button(c.0) { hub.send(["t": "key.combo", "keys": c.1]) }
                            .buttonStyle(.bordered).font(.footnote).lineLimit(1).minimumScaleFactor(0.7)
                    }
                }

                Text("Multimedia").font(.headline)
                HStack {
                    media("backward.fill", "prev"); media("playpause.fill", "play_pause"); media("forward.fill", "next")
                    media("speaker.minus.fill", "vol_down"); media("speaker.plus.fill", "vol_up"); media("speaker.slash.fill", "mute")
                }
                HStack {
                    media("sun.min.fill", "bright_down"); media("sun.max.fill", "bright_up")
                }
            }
            .padding()
        }
    }

    private func sendText(enter: Bool) {
        guard !text.isEmpty else { return }
        hub.send(["t": "text.type", "text": text, "enter": enter])
        text = ""
    }

    private func media(_ icon: String, _ action: String) -> some View {
        Button { hub.send(["t": "media", "action": action]) } label: {
            Image(systemName: icon).frame(maxWidth: .infinity)
        }.buttonStyle(.bordered).controlSize(.large)
    }
}

struct ClaudeView: View {
    @EnvironmentObject var hub: Hub
    @State private var prompt = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack {
                    ForEach(hub.presets, id: \.self) { p in
                        Button(p) { hub.runPreset(p) }.buttonStyle(.bordered).disabled(hub.claudeBusy)
                    }
                }
            }
            ScrollView {
                Text(hub.claudeOutput.isEmpty ? "La respuesta de Claude Code aparece acá." : hub.claudeOutput)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .foregroundStyle(hub.claudeOutput.isEmpty ? .secondary : .primary)
                    .textSelection(.enabled)
            }
            .padding().background(.gray.opacity(0.12), in: RoundedRectangle(cornerRadius: 12))
            TextField("Pedile algo a Claude Code (dictá con el micrófono)", text: $prompt, axis: .vertical)
                .textFieldStyle(.roundedBorder).lineLimit(1...4)
            HStack {
                Button { send(false) } label: { Label("Enviar", systemImage: "paperplane.fill") }
                    .buttonStyle(.borderedProminent).disabled(hub.claudeBusy || prompt.isEmpty)
                Button("Continuar") { send(true) }.buttonStyle(.bordered).disabled(hub.claudeBusy || prompt.isEmpty)
                if hub.claudeBusy {
                    Button("Cancelar", role: .destructive) { hub.send(["t": "claude.cancel"]) }.buttonStyle(.bordered)
                    ProgressView()
                }
            }
        }
        .padding()
    }

    private func send(_ cont: Bool) {
        hub.runClaude(prompt, continueLast: cont)
        prompt = ""
    }
}

struct PhoneView: View {
    @EnvironmentObject var hub: Hub
    @ObservedObject private var actions = PhoneActions.shared

    var body: some View {
        VStack(spacing: 12) {
            ZStack {
                CameraPreview(session: actions.camera.session)
                    .clipShape(RoundedRectangle(cornerRadius: 16))
                    .background(.black, in: RoundedRectangle(cornerRadius: 16))
                VStack {
                    Spacer()
                    Button { actions.camera.capture() } label: {
                        Circle().strokeBorder(.white, lineWidth: 4).frame(width: 64, height: 64)
                            .overlay(Circle().fill(.white).padding(6))
                    }.padding(.bottom, 12)
                }
            }
            HStack {
                Button { actions.toggleTorch() } label: {
                    Label(actions.torchOn ? "Apagar linterna" : "Linterna", systemImage: "flashlight.on.fill")
                }.buttonStyle(.bordered)
            }
            if !hub.shortcuts.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack {
                        ForEach(hub.shortcuts, id: \.self) { s in
                            Button(s) { actions.runShortcut(s) }.buttonStyle(.bordered)
                        }
                    }
                }
            }
            Text("Desde el Watch o la compu podés disparar la foto, la linterna y tus Atajos. La app tiene que estar abierta.")
                .font(.footnote).foregroundStyle(.secondary).multilineTextAlignment(.center)
        }
        .padding()
        .onAppear { actions.camera.start() }
        .onDisappear { actions.camera.stop() }
    }
}

struct SettingsView: View {
    @EnvironmentObject var hub: Hub

    var body: some View {
        Form {
            Section("Compu (Mac o Windows)") {
                ForEach(hub.discovered) { e in
                    Button {
                        hub.host = e.host; hub.port = e.port
                    } label: {
                        HStack { Image(systemName: "desktopcomputer"); Text(e.name); Spacer(); Text(e.host).foregroundStyle(.secondary) }
                    }
                }
                if hub.discovered.isEmpty { Text("Buscando en la red local…").foregroundStyle(.secondary) }
                TextField("IP", text: $hub.host).keyboardType(.numbersAndPunctuation).autocorrectionDisabled().textInputAutocapitalization(.never)
                TextField("Puerto", value: $hub.port, format: .number.grouping(.never)).keyboardType(.numberPad)
                SecureField("Token (lo muestra el receptor)", text: $hub.token)
                if hub.status.isConnected {
                    Button("Desconectar", role: .destructive) { hub.disconnect() }
                } else {
                    Button("Conectar") { hub.connect() }.disabled(!hub.hasSaved)
                }
            }
            Section("Atajos de iOS (separados por coma)") {
                TextField("Ej: Modo cine, Llamar a casa", text: $hub.shortcutNames)
            }
            Section("Presets de Claude (nombres de config.toml)") {
                TextField("tests, status, review", text: $hub.presetNames).textInputAutocapitalization(.never)
            }
            Section {
                Text("Tip: escaneá el QR que muestra el receptor con la cámara del iPhone y queda todo configurado.")
                    .font(.footnote).foregroundStyle(.secondary)
            }
        }
    }
}
