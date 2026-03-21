"""Claude API を使った売買判断"""
import json
import anthropic
import config


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


def analyze(summary: dict, position_btc: float) -> dict:
    """テクニカルサマリをClaudeに渡して売買判断を得る"""
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)

    user_msg = f"""\
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

    resp = client.messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=256,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_msg}],
    )

    text = resp.content[0].text.strip()
    # JSON部分を抽出
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    return json.loads(text)
