"""受语法上下文约束的 because 口语缩略；不把普通 cause 纳入词表。"""

import re

CAUSE_RULE_VERSION = "causal-cause-v1"
# 第一版只确认行首 cause + 代词主语 + 可确认的限定助动词。
# 不接受 cause you pain / cause you to leave / a good cause / the cause you described。
CLAUSE = re.compile(
    r"^[ \t]+(?:"
    r"(?:i|you|we|they|he|she|it)[ \t]+(?:am|is|are|was|were|have|has|had|can|could|will|would|shall|should|must|do|does|did)\b"
    r"|(?:i'm|i've|i'll|i'd|you're|you've|you'll|you'd|we're|we've|we'll|we'd|they're|they've|they'll|they'd|he's|she's|it's)\b"
    r")(?=[ \t]+[a-z])", re.IGNORECASE | re.ASCII)


def is_causal_cause(sentence, start, end):
    """仅确定文本中 because 的缩略用法，不确定实际发音。"""
    text = sentence[start:end].lower().replace("’", "'")
    if text not in {"cause", "'cause"}:
        return False
    before = sentence[:start].rsplit("\n", 1)[-1]
    after = sentence[end:].split("\n", 1)[0].replace("’", "'")
    return not before.strip() and CLAUSE.match(after) is not None
