"""从英文文本提取学习提示，可直接在 PyCharm 中运行。"""

import argparse
import json
import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEXT_SECTIONS = ("vocabulary", "grammar")
SOUND_SECTIONS = ("reduction", "weak_forms", "linking")
NOTE = "这是基于文本的分析。实际发音受重音、停顿和唱法影响，需要听音频确认。"

VOCABULARY = {
    "pick up": "拿起。在样例中，pick up the guitar 表示拿起吉他。",
    "guitar": "吉他，一种弦乐器。",
    "rehearse": "排练，为演出或表演提前练习。",
    "take it slow": "慢慢来，放慢节奏。",
}

REDUCTIONS = {
    "wanna": "口语中常表示 want to。例如 wanna sing 表示想唱歌。",
    "gonna": "口语中常表示 going to，用来谈论计划或即将发生的事。",
}

# 这里只收录已核对的词对。连读取决于音素，不能只看首尾字母。
LINKING = {
    "pick up": "pick 末尾的 /k/ 后面是 up 开头的元音。",
    "take it": "take 末尾的 /k/ 后面是 it 开头的元音。",
}

# 第一组捕获 can 和动词，第二组只捕获 can。
MODAL_CAN = re.compile(
    r"\b(?:i|you|we|they|he|she|it)\s+((can)\s+"
    r"(?:pick|sing|learn|take|play|help|rehearse))\b",
    re.IGNORECASE,
)


def new_result(sentence: str, source: str) -> dict:
    """建立输出的统一结构，各类别即使没有结果也会保留空列表。"""
    return {
        "input_text": sentence,
        "analysis_source": source,
        "pronunciation_note": NOTE,
        "vocabulary": [],
        "grammar": [],
        "reduction": [],
        "weak_forms": [],
        "linking": [],
        "speaking_tips": [],
    }


def check_sentence(sentence: str) -> None:
    if not sentence.strip():
        raise ValueError("请输入一句英文，不能只输入空格。")


def find_phrase(sentence: str, phrase: str):
    """按完整词或词组查找，忽略大小写，允许词间有多个空格。"""
    words = [re.escape(word) for word in phrase.split()]
    # 边界约束能避免把 wanna 匹配到 wannabe 中。
    pattern = r"(?<![\w'’])" + r"\s+".join(words) + r"(?![\w'’])"
    return re.finditer(pattern, sentence, re.IGNORECASE)


def make_item(sentence: str, start: int, end: int, explanation: str) -> dict:
    return {
        "text": sentence[start:end],
        "start": start,
        "end": end,
        "explanation_zh": explanation,
    }


def mark_pronunciation(item: dict, evidence: str, condition: str) -> dict:
    item["evidence"] = evidence
    item["actual_pronunciation"] = "uncertain"
    item["condition_zh"] = condition
    return item


def analyze(sentence: str) -> dict:
    """用少量离线规则分析一句英文。"""
    check_sentence(sentence)
    result = new_result(sentence, "offline_rules")

    for phrase, explanation in VOCABULARY.items():
        for match in find_phrase(sentence, phrase):
            start, end = match.span()
            result["vocabulary"].append(make_item(sentence, start, end, explanation))

    for match in MODAL_CAN.finditer(sentence):
        start, end = match.span(1)
        result["grammar"].append(
            make_item(sentence, start, end, "can 后接动词原形，可用来表示能力。")
        )
        start, end = match.span(2)
        item = make_item(sentence, start, end, "情态动词 can 在非重读时可能读作 /kən/。")
        result["weak_forms"].append(
            mark_pronunciation(item, "text_candidate", "作为情态动词使用，且没有被重读时。")
        )

    for phrase, explanation in REDUCTIONS.items():
        for match in find_phrase(sentence, phrase):
            start, end = match.span()
            item = make_item(sentence, start, end, explanation)
            result["reduction"].append(
                mark_pronunciation(item, "text_observed", "缩读拼写已出现，实际发音需听音频确认。")
            )

    for phrase, explanation in LINKING.items():
        for match in find_phrase(sentence, phrase):
            start, end = match.span()
            item = make_item(sentence, start, end, explanation)
            result["linking"].append(
                mark_pronunciation(item, "text_candidate", "自然语流中两个词之间没有明显停顿时。")
            )

    if result["reduction"]:
        result["speaking_tips"].append("试着对照读完整形式和缩读拼写，留意两者的节奏。")
    if result["weak_forms"]:
        result["speaking_tips"].append("练习读同一句话，比较重读与不重读 can 时的声音。")
    if result["linking"]:
        result["speaking_tips"].append("选一个标出的词对，先分开读，再尝试在两个词之间不停顿。")
    if not result["speaking_tips"]:
        result["speaking_tips"].append("先按意群朗读，再听音频核对重音与停顿。")

    return result


def analyze_with_fallback(sentence: str) -> dict:
    """加载模型配置，模型不可用时继续用同一句话做离线分析。"""
    from dotenv import load_dotenv

    # 支持在 PyCharm 直接运行此文件，也支持 python -m src.analyzer。
    if __package__:
        from .model_client import ModelError, analyze_with_model
    else:
        from model_client import ModelError, analyze_with_model

    # 以代码所在位置定位项目。已设置的进程环境变量优先。
    load_dotenv(PROJECT_ROOT / ".env", override=False, interpolate=False)
    try:
        return analyze_with_model(sentence)
    except ModelError as error:
        print(f"{error} 已切换到离线规则（offline_rules）。", file=sys.stderr)
        return analyze(sentence)


def main() -> None:
    parser = argparse.ArgumentParser(description="输出英文句子的学习提示 JSON。")
    parser.add_argument("sentence", nargs="?", help="需要分析的英文句子")
    parser.add_argument("--sample", action="store_true", help="运行项目内的原创样例")
    parser.add_argument("--model", action="store_true", help="使用 DeepSeek，失败时切换为离线规则")
    args = parser.parse_args()

    if args.sample and args.sentence is not None:
        parser.error("请选择 --sample 或输入自己的句子。")

    if args.sample:
        sample_path = PROJECT_ROOT / "data" / "sample.txt"
        sentence = sample_path.read_text(encoding="utf-8").strip()
    elif args.sentence is not None:
        sentence = args.sentence
    else:
        # 提示信息走错误输出，标准输出只保留 JSON，便于后续自动处理。
        print("请输入一句英文并按 Enter：", file=sys.stderr)
        try:
            sentence = input()
        except EOFError:
            parser.error("没有收到输入。可以加 --sample 运行项目样例。")

    try:
        if args.model:
            result = analyze_with_fallback(sentence)
        else:
            result = analyze(sentence)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
