import os
import io
import logging

import boto3

logger = logging.getLogger()

# プランに応じて自動で切り替わるナレーター音声エンジン。
# free: standard(Mizuki/Joanna) / standard・pro: neural(Kazuha/Joanna, 高品質・課金発生)
VOICE_MAP = {
    "ja": {"standard": "Mizuki", "neural": "Kazuha"},
    "en": {"standard": "Joanna", "neural": "Joanna"},
}

PAID_PLANS = {"standard", "pro"}

LANGUAGE_CODE_MAP = {
    "ja": "ja-JP",
    "en": "en-US",
}

SENTENCE_END_CHARS = {
    "ja": ("。", "！", "？", "\n"),
    "en": (".", "!", "?", "\n"),
}

POLLY_CHAR_LIMIT = 2900  # Polly 1リクエストあたりの文字数上限


class TTSGenerator:
    def __init__(self, language: str = "ja", plan: str = "free"):
        self._polly = boto3.client("polly")
        self._language = language if language in VOICE_MAP else "ja"

        engine = "neural" if plan in PAID_PLANS else "standard"
        # neuralはTTS_ENGINE=neuralの本番環境でのみ使用する(dev/testでの誤課金を防ぐため、
        # 有料プランでもTTS_ENGINE=standardの環境ではstandardにフォールバック)
        if engine == "neural" and os.environ.get("TTS_ENGINE", "standard") != "neural":
            engine = "standard"

        self._engine = engine
        self._voice_id = VOICE_MAP[self._language][engine]
        self._language_code = LANGUAGE_CODE_MAP[self._language]

    def synthesize(self, text: str) -> bytes:
        """テキストをMP3音声に変換"""
        chunks = _split_by_sentence(text, POLLY_CHAR_LIMIT, self._language)
        logger.info(f"Polly 合成: {len(text)} 文字, {len(chunks)} チャンク, voice={self._voice_id}")

        audio_parts = [self._synthesize_chunk(chunk) for chunk in chunks]
        return b"".join(audio_parts)

    def _synthesize_chunk(self, text: str) -> bytes:
        resp = self._polly.synthesize_speech(
            Text=text,
            OutputFormat="mp3",
            VoiceId=self._voice_id,
            Engine=self._engine,
            LanguageCode=self._language_code,
            TextType="text",
        )
        return resp["AudioStream"].read()


def _split_by_sentence(text: str, max_chars: int, language: str = "ja") -> list:
    """文末で分割してPollyのchar制限に収める"""
    if len(text) <= max_chars:
        return [text]

    end_chars = SENTENCE_END_CHARS.get(language, SENTENCE_END_CHARS["ja"])
    sentences: list[str] = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in end_chars and buf:
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
