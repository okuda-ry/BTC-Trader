"""Claude を使った売買判断（CLI / API 切り替え対応）"""
import json
import logging
import subprocess
import config

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
あなたはBTC/JPYのデイトレード専門のトレーディングアナリストです。
テクニカル指標データを受け取り、売買判断を行います。

判断基準:
- RSI: 30以下で売られすぎ（買いシグナル）、70以上で買われすぎ（売りシグナル）
- MACD: ヒストグラムが正転で買い、負転で売り
- ボリンジャーバンド: 下限タッチで反発買い、上限タッチで反落売り
- 複数指標が一致する方向に強いシグナル

必ず以下のJSON形式のみで回答してください（他のテキストは不要）:
{
  "action": "BUY" or "SELL" or "HOLD",
  "confidence": 0.0〜1.0,
  "reason": "判断理由を1-2文で"
}
"""


def _build_user_message(summary: dict, position_btc: float) -> str:
    return f"""\
現在のBTC/JPYテクニカル指標:
- 現在価格: ¥{summary['price']:,.0f}
- RSI(14): {summary['rsi']}
- MACD: {summary['macd']} (シグナル: {summary['macd_signal']}, ヒストグラム: {summary['macd_histogram']})
- ボリンジャーバンド: 上限 ¥{summary['bb_upper']:,.0f} / 中央 ¥{summary['bb_middle']:,.0f} / 下限 ¥{summary['bb_lower']:,.0f}
- BB位置(0=下限, 1=上限): {summary['bb_position']}
- 1時間変動率: {summary['price_change_1h']}%
- 4時間変動率: {summary['price_change_4h']}%
- 現在BTC保有量: {position_btc:.8f} BTC

売買判断をJSON形式で回答してください。"""


def _parse_response(text: str) -> dict:
    """レスポンスからJSONを抽出してパースする"""
    text = text.strip()
    # コードブロックで囲まれている場合
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    # JSON部分だけ抽出（前後に余計なテキストがある場合）
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        text = text[start:end]
    return json.loads(text)


def _analyze_with_cli(summary: dict, position_btc: float) -> dict:
    """Claude Code CLI (claude -p) を使って分析"""
    user_msg = _build_user_message(summary, position_btc)
    prompt = f"{SYSTEM_PROMPT}\n\n{user_msg}"

    logger.info("Claude Code CLI で分析中...")
    # CLI はサブスクの認証を使うので、.env の ANTHROPIC_API_KEY を除外する
    env = {k: v for k, v in __import__("os").environ.items() if k != "ANTHROPIC_API_KEY"}
    result = subprocess.run(
        ["claude", "-p", prompt],
        capture_output=True,
        timeout=120,
        encoding="utf-8",
        env=env,
    )

    logger.info("CLI returncode=%d", result.returncode)
    if result.stdout:
        logger.info("CLI stdout: %s", result.stdout[:500])
    if result.stderr:
        logger.info("CLI stderr: %s", result.stderr[:500])

    output = result.stdout.strip()
    if not output:
        err = result.stderr.strip() if result.stderr else "出力なし"
        raise RuntimeError(f"Claude Code CLI の応答が空です (code={result.returncode}): {err}")

    return _parse_response(output)


def _analyze_with_api(summary: dict, position_btc: float) -> dict:
    """Anthropic API を使って分析"""
    import anthropic

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    user_msg = _build_user_message(summary, position_btc)

    resp = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=256,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    return _parse_response(resp.content[0].text)


def analyze(summary: dict, position_btc: float) -> dict:
    """テクニカルサマリをClaudeに渡して売買判断を得る。
    config.ANALYZER_MODE に応じて CLI / API を切り替え。
    """
    if config.ANALYZER_MODE == "api":
        return _analyze_with_api(summary, position_btc)
    else:
        return _analyze_with_cli(summary, position_btc)
