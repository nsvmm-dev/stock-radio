import os
import io
import logging

import boto3

logger = logging.getLogger()

# テスト: Mizuki (standard) = 無料枠 5M字/月
# 本番:   Kazuha (neural)   = 高品質、課金発生
VOICE_MAP = {
    "standard": "Mizuki",
    "neural": "Kazuha",
}

POLLY_CHAR_LIMIT = 2900  # Polly 1リクエストあたりの文字数上限


class TTSGenerator:
    def __init__(self):
        self._polly = boto3.client("polly")
        engine = os.environ.get("TTS_ENGINE", "standard")
        self._engine = engine
        self._voice_id = VOICE_MAP.get(engine, "Mizuki")

    def synthesize(self, text: str) -> bytes:
        """テキストをMP3音声に変換"""
        chunks = _split_by_sentence(text, POLLY_CHAR_LIMIT)
        logger.info(f"Polly 合成: {len(text)} 文字, {len(chunks)} チャンク, voice={self._voice_id}")

        audio_parts = [self._synthesize_chunk(chunk) for chunk in chunks]
        return b"".join(audio_parts)

    def _synthesize_chunk(self, text: str) -> bytes:
        resp = self._polly.synthesize_speech(
            Text=text,
            OutputFormat="mp3",
            VoiceId=self._voice_id,
            Engine=self._engine,
            LanguageCode="ja-JP",
            TextType="text",
        )
        return resp["AudioStream"].read()


def _split_by_sentence(text: str, max_chars: int) -> list:
    """文末（。！？\n）で分割してPollyのchar制限に収める"""
    if len(text) <= max_chars:
        return [text]

    sentences: list[str] = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in ("。", "！", "？", "\n") and buf:
            sentences.append(buf)
            buf = ""
    if buf:
        sentences.append(buf)

    chunks, current = [], ""
    for sentence in sentences:
        if len(current) + len(sentence) > max_chars:
            if current:
                chunks.append(current)
            current = sentence
        else:
            current += sentence

    if current:
        chunks.append(current)

    return chunks or [text[:max_chars]]
