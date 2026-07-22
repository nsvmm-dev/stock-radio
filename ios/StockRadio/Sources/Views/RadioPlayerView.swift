import SwiftUI

struct RadioPlayerView: View {
    let radio: RadioMeta
    @StateObject private var vm: RadioPlayerViewModel
    @ObservedObject private var player = AudioPlayerService.shared

    init(radio: RadioMeta) {
        self.radio = radio
        _vm = StateObject(wrappedValue: RadioPlayerViewModel(radio: radio))
    }

    var body: some View {
        VStack(spacing: 32) {
            Spacer()

            // アートワーク
            Image(systemName: "waveform.circle.fill")
                .font(.system(size: 120))
                .foregroundStyle(.blue.gradient)

            // タイトル
            VStack(spacing: 4) {
                Text("株価ラジオ")
                    .font(.title2.bold())
                Text(radio.radioDate)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            // シークバー
            VStack(spacing: 8) {
                Slider(
                    value: $player.currentTime,
                    in: 0...max(player.duration, 1),
                    onEditingChanged: { editing in
                        if !editing { player.seek(to: player.currentTime) }
                    }
                )
                .tint(.blue)

                HStack {
                    Text(formatTime(player.currentTime))
                    Spacer()
                    Text(formatTime(player.duration))
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }
            .padding(.horizontal)

            // 再生コントロール
            HStack(spacing: 40) {
                Button { player.skip(seconds: -15) } label: {
                    Image(systemName: "gobackward.15")
                        .font(.title)
                }

                Button {
                    if player.isPlaying { player.pause() } else { player.resume() }
                } label: {
                    Image(systemName: player.isPlaying ? "pause.circle.fill" : "play.circle.fill")
                        .font(.system(size: 64))
                }
                .disabled(vm.isLoading)

                Button { player.skip(seconds: 30) } label: {
                    Image(systemName: "goforward.30")
                        .font(.title)
                }
            }
            .foregroundStyle(.primary)

            // 再生速度
            PlaybackRatePicker(rate: player.playbackRate) { rate in
                player.setPlaybackRate(rate)
            }

            Spacer()
        }
        .navigationTitle("ラジオを聴く")
        .navigationBarTitleDisplayMode(.inline)
        .overlay {
            if vm.isLoading {
                ProgressView("音声を取得中...")
                    .padding()
                    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12))
            }
        }
        .alert("エラー", isPresented: Binding(
            get: { vm.errorMessage != nil },
            set: { if !$0 { vm.errorMessage = nil } }
        )) {
            Button("OK") { vm.errorMessage = nil }
        } message: {
            Text(vm.errorMessage ?? "")
        }
        .task {
            await vm.fetchAndPlay()
        }
    }

    private func formatTime(_ seconds: Double) -> String {
        guard seconds.isFinite, seconds >= 0 else { return "0:00" }
        let m = Int(seconds) / 60
        let s = Int(seconds) % 60
        return String(format: "%d:%02d", m, s)
    }
}

// ── 再生速度ピッカー ────────────────────────────────────────────────

struct PlaybackRatePicker: View {
    let rate: Float
    let onChange: (Float) -> Void
    private let rates: [Float] = [0.75, 1.0, 1.25, 1.5, 2.0]

    var body: some View {
        HStack(spacing: 0) {
            ForEach(rates, id: \.self) { r in
                Button {
                    onChange(r)
                } label: {
                    Text(r == 1.0 ? "標準" : "\(r, specifier: "%.2g")x")
                        .font(.caption.bold())
                        .padding(.horizontal, 12)
                        .padding(.vertical, 6)
                        .background(rate == r ? Color.blue : Color.clear)
                        .foregroundStyle(rate == r ? .white : .primary)
                }
            }
        }
        .background(.quaternary, in: Capsule())
        .overlay(Capsule().stroke(.separator))
    }
}

// ── ViewModel ────────────────────────────────────────────────────

@MainActor
final class RadioPlayerViewModel: ObservableObject {
    let radio: RadioMeta
    @Published var isLoading = false
    @Published var errorMessage: String?

    init(radio: RadioMeta) {
        self.radio = radio
    }

    func fetchAndPlay() async {
        // 既に同じラジオが再生中なら何もしない
        if AudioPlayerService.shared.currentRadio?.id == radio.id { return }

        isLoading = true
        defer { isLoading = false }

        do {
            let detail = try await APIService.shared.getRadio(
                userId: radio.userId, date: radio.radioDate
            )
            guard let urlString = detail.audioUrl, let url = URL(string: urlString) else {
                throw APIError.noData
            }
            AudioPlayerService.shared.play(radio: radio, audioURL: url)
        } catch {
            errorMessage = "音声の取得に失敗しました: \(error.localizedDescription)"
        }
    }
}
