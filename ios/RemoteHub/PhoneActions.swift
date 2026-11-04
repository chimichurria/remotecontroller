import AVFoundation
import Photos
import SwiftUI
import UIKit

/// Cosas que el iPhone hace cuando se las piden el Watch o la compu.
/// OJO: iOS solo permite cámara, linterna y abrir Atajos con la app en primer plano.
@MainActor
final class PhoneActions: ObservableObject {
    static let shared = PhoneActions()
    let camera = CameraController()
    @Published var torchOn = false

    func run(_ m: [String: Any]) {
        switch m["action"] as? String {
        case "camera.shutter": camera.captureOnDemand()
        case "torch": toggleTorch()
        case "shortcut.run":
            if let name = m["name"] as? String { runShortcut(name) }
        default: break
        }
    }

    func toggleTorch() {
        guard let dev = AVCaptureDevice.default(for: .video), dev.hasTorch else { return }
        do {
            try dev.lockForConfiguration()
            dev.torchMode = dev.torchMode == .on ? .off : .on
            torchOn = dev.torchMode == .on
            dev.unlockForConfiguration()
        } catch {}
    }

    /// Ejecuta un Atajo y vuelve a RemoteHub (x-success) para no perder la conexión.
    func runShortcut(_ name: String) {
        var c = URLComponents(string: "shortcuts://x-callback-url/run-shortcut")!
        c.queryItems = [
            URLQueryItem(name: "name", value: name),
            URLQueryItem(name: "x-success", value: "remotehub://back"),
            URLQueryItem(name: "x-cancel", value: "remotehub://back"),
            URLQueryItem(name: "x-error", value: "remotehub://back"),
        ]
        if let u = c.url { UIApplication.shared.open(u) }
    }
}

final class CameraController: NSObject, ObservableObject, AVCapturePhotoCaptureDelegate {
    let session = AVCaptureSession()
    private let output = AVCapturePhotoOutput()
    private var configured = false
    private let queue = DispatchQueue(label: "remotehub.camera")

    func start() {
        AVCaptureDevice.requestAccess(for: .video) { ok in
            guard ok else { return }
            self.queue.async {
                self.configureIfNeeded()
                if !self.session.isRunning { self.session.startRunning() }
            }
        }
    }

    func stop() {
        queue.async { if self.session.isRunning { self.session.stopRunning() } }
    }

    private func configureIfNeeded() {
        guard !configured else { return }
        session.beginConfiguration()
        session.sessionPreset = .photo
        if let dev = AVCaptureDevice.default(.builtInWideAngleCamera, for: .video, position: .back),
           let input = try? AVCaptureDeviceInput(device: dev), session.canAddInput(input) {
            session.addInput(input)
        }
        if session.canAddOutput(output) { session.addOutput(output) }
        session.commitConfiguration()
        configured = true
    }

    func capture() {
        output.capturePhoto(with: AVCapturePhotoSettings(), delegate: self)
    }

    /// Si la cámara no está corriendo, la prende, espera a que estabilice y dispara.
    func captureOnDemand() {
        if session.isRunning { capture(); return }
        start()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.9) { self.capture() }
    }

    func photoOutput(_ output: AVCapturePhotoOutput, didFinishProcessingPhoto photo: AVCapturePhoto, error: Error?) {
        guard error == nil, let data = photo.fileDataRepresentation() else { return }
        PHPhotoLibrary.requestAuthorization(for: .addOnly) { status in
            guard status == .authorized || status == .limited else { return }
            PHPhotoLibrary.shared().performChanges({
                PHAssetCreationRequest.forAsset().addResource(with: .photo, data: data, options: nil)
            }, completionHandler: { ok, _ in
                if ok { Task { @MainActor in WatchBridge.shared.ack("camera.shutter") } }
            })
        }
    }
}

struct CameraPreview: UIViewRepresentable {
    let session: AVCaptureSession

    final class PreviewView: UIView {
        override class var layerClass: AnyClass { AVCaptureVideoPreviewLayer.self }
        var layer_: AVCaptureVideoPreviewLayer { layer as! AVCaptureVideoPreviewLayer }
    }

    func makeUIView(context: Context) -> PreviewView {
        let v = PreviewView()
        v.layer_.session = session
        v.layer_.videoGravity = .resizeAspectFill
        return v
    }

    func updateUIView(_ uiView: PreviewView, context: Context) {}
}
