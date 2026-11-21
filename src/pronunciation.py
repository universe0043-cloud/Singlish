"""生成指定版本的发音提示词并校验标注。"""

import json

from .analyzer import PROJECT_ROOT, check_sentence, mark_pronunciation
from .model_client import ModelError, locate_span
from .causal_reduction import is_causal_cause


PROMPT_VERSION = "pronunciation-v0.3-pilot-01"
EXAMPLE_IDS = ("pilot-001", "pilot-003", "pilot-010", "pilot-019")
PILOT_02_VERSION = "pronunciation-v0.3-pilot-02"
PILOT_02_EXAMPLE_IDS = (*EXAMPLE_IDS, "pilot-008", "pilot-016")
PILOT_03_VERSION = "pronunciation-v0.4-pilot-03"
PILOT_03_EXAMPLE_IDS = (*PILOT_02_EXAMPLE_IDS, "pilot-020")
RESPONSE_FIELDS = ("text", "category", "evidence", "speaking_tip_zh")
EVIDENCE_BY_CATEGORY = {
    "weak_forms": "text_candidate",
    "linking": "text_candidate",
    "elision": "text_candidate",
    "sound_change": "text_candidate",
    "reduction": "text_observed",
}
# 校验词表与测试参考对齐。已归档的提示词版本仍按原文生成。
PILOT_REDUCTIONS = {"wanna", "gonna", "gotta", "gimme", "lemme"}


def build_pronunciation_prompt(version: str = PROMPT_VERSION) -> str:
    guide_version = "v0.3"
    if version == PROMPT_VERSION:
        example_ids = EXAMPLE_IDS
    elif version == PILOT_02_VERSION:
        example_ids = PILOT_02_EXAMPLE_IDS
    elif version == PILOT_03_VERSION:
        example_ids = PILOT_03_EXAMPLE_IDS
        guide_version = "v0.4"
    else:
        raise ModelError("未知的发音提示词版本。")

    path = PROJECT_ROOT / "data" / f"pronunciation_pilot_{guide_version}.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    by_id = {row["id"]: row for row in rows}
    example_lines = []
    covered = set()
    for example_id in example_ids:
        row = by_id[example_id]
        output = {
            "annotations": [{key: item[key] for key in RESPONSE_FIELDS} for item in row["annotations"]],
        }
        covered.update(item["category"] for item in output["annotations"])
        example_lines.append(
            f"{example_id}\n原句：{row['input_text']}\nJSON：{json.dumps(output, ensure_ascii=False)}"
        )

    if covered != set(EVIDENCE_BY_CATEGORY):
        raise ModelError("试跑示例未覆盖全部五类。")

    linking_rule = """- linking：相邻词的常用读音直接满足前词以辅音结束、后词以元音开始。标连续两个词。
  提示无停顿才可能连读。排除 turn left、需要先去掉 /h/ 的 call her。
  did I 可标连读，did you 的 /d/ 与 /j/ 合音属于变音。"""
    if version == PILOT_03_VERSION:
        linking_rule = """- linking：标连续两个原文词。按词界音素判断，收录辅音接元音，
  以及无明显停顿时可用轻滑音 [j] 或 [w] 过渡的元音接元音。提示写出具体过渡音。
  辅音接辅音、元音接辅音和需要先省去其他音才能成立的情况都超出本版范围。
  did I 可标连读，did you 的 /d/ 与 /j/ 合音属于变音。"""

    span_rule = "只出现一次且只包含一次 text 的连续片段。字符位置由 Python 计算，不返回 start 或 end。"
    if version == PILOT_03_VERSION:
        span_rule = (
            "只出现一次且只包含一次完整的 text 的连续片段。text 按完整词或词组匹配。"
            "字符位置由 Python 计算，不返回 start 或 end。"
        )
    rules = f"""按 Singlish 发音试标指南 {guide_version} 标注用户消息中的英文原句。只返回一个 JSON 对象，
结构为 {{"annotations": [...] }}，没有符合规则的标注时返回 {{"annotations": []}}。
每项必须包含 text、category、evidence 和 speaking_tip_zh。text 逐字复制一段连续原文，
保留大小写、空格和标点。重复片段用额外的 context 字段消歧，context 必须是原文中
{span_rule}
允许多项、区间重叠以及同一区间的不同类别。同类别、同一区间只标一次。

只使用以下类别。中文提示写明成立条件，输入没有音频，不能断言实际发音。
- weak_forms：有可教弱式且可能不重读的功能词。标单词。回答或对比重点按完整读法，
  例如 Yes, I can. 的 can 不标弱读。
{linking_rule}
- elision：前词以辅音丛结尾、末音是 /t/ 或 /d/，后词以辅音开始时才考虑。
  标连续两个词，并给出保留末音的读法供对照。next item 不按 next week 标注。
  and chips 的省音本版暂缓，and 的弱读已覆盖这一听辨点。
- sound_change：包括 /d/ 或 /t/ 与 /j/ 合音（例如 Don't you 的 /t/ 与 /j/），
  相邻辅音导致发音部位变化（例如 ten people），以及词内美式 /t/ 轻弹音 [ɾ]。
  跨词变化标词对，词内变化标整词。轻弹音注明常见美式读法及重音条件。
- reduction：本批仅标原文中直接出现的非正式拼写 wanna、gonna、gotta、gimme，
  保留原大小写；I'm、Don't、won't 等常规缩写不属于本版口语缩读。

reduction 的 evidence 为 text_observed，其余四类为 text_candidate。
发音确定性由 Python 统一设为 uncertain，请省略 actual_pronunciation。
以下是 v0.3 数据中的四条示例，仅用于说明规则和返回格式。"""
    if version in (PILOT_02_VERSION, PILOT_03_VERSION):
        linking_check = """1. linking：逐个检查相邻词，按常用读音判断前词最后一个音素与后词第一个音素。
   只有「辅音接元音」才标。正例 Hold on，/d/ 接元音。反例 turn left，/n/ 接 /l/，
   属于辅音接辅音。反例 go out，/oʊ/ 接 /aʊ/，属于元音接元音。连续读时可能出现的
   [j] 或 [w] 过渡音、双元音的滑动都不算前词原有的末尾辅音。元音接辅音也不标。"""
        if version == PILOT_03_VERSION:
            linking_check = """1. linking：逐个检查相邻词的词界音素。正例 Hold on，/d/ 接元音；
   正例 see it，/iː/ 接 /ɪ/ 时可轻带 [j]；正例 go out，/oʊ/ 接 /aʊ/ 时可轻带 [w]。
   元音间的轻滑音只是过渡。在中文提示里写出 [j] 或 [w]，并说明两词之间无明显停顿的条件。
   反例 turn left，/n/ 接 /l/，属于辅音接辅音。元音接辅音也不标。"""
        rules = rules.rsplit("\n", 1)[0] + f"""

返回 JSON 前，针对原句逐项检查五类：
{linking_check}
2. weak_forms：逐词查找有常见弱式且可能不承载重音的功能词，尤其要找冠词 a。
   不重读的 a 可读 /ə/，即使它所在的两词交界不符合连读，也可单独标 a。
   非正式拼写如 gonna 按 reduction 教学，不因读得快或轻就另标 weak_forms。
3. elision：逐个检查词界，前词以辅音丛结尾且最后是 /t/ 或 /d/，后词以辅音起始时，
   考虑末音在快读中省去的候选，并用保留末音的读法对照。
4. sound_change：既检查跨词音变，也逐词检查词内音变。示例 water 中，
   /t/ 在重读音节之后、较轻音节之前可读成常见美式轻弹音 [ɾ]，标整个词。
5. reduction：只标原句中直接出现的非正式缩读拼写。同一区间加第二类时，
   必须在中文提示里指出独立的发音现象。例如 gotta 的缩读拼写归 reduction，
   重读后、较轻音节前的美式 [ɾ] 则是独立的 sound_change。

五类逐项检查后，保留符合规则的全部标注，包括允许重叠的区间。
没有符合项时，返回 {{"annotations": []}}。
以下是 {guide_version} 数据示例，仅用于说明规则和返回格式。"""
    return f"{version}\n{rules}\n\n" + "\n\n".join(example_lines)


def validate_pronunciation(sentence: str, content: str, *, allow_causal_cause: bool = False) -> dict:
    """验证模型正文并用原句计算坐标，保持模型生成的教学提示。"""
    check_sentence(sentence)
    try:
        raw = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        raise ModelError("发音标注响应不是有效 JSON。") from None
    if not isinstance(raw, dict) or not isinstance(raw.get("annotations"), list):
        raise ModelError("发音标注响应必须是含 annotations 数组的 JSON 对象。")

    annotations = []
    seen = set()
    for index, item in enumerate(raw["annotations"]):
        label = f"annotations[{index}]"
        if not isinstance(item, dict):
            raise ModelError(f"{label} 必须是对象。")
        category = item.get("category")
        if not isinstance(category, str) or category not in EVIDENCE_BY_CATEGORY:
            raise ModelError(f"{label} 的 category 不属于指南的五类。")
        evidence = EVIDENCE_BY_CATEGORY[category]
        if item.get("evidence") != evidence:
            raise ModelError(f"{label} 的 evidence 必须为 {evidence}。")
        tip = item.get("speaking_tip_zh")
        if not isinstance(tip, str) or not tip.strip():
            raise ModelError(f"{label} 缺少中文练习提示。")
        try:
            start, end = locate_span(sentence, item, allow_case_mismatch=True)
        except ModelError as error:
            raise ModelError(f"{label} {error}") from None
        source_text = sentence[start:end]
        if not 0 <= start < end <= len(sentence) or source_text.lower() != item["text"].lower():
            raise ModelError(f"{label} 的位置与原文片段不一致。")
        causal_cause = category == "reduction" and allow_causal_cause and is_causal_cause(sentence, start, end)
        if causal_cause and item.get("expansion", "because") != "because":
            raise ModelError(f"{label} 的 Cause expansion 必须为 because。")
        if category == "reduction" and source_text.lower() not in PILOT_REDUCTIONS and not causal_cause:
            raise ModelError(f"{label} 不是本批指南中的口语缩读形式。")
        key = (category, start, end)
        if key in seen:
            raise ModelError(f"{label} 与前面的标注类别和区间重复。")
        seen.add(key)
        annotations.append({
            "text": source_text,
            "start": start,
            "end": end,
            "category": category,
            "evidence": evidence,
            "actual_pronunciation": "uncertain",
            "speaking_tip_zh": tip,
        })
    return {
        "input_text": sentence,
        "analysis_source": "configured_model",
        "annotations": annotations,
    }
