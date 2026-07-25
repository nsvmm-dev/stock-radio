import os
import logging
from datetime import datetime
from typing import Protocol

logger = logging.getLogger()

SCRIPT_SYSTEM_PROMPT = """あなたはプロの株価情報ラジオパーソナリティです。
以下のルールで台本を作成してください:
- 自然な話し言葉（です・ます調）
- 数字は読み上げやすい表現（例: 3万8000円、プラス1.5パーセント）
- 上昇・下落を明確に、かつポジティブに伝える
- 合計 900〜1500文字（約3〜5分の放送）
- 台本テキストのみ出力（説明・見出しは不要）"""

SCRIPT_PROMPT_TEMPLATE = """【放送日】{date_str}

【台本構成】
1. 冒頭あいさつ（15秒）
2. 米国市場の動向（30秒）
3. 日本市場の概況（30秒）
4. ウォッチリスト銘柄（銘柄ごと約20秒）
5. 注目ニュース（30秒）
6. 締めのあいさつ（10秒）

【市場データ】
{market_summary}

【ウォッチリスト銘柄】
{watchlist_summary}

【最新ニュース（上位8件）】
{news_summary}

台本を作成してください。"""

SCRIPT_SYSTEM_PROMPT_EN = """You are a professional stock market radio host.
Follow these rules when writing the script:
- Natural, conversational spoken English
- Read numbers in an easy-to-follow way (e.g., "38,000 yen", "up 1.5 percent")
- Clearly and positively convey gains and losses
- Total length: 700-1100 words (about 3-5 minutes of broadcast)
- Output only the script text (no explanations or headings)"""

SCRIPT_PROMPT_TEMPLATE_EN = """[Broadcast date] {date_str}

[Script structure]
1. Opening greeting (15 sec)
2. US market overview (30 sec)
3. Japan market overview (30 sec)
4. Watchlist stocks (about 20 sec each)
5. Notable news (30 sec)
6. Closing greeting (10 sec)

[Market data]
{market_summary}

[Watchlist stocks]
{watchlist_summary}

[Latest news (top 8)]
{news_summary}

Please write the script."""


class _LLMBackend(Protocol):
    def generate(self, prompt: str, system_prompt: str) -> str: ...


class ScriptGenerator:
    def __init__(self):
        provider = os.environ.get("LLM_PROVIDER", "groq")
        self._backend = _build_backend(provider)

    def generate(self, radio_date: str, market_data: dict,
                 watchlist_data: list, news: list, language: str = "ja") -> str:
        system_prompt = SCRIPT_SYSTEM_PROMPT_EN if language == "en" else SCRIPT_SYSTEM_PROMPT
        prompt = _build_prompt(radio_date, market_data, watchlist_data, news, language)
        try:
            script = self._backend.generate(prompt, system_prompt)
            logger.info(f"台本生成完了: {len(script)} 文字")
            return script
        except Exception as e:
            logger.error(f"台本生成エラー: {e}", exc_info=True)
            return _fallback_script(radio_date, market_data, watchlist_data, language)


# ── バックエンド実装 ────────────────────────────────────────────────

class _GroqBackend:
    """Groq (Llama) - free tier, fast, commercial OK"""

    def __init__(self):
        from groq import Groq
        self._client = Groq(api_key=os.environ["GROQ_API_KEY"])

    def generate(self, prompt: str, system_prompt: str) -> str:
        resp = self._client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            max_tokens=2048,
            temperature=0.7,
        )
        return resp.choices[0].message.content.strip()


class _GeminiBackend:
    """Google Gemini - requires billing enabled"""

    def __init__(self):
        import google.generativeai as genai
        self._genai = genai
        genai.configure(api_key=os.environ["GEMINI_API_KEY"])

    def generate(self, prompt: str, system_prompt: str) -> str:
        model = self._genai.GenerativeModel(
            "gemini-2.0-flash",
            system_instruction=system_prompt,
        )
        resp = model.generate_content(
            prompt,
            generation_config={"temperature": 0.7, "max_output_tokens": 2048},
        )
        return resp.text.strip()


class _ClaudeBackend:
    """Anthropic Claude Sonnet - 本番向け高品質"""

    def __init__(self):
        import anthropic
        self._client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def generate(self, prompt: str, system_prompt: str) -> str:
        msg = self._client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()


class _OpenAIBackend:
    """OpenAI GPT-4o - 本番向け高品質"""

    def __init__(self):
        from openai import OpenAI
        self._client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    def generate(self, prompt: str, system_prompt: str) -> str:
        resp = self._client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            max_tokens=2048,
            temperature=0.7,
        )
        return resp.choices[0].message.content.strip()


def _build_backend(provider: str) -> _LLMBackend:
    if provider == "claude":
        return _ClaudeBackend()
    if provider == "openai":
        return _OpenAIBackend()
    if provider == "gemini":
        return _GeminiBackend()
    return _GroqBackend()  # default: groq


# ── プロンプト構築 ──────────────────────────────────────────────────

def _build_prompt(radio_date: str, market_data: dict,
                  watchlist_data: list, news: list, language: str = "ja") -> str:
    if language == "en":
        date_str = datetime.strptime(radio_date, "%Y-%m-%d").strftime("%B %d, %Y")
        return SCRIPT_PROMPT_TEMPLATE_EN.format(
            date_str=date_str,
            market_summary=_fmt_market_en(market_data),
            watchlist_summary=_fmt_watchlist_en(watchlist_data),
            news_summary=_fmt_news(news),
        )

    date_str = datetime.strptime(radio_date, "%Y-%m-%d").strftime("%Y年%m月%d日")
    return SCRIPT_PROMPT_TEMPLATE.format(
        date_str=date_str,
        market_summary=_fmt_market(market_data),
        watchlist_summary=_fmt_watchlist(watchlist_data),
        news_summary=_fmt_news(news),
    )


def _fmt_market(data: dict) -> str:
    NAMES = {
        "nikkei": "日経平均",
        "topix": "TOPIX",
        "dow": "ダウ平均(DIA ETF・参考値)",
        "nasdaq": "NASDAQ100(QQQ ETF・参考値)",
        "sp500": "S&P500(SPY ETF・参考値)",
    }
    lines = []
    for key, name in NAMES.items():
        d = data.get(key)
        if d:
            sign = "+" if d.get("change_pct", 0) >= 0 else ""
            lines.append(f"{name}: {d.get('close', 'N/A')} ({sign}{d.get('change_pct', 0):.2f}%)")
        else:
            lines.append(f"{name}: データなし")
    return "\n".join(lines)


def _fmt_watchlist(stocks: list) -> str:
    if not stocks:
        return "ウォッチリストに銘柄が登録されていません"
    lines = []
    for s in stocks:
        pct = s.get("change_pct", 0)
        sign = "+" if pct >= 0 else ""
        mkt = "東証" if s.get("market") == "JP" else "米国"
        lines.append(
            f"・{s.get('name', s.get('code'))}（{mkt}）"
            f" 終値{s.get('close', 'N/A')} 前日比{sign}{pct:.2f}%"
        )
    return "\n".join(lines)


def _fmt_news(news: list) -> str:
    if not news:
        return "ニュースなし"
    lines = []
    for i, item in enumerate(news[:8], 1):
        lines.append(f"{i}. 【{item.get('source', '')}】{item.get('title', '')}")
    return "\n".join(lines)


def _fmt_market_en(data: dict) -> str:
    NAMES = {
        "nikkei": "Nikkei 225",
        "topix": "TOPIX",
        "dow": "Dow Jones (DIA ETF proxy)",
        "nasdaq": "NASDAQ 100 (QQQ ETF proxy)",
        "sp500": "S&P 500 (SPY ETF proxy)",
    }
    lines = []
    for key, name in NAMES.items():
        d = data.get(key)
        if d:
            sign = "+" if d.get("change_pct", 0) >= 0 else ""
            lines.append(f"{name}: {d.get('close', 'N/A')} ({sign}{d.get('change_pct', 0):.2f}%)")
        else:
            lines.append(f"{name}: no data")
    return "\n".join(lines)


def _fmt_watchlist_en(stocks: list) -> str:
    if not stocks:
        return "No stocks in the watchlist"
    lines = []
    for s in stocks:
        pct = s.get("change_pct", 0)
        sign = "+" if pct >= 0 else ""
        mkt = "Tokyo" if s.get("market") == "JP" else "US"
        lines.append(
            f"- {s.get('name', s.get('code'))} ({mkt})"
            f" close {s.get('close', 'N/A')}, change {sign}{pct:.2f}%"
        )
    return "\n".join(lines)


def _fallback_script(radio_date: str, market_data: dict, watchlist_data: list, language: str = "ja") -> str:
    """LLM 失敗時の最低限のフォールバック台本"""
    if language == "en":
        return _fallback_script_en(radio_date, market_data, watchlist_data)

    date_str = datetime.strptime(radio_date, "%Y-%m-%d").strftime("%Y年%m月%d日")
    lines = [f"おはようございます。{date_str}の株価ラジオをお届けします。\n"]

    nikkei = market_data.get("nikkei")
    if nikkei:
        direction = "上昇" if nikkei.get("change_pct", 0) >= 0 else "下落"
        lines.append(f"昨日の日経平均は{nikkei.get('close', 'N/A')}円、前日比{direction}でした。\n")

    for s in watchlist_data:
        pct = s.get("change_pct", 0)
        direction = "上昇" if pct >= 0 else "下落"
        lines.append(f"{s.get('name')}は終値{s.get('close', 'N/A')}円、前日比{abs(pct):.1f}%の{direction}でした。")

    lines.append("\n以上が本日の株価ラジオでした。良い一日をお過ごしください。")
    return "\n".join(lines)


def _fallback_script_en(radio_date: str, market_data: dict, watchlist_data: list) -> str:
    date_str = datetime.strptime(radio_date, "%Y-%m-%d").strftime("%B %d, %Y")
    lines = [f"Good morning. Here is your stock radio for {date_str}.\n"]

    nikkei = market_data.get("nikkei")
    if nikkei:
        direction = "up" if nikkei.get("change_pct", 0) >= 0 else "down"
        lines.append(f"Yesterday, the Nikkei 225 closed at {nikkei.get('close', 'N/A')} yen, {direction} from the previous day.\n")

    for s in watchlist_data:
        pct = s.get("change_pct", 0)
        direction = "up" if pct >= 0 else "down"
        lines.append(f"{s.get('name')} closed at {s.get('close', 'N/A')}, {direction} {abs(pct):.1f}% from the previous day.")

    lines.append("\nThat's all for today's stock radio. Have a great day.")
    return "\n".join(lines)
