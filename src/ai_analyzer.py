"""Claude を使った売買判断（CLI / API 切り替え対応・マルチ通貨）"""
import json
import logging
import subprocess
from . import config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
あなたは暗号資産のデイトレード専門のトレーディングアナリストです。
テクニカル指標データを受け取り、売買判断を行います。

判断基準:
- RSI: 30以下で売られすぎ（買いシグナル）、70以上で買われすぎ（売りシグナル）
- MACD: ヒストグラムが正転で買い、負転で売り
- ボリンジャーバンド: 下限タッチで反発買い、上限タッチで反落売り
- 複数指標が一致する方向に強いシグナル
- 他通貨の動向も参考にすること（BTC下落時はアルトも連動しやすい）

必ず以下のJSON形式のみで回答してください（他のテキストは不要）:
{
  "action": "BUY" or "SELL" or "HOLD",
  "confidence": 0.0〜1.0,
  "reason": "判断理由を1-2文で"
}
"""


def _build_user_message(symbol: str, summary: dict, position_size: float,
                        other_summaries: dict | None = None) -> str:
    msg = f"""\
【分析対象: {symbol}/JPY】
- 現在価格: ¥{summary['price']:,.0f}
- RSI(14): {summary['rsi']}
- MACD: {summary['macd']} (シグナル: {summary['macd_signal']}, ヒストグラム: {summary['macd_histogram']})
- ボリンジャーバンド: 上限 ¥{summary['bb_upper']:,.0f} / 中央 ¥{summary['bb_middle']:,.0f} / 下限 ¥{summary['bb_lower']:,.0f}
- BB位置(0=下限, 1=上限): {summary['bb_position']}
- 1時間変動率: {summary['price_change_1h']}%
- 4時間変動率: {summary['price_change_4h']}%
- 現在保有量: {position_size} {symbol}"""

    if other_summaries:
        msg += "\n\n【参考: 他通貨の状況】"
        for sym, s in other_summaries.items():
            msg += f"\n- {sym}/JPY: ¥{s['price']:,.0f} RSI={s['rsi']} 1h変動={s['price_change_1h']}%"

    msg += "\n\n売買判断をJSON形式で回答してください。"
    return msg


def _parse_response(text: str) -> dict:
    text = text.strip()
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        text = text[start:end]
    return json.loads(text)


def _analyze_with_cli(symbol: str, summary: dict, position_size: float,
                      other_summaries: dict | None = None) -> dict:
    user_msg = _build_user_message(symbol, summary, position_size, other_summaries)
    prompt = f"{SYSTEM_PROMPT}\n\n{user_msg}"

    logger.info("[%s] Claude Code CLI で分析中...", symbol)
    env = {k: v for k, v in __import__("os").environ.items() if k != "ANTHROPIC_API_KEY"}
    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True,
        timeout=120,
        encoding="utf-8",
        env=env,
    )

    output = result.stdout.strip()
    if not output:
        err = result.stderr.strip() if result.stderr else "出力なし"
        raise RuntimeError(f"Claude CLI 応答なし (code={result.returncode}): {err}")

    return _parse_response(output)


def _analyze_with_api(symbol: str, summary: dict, position_size: float,
                      other_summaries: dict | None = None) -> dict:
    import anthropic
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    user_msg = _build_user_message(symbol, summary, position_size, other_summaries)

    resp = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=256,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )
    return _parse_response(resp.content[0].text)


def _validate_decision(data: dict) -> dict:
    """AI応答を検証し、安全なデフォルト値で補完する。"""
    action = data.get("action", "HOLD")
    if action not in ("BUY", "SELL", "HOLD"):
        logger.warning("AI応答の action が不正: %s → HOLD に変更", action)
        action = "HOLD"

    confidence = data.get("confidence", 0.0)
    try:
        confidence = float(confidence)
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.0

    reason = data.get("reason", "理由なし")
    return {"action": action, "confidence": confidence, "reason": str(reason)}


def analyze(symbol: str, summary: dict, position_size: float,
            other_summaries: dict | None = None) -> dict:
    try:
        if config.ANALYZER_MODE == "api":
            raw = _analyze_with_api(symbol, summary, position_size, other_summaries)
        else:
            raw = _analyze_with_cli(symbol, summary, position_size, other_summaries)
        return _validate_decision(raw)
    except Exception as e:
        logger.error("[%s] AI分析エラー: %s → HOLD返却", symbol, e)
        return {"action": "HOLD", "confidence": 0.0, "reason": f"分析エラー: {e}"}
