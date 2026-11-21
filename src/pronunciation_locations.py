"""可追溯的原文单词编号协议；字符位置始终由 Python 生成。"""

import json
import re

if __package__:
    from .model_client import ModelError
else:
    from model_client import ModelError

LOCATION_SCHEMA = "pronunciation-location-v2"
LOCATION_PROMPT_VERSION = "pronunciation-v0.3-pilot-02-locations-01"
TOKEN = re.compile(r"['’]cause\b|[a-z]+(?:['’][a-z]+)*", re.IGNORECASE | re.ASCII)


def tokens(line):
    return list(TOKEN.finditer(line))


def prepare_input(text):
    """编号在每一行从 0 开始；标点、空格仍以 input_text 原文为准。"""
    return json.dumps({"schema_version": LOCATION_SCHEMA, "lines": [
        {"line": number, "input_text": line,
         "tokens": [{"id": i, "text": match[0]} for i, match in enumerate(tokens(line))]}
        for number, line in enumerate(text.split("\n"), 1)]}, ensure_ascii=False)


def check_context(line, item, start, end):
    """只验证模型原样提供的 context，不构造、不纠正上下文。"""
    if "context" not in item:
        return
    context = item["context"]
    if not isinstance(context, str) or not context.strip():
        raise ModelError("context 必须是非空原文片段。")
    location = line.find(context)
    if location < 0 or line.find(context, location + 1) >= 0:
        raise ModelError("context 在原文中无法唯一定位。")
    if not location <= start < end <= location + len(context):
        raise ModelError("context 与选定的原文位置不一致。")


def locate_tokens(line, item):
    """选定连续的单词 ID 后，从原文 Match 对象导出 start/end。"""
    ids = item.get("token_ids")
    source = tokens(line)
    if (not isinstance(ids, list) or not ids or len(ids) > len(source)
            or any(type(i) is not int for i in ids)):
        raise ModelError("token_ids 必须是非空整数数组。")
    if ids != list(range(ids[0], ids[-1] + 1)) or not 0 <= ids[0] <= ids[-1] < len(source):
        raise ModelError("token_ids 必须按原文顺序连续、无重复且不越界。")
    start, end = source[ids[0]].start(), source[ids[-1]].end()
    if item.get("text") != line[start:end]:
        raise ModelError("token_ids 对应的 text 与原文不一致。")
    if any(name in item for name in ("start", "end")):
        if (type(item.get("start")) is not int or type(item.get("end")) is not int
                or item["start"] != start or item["end"] != end):
            raise ModelError("额外字符位置与 token_ids 计算的位置不一致。")
    check_context(line, item, start, end)
    return start, end


def build_location_prompt(legacy_prompt):
    """旧 pilot-02 文本不改写，新版本规则作为明确的协议扩展。"""
    return LOCATION_PROMPT_VERSION + "\n" + legacy_prompt + f"""

【新版本响应协议：{LOCATION_SCHEMA}；以下定位和 Cause 扩展优先于旧版定位描述】
用户消息是 JSON，lines 每项的 input_text 是未经改写的一行原文。
line 是从 1 开始的行号；tokens 是 Python 生成的单词表，每行 id 从 0 开始。
这些是给定的单词 ID，不是字符位置，不要自己重新分词或计算字符索引。
返回 {{"schema_version":"{LOCATION_SCHEMA}","annotations":[...]}}。
每项保留 text/category/evidence/speaking_tip_zh/可选 ipa，并必须返回 line 和 token_ids。
token_ids 逐项复制待标注连续原文词的 id；单个词也要用数组。重复词每次各选其确切 ID。
text 必须与所选连续单词的原文一致，包括中间空格、标点和大小写。不要返回 start/end。
Python 从这些 ID 对应的原文区间计算最终 start/end（0-based、右端不含）。
可另给 context；它必须逐字复制该行中唯一出现的连续原文，并包含所选片段。
不能用整句但不含该片段的 context，不能伪造或规范化 context。
无 token_ids 时只允许旧版唯一原文 context 消歧；缺少定位信息就会被拒绝，不能按列表顺序猜。

示例：第 2 行为 “We can go, we can stay.”，给定 tokens 为
0:We 1:can 2:go 3:we 4:can 5:stay。
第二个 can 返回 {{"line":2,"token_ids":[4],"text":"can","category":"weak_forms",
"evidence":"text_candidate","speaking_tip_zh":"不强调能力时，可轻读为 /kən/。"}}。
第一次 can 用 [1]；go, we 这段原文若标注，其 ID 为 [2,3]，text 必须保留逗号和空格。
同一句重复在两行时，分别使用各自 line 和该行 token_ids，不能合并成一次。

缩读扩展：Lemme 已受支持。另仅在行首 Cause/'cause/’cause 后紧接代词主语与
明确的限定助动词（例如 you were / I'm / we have）引导原因从句时，可标 reduction，
expansion 必须为 "because"，evidence=text_observed。提示解释 because 的非正式缩略，
不确定实际发音。不能把 a good cause、cause trouble、cause you pain、cause you to wait
的名词或动词 cause 标为缩读。上下文不足时不要标 Cause，不能靠字符串就判断。
其他五类规则不变。无音频证据时 actual_pronunciation 统一由 Python 设为 uncertain。
"""
