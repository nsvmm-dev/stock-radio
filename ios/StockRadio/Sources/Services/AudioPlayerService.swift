import AVFoundation
import MediaPlayer
import Combine

@MainActor
final class AudioPlayerService: ObservableObject {
    static let shared = AudioPlayerService()
    private init() { setupRemoteTransportControls() }

    private var player: AVPlayer?
    private var timeObserver: Any?

    @Published var isPlaying = false
    @Published var duration: Double = 0
    @Published var currentTime: Double = 0
    @Published var playbackRate: Float = 1.0
    @Published var currentRadio: RadioMeta?

    func play(radio: RadioMeta, audioURL: URL) {
        stop()
        currentRadio = radio

        configureAudioSession()

        let item = AVPlayerItem(url: audioURL)
        player = AVPlayer(playerItem: item)
        player?.rate = playbackRate

        // 再生時間の監視
        timeObserver = player?.addPeriodicTimeObserver(
            forInterval: CMTime(seconds: 0.5, preferredTimescale: 600),
            queue: .main
        ) { [weak self] time in
            guard let self else { return }
            self.currentTime = time.seconds
            if let dur = self.player?.currentItem?.duration.seconds, dur.isFinite {
                self.duration = dur
            }
        }

        // 再生終了の監視
        NotificationCenter.default.addObserver(
            self,
            selector: #selector(playerDidFinish),
            name: .AVPlayerItemDidPlayToEndTime,
            object: item
        )

        player?.play()
        isPlaying = true
        updateNowPlayingInfo(radio: radio)
    }

    func pause() {
        player?.pause()
        isPlaying = false
    }

    func resume() {
        player?.play()
        isPlaying = true
    }

    func stop() {
        if let observer = timeObserver {
            player?.removeTimeObserver(observer)
            timeObserver = nil
        }
        player?.pause()
        player = nil
        isPlaying = false
        currentTime = 0
        duration = 0
        currentRadio = nil
        MPNowPlayingInfoCenter.default().nowPlayingInfo = nil
    }

    func seek(to seconds: Double) {
        let time = CMTime(seconds: seconds, preferredTimescale: 600)
        player?.seek(to: time)
    }

    func skip(seconds: Double) {
        let newTime = currentTime + seconds
        seek(to: max(0, min(newTime, duration)))
    }

    func setPlaybackRate(_ rate: Float) {
        playbackRate = rate
        if isPlaying { player?.rate = rate }
    }

    // ── ロック画面 / コントロールセンター ───────────────────────────

    private func updateNowPlayingInfo(radio: RadioMeta) {
        var info: [String: Any] = [
            MPMediaItemPropertyTitle: "\(radio.radioDate) 株価ラジオ",
            MPMediaItemPropertyArtist: "Stock Radio",
            MPNowPlayingInfoPropertyPlaybackRate: playbackRate,
            MPNowPlayingInfoPropertyElapsedPlaybackTime: currentTime,
        ]
        if let dur = radio.durationSec {
            info[MPMediaItemPropertyPlaybackDuration] = Double(dur)
        }
        MPNowPlayingInfoCenter.default().nowPlayingInfo = info
    }

    private func setupRemoteTransportControls() {
        let center = MPRemoteCommandCenter.shared()
        center.playCommand.addTarget { [weak self] _ in
            self?.resume(); return .success
        }
        center.pauseCommand.addTarget { [weak self] _ in
            self?.pause(); return .success
        }
        center.skipForwardCommand.preferredIntervals = [30]
        center.skipForwardCommand.addTarget { [weak self] _ in
            self?.skip(seconds: 30); return .success
        }
        center.skipBackwardCommand.preferredIntervals = [15]
        center.skipBackwardCommand.addTarget { [weak self] _ in
            self?.skip(seconds: -15); return .success
        }
    }

    private func configureAudioSession() {
        try? AVAudioSession.sharedInstance().setCategory(.playback, mode: .spokenAudio)
        try? AVAudioSession.sharedInstance().setActive(true)
    }

    @objc private func playerDidFinish() {
        isPlaying = false
        currentTime = duration
    }
}
