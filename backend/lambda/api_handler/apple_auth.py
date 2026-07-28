import base64
import json
import logging
import time
from urllib.error import URLError
from urllib.request import urlopen

import rsa

logger = logging.getLogger()

APPLE_KEYS_URL = "https://appleid.apple.com/auth/keys"
APPLE_ISSUER = "https://appleid.apple.com"
_JWKS_CACHE_TTL_SEC = 3600

# Lambda実行コンテナ内でウォーム起動間キャッシュする(コールドスタート毎に再取得)
_jwks_cache = {"keys": None, "fetched_at": 0.0}


class AppleTokenError(Exception):
    """Sign in with Apple の identityToken 検証エラー"""


def _b64url_decode(data: str) -> bytes:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded)


def _b64url_to_int(data: str) -> int:
    return int.from_bytes(_b64url_decode(data), "big")


def _get_apple_keys() -> list:
    now = time.time()
    if _jwks_cache["keys"] is not None and (now - _jwks_cache["fetched_at"]) < _JWKS_CACHE_TTL_SEC:
        return _jwks_cache["keys"]

    try:
        with urlopen(APPLE_KEYS_URL, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        keys = data.get("keys", [])
        _jwks_cache["keys"] = keys
        _jwks_cache["fetched_at"] = now
        return keys
    except URLError as e:
        if _jwks_cache["keys"] is not None:
            logger.warning(f"Apple公開鍵の再取得に失敗、キャッシュを使用: {e}")
            return _jwks_cache["keys"]
        raise AppleTokenError(f"Apple公開鍵の取得に失敗しました: {e}")


def verify_apple_identity_token(identity_token: str, audience: str) -> dict:
    """
    Sign in with Apple の identityToken(JWT/RS256)を検証し、claims(dict)を返す。
    署名不正・iss/aud不一致・有効期限切れの場合は AppleTokenError を送出する。
    """
    parts = identity_token.split(".")
    if len(parts) != 3:
        raise AppleTokenError("不正なトークン形式です")

    header_b64, payload_b64, signature_b64 = parts
    try:
        header = json.loads(_b64url_decode(header_b64))
        payload = json.loads(_b64url_decode(payload_b64))
        signature = _b64url_decode(signature_b64)
    except (ValueError, json.JSONDecodeError) as e:
        raise AppleTokenError(f"トークンのデコードに失敗しました: {e}")

    kid = header.get("kid")
    keys = _get_apple_keys()
    jwk = next((k for k in keys if k.get("kid") == kid), None)
    if jwk is None:
        raise AppleTokenError("対応するApple公開鍵が見つかりません")

    public_key = rsa.PublicKey(_b64url_to_int(jwk["n"]), _b64url_to_int(jwk["e"]))

    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    try:
        rsa.verify(signing_input, signature, public_key)
    except rsa.pkcs1.VerificationError:
        raise AppleTokenError("署名検証に失敗しました")

    if payload.get("iss") != APPLE_ISSUER:
        raise AppleTokenError("issが不正です")
    if payload.get("aud") != audience:
        raise AppleTokenError("audが不正です")
    if payload.get("exp", 0) < time.time():
        raise AppleTokenError("トークンの有効期限が切れています")
    if "sub" not in payload:
        raise AppleTokenError("subクレームがありません")

    return payload
