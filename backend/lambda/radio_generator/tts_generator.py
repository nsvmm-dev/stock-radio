import os
import io
import logging

import boto3

logger = logging.getLogger()

# ユーザーがマイページで選択できるナレーター音声。
# 日本語は Mizuki(standard, 無料枠) / Kazuha(neural, 高品質・課金発生) の2択。
# 英語は Joanna のみ(選択肢なし)。
RADIO_VOICES = {
    "ja": {
        "mizuki": {"voiceId": "Mizuki", "engine": "standard"},
        "kazuha": {"voiceId": "Kazuha", "engine": "neural"},
    },
    "en": {
        "joanna": {"voiceId": "Joanna", "engine": "standard"},
    },
}

DEFAULT_VOICE = {"ja": "mizuki", "en": "joanna"}

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
    def __init__(self, language: str = "ja", voice: str = None):
        self._polly = boto3.client("polly")
        self._language = language if language in RADIO_VOICES else "ja"
        voices = RADIO_VOICES[self._language]
        voice_key = voice if voice in voices else DEFAULT_VOICE[self._language]
        selected = voices[voice_key]

        # neural音声はTTS_ENGINE=neuralの本番環境でのみ使用する(dev/testでの誤課金を防ぐため、
        # ユーザーがneural音声を選択していてもTTS_ENGINE=standardの環境ではデフォルト音声にフォールバック)
        if selected["engine"] == "neural" and os.environ.get("TTS_ENGINE", "standard") != "neural":
            voice_key = DEFAULT_VOICE[self._language]
            selected = voices[voice_key]

        self._voice_id = selected["voiceId"]
        self._engine = selected["engine"]
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
