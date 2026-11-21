"""用本地美式发音词典和项目指南复核标注，生成跟读用的对照 IPA。"""

import re
from dataclasses import dataclass
from functools import cache

import cmudict
from src.causal_reduction import is_causal_cause


WORD = r"[a-z]+(?:'[a-z]+)*"
WORDS = re.compile(rf"{WORD}(?:[ \t]+{WORD})?")
LYRIC_WORD = re.compile(r"['’]cause\b|[a-z]+(?:['’][a-z]+)*", re.IGNORECASE | re.ASCII)
VOWELS = {
    "AA": "ɑ", "AE": "æ", "AH": "ʌ", "AO": "ɔ", "AW": "aʊ", "AY": "aɪ",
    "EH": "ɛ", "ER": "ɝ", "EY": "eɪ", "IH": "ɪ", "IY": "i", "OW": "oʊ",
    "OY": "ɔɪ", "UH": "ʊ", "UW": "u",
}
CONSONANTS = {
    "B": "b", "CH": "tʃ", "D": "d", "DH": "ð", "F": "f", "G": "ɡ", "HH": "h", "JH": "dʒ",
    "K": "k", "L": "l", "M": "m", "N": "n", "NG": "ŋ", "P": "p", "R": "ɹ", "S": "s", "SH": "ʃ",
    "T": "t", "TH": "θ", "V": "v", "W": "w", "Y": "j", "Z": "z", "ZH": "ʒ",
}
# 对照采用一种词典列出的美式读法。功能词在分开读时选完整读法。
PREFERRED = {
    "again": "AH0 G EH1 N", "a": "EY1", "and": "AE1 N D", "of": "AH1 V", "to": "T UW1",
    "you": "Y UW1", "your": "Y AO1 R", "are": "AA1 R", "that": "DH AE1 T", "am": "AE1 M",
    "don't": "D OW1 N T", "won't": "W OW1 N T", "on": "AA1 N", "was": "W AA1 Z", "want": "W AA1 N T",
    "the": "DH IY1", "them": "DH EH1 M", "can": "K AE1 N", "at": "AE1 T",
    "as": "AE1 Z", "for": "F AO1 R",
}
WEAK = {
    "a": ("eɪ", "ə"), "an": ("æn", "ən"), "and": ("ænd", "ən"), "at": ("æt", "ət"),
    "can": ("kæn", "kən"), "her": ("hɝ", "hɚ"), "me": ("miː", "mi"), "of": ("ʌv", "əv"),
    "some": ("sʌm", "səm"), "them": ("ðɛm", "ðəm"), "will": ("wɪl", "wəl"),
    "you": ("juː", "jə"), "your": ("jɔɹ", "jɚ"),
    "for": ("fɔɹ", "fɚ"), "as": ("æz", "əz"), "or": ("ɔɹ", "ɚ"), "would": ("wʊd", "wəd"),
}
AUTO_WEAK = frozenset(WEAK) | {"the", "to"}
REDUCTIONS = {
    "wanna": ("wɑnt tu", "wɑnə"), "gonna": ("ɡoʊɪŋ tu", "ɡənə"),
    "gotta": ("ɡɑt tu", "ɡɑtə"), "gimme": ("ɡɪv mi", "ɡɪmi"),
    "lemme": ("lɛt mi", "lɛmi"),
}
FRONT_GLIDES = {"i", "ɪ", "eɪ", "aɪ", "ɔɪ"}
BACK_GLIDES = {"u", "oʊ", "aʊ"}
FLAPS = {"water": ("wɔ", "ɚ"), "better": ("bɛ", "ɚ"), "gotta": ("ɡɑ", "ə")}
PAIR_CATEGORIES = {"linking", "sound_change", "elision"}

REASONS = {
    "span": "找不到与原文一致的字符区间。",
    "word_count": "这个类别需要符合规则的单词或连续词对。",
    "weak_context": "这个上下文中没有可核对的弱读。",
    "weak_onset_unknown": "后词起始音不确定，暂时无法确定这个功能词的弱读。",
    "not_spelled_reduction": "原文没有出现受支持的非正式缩读拼写。",
    "unknown_word": "词典缺少这个词的可靠发音。",
    "ambiguous_sounds": "词典读法对目标音变是否成立有分歧。",
    "consonant_onset": "后词以辅音开头，超出本版连读范围。",
    "no_glide": "此元音词界暂缺可确认的过渡音。",
    "no_elision_cluster": "省音需要以 /t/ 或 /d/ 结尾的词尾辅音丛，后词以辅音开头。",
    "and_chips": "本版在此保留 and 的弱读教学。",
    "no_sound_change": "当前词界或词内没有成立的受支持音变。",
    "fricative_yod": "擦音与 /j/ 的合音超出本版已核对的范围，需要单独回听。",
    "duplicate": "改类后的类别、区间与另一条通过校验的候选相同。",
    "link_consonant_vowel": "词尾辅音接后词元音。",
    "link_glide": "两个元音之间可加轻滑音过渡。",
    "yod": "/t/ 或 /d/ 与后词 /j/ 可合音，属于变音。",
    "nasal": "/n/ 可受后词双唇音影响。",
    "cluster_elision": "/t/ 或 /d/ 位于词尾辅音丛，后面紧接另一辅音。",
    "weak": "单个功能词有本版支持的弱读。",
    "reduction": "原文出现本版支持的缩读拼写。",
    "causal_cause": "行首 Cause 引导原因从句，是 because 的非正式缩略。",
    "flap": "词内轻弹音符合本版美式示范。",
}


@dataclass(frozen=True)
class Check:
    status: str
    code: str
    category: str | None = None
    left: tuple = ()
    right: tuple = ()
    detail: tuple = ()


@cache
def pronunciation_dictionary():
    return cmudict.dict()


def phoneme(phone):
    if phone == "AH0":
        return "ə"
    if phone == "ER0":
        return "ɚ"
    return VOWELS.get(phone.rstrip("012")) or CONSONANTS[phone]


def phonetic_options(word):
    if word in PREFERRED:
        return (tuple(PREFERRED[word].split()),)
    return tuple(tuple(option) for option in pronunciation_dictionary().get(word, []))


def weak_form(word, before, after):
    # 回答末尾的 can 承担重音。数字、单字母等其他用途不自动判作弱读。
    following = re.match(rf"[ \t]+({WORD})", after)
    if word in {"can", "for", "as", "or", "would"} and not following:
        return None
    if word == "a" and (not following or re.search(r"\bplan[ \t]+$", before)):
        return None
    if word in {"the", "to"}:
        options = phonetic_options(following[1]) if following else ()
        if options and all(option[0] in CONSONANTS for option in options):
            return ("ði", "ðə") if word == "the" else ("tu", "tə")
    return WEAK.get(word)


def check_pair(category, words, left, right):
    tail, onset = left[-1], right[0]
    yod = tail in {"T", "D"} and onset == "Y"
    cluster = tail in {"T", "D"} and len(left) >= 2 and left[-2] in CONSONANTS and onset in CONSONANTS
    exception = words == ["and", "chips"]

    if category == "linking":
        if yod:
            return Check("reclassified", "yod", "sound_change", left, right)
        if cluster and not exception:
            return Check("reclassified", "cluster_elision", "elision", left, right)
        if onset in CONSONANTS:
            return Check("removed", "consonant_onset")
        if tail in CONSONANTS:
            return Check("passed", "link_consonant_vowel", category, left, right, ("‿",))
        vowel = phoneme(tail)
        if vowel in FRONT_GLIDES or vowel in BACK_GLIDES:
            glide = "j" if vowel in FRONT_GLIDES else "w"
            return Check("passed", "link_glide", category, left, right, (glide,))
        return Check("pending", "no_glide")
    if category == "elision":
        if exception:
            return Check("removed", "and_chips")
        if cluster:
            return Check("passed", "cluster_elision", category, left, right)
        return Check("removed", "no_elision_cluster")
    if yod:
        return Check("passed", "yod", category, left, right)
    if tail == "N" and onset in {"P", "B", "M"}:
        return Check("passed", "nasal", category, left, right)
    if tail in {"S", "Z"} and onset == "Y":
        return Check("pending", "fricative_yod")
    return Check("removed", "no_sound_change")


def validate_category(annotation, lyric):
    """先核对区间和发音现象，只在词界证据一致时通过或改类。"""
    start, end = annotation["start"], annotation["end"]
    if not 0 <= start < end <= len(lyric) or lyric[start:end] != annotation["text"]:
        return Check("removed", "span")
    word = annotation["text"].lower().replace("’", "'")
    kind = annotation["category"]
    if kind == "reduction" and is_causal_cause(lyric, start, end):
        return Check("passed", "causal_cause", kind, detail=("bɪˈkɒz", "kəz"))
    if not WORDS.fullmatch(word):
        return Check("removed", "word_count")
    if kind == "weak_forms":
        before = lyric[:start].rsplit("\n", 1)[-1].lower()
        after = lyric[end:].split("\n", 1)[0].lower()
        if forms := weak_form(word, before, after):
            return Check("passed", "weak", kind, detail=forms)
        following = re.match(rf"[ \t]+({WORD})", after)
        if word in {"the", "to"} and following:
            onset_types = {option[0] in CONSONANTS for option in phonetic_options(following[1])}
            if len(onset_types) != 1:
                return Check("pending", "weak_onset_unknown")
        return Check("removed", "weak_context")
    if kind == "reduction":
        if word in REDUCTIONS:
            return Check("passed", "reduction", kind, detail=REDUCTIONS[word])
        return Check("removed", "not_spelled_reduction")
    if kind == "sound_change" and word in FLAPS:
        return Check("passed", "flap", kind, detail=FLAPS[word])
    words = word.split()
    if kind == "sound_change" and len(words) == 1:
        if not phonetic_options(word):
            return Check("pending", "unknown_word")
        return Check("removed", "no_sound_change")
    if kind not in PAIR_CATEGORIES or len(words) != 2:
        return Check("removed", "word_count")
    left, right = map(phonetic_options, words)
    if not left or not right:
        return Check("pending", "unknown_word")
    checks = [check_pair(kind, words, first, second) for first in left for second in right]
    first_check = checks[0]
    signature = {(item.status, item.code, item.category, item.detail) for item in checks}
    if len(signature) == 1:
        return first_check
    if all(item.status == "removed" for item in checks):
        return first_check
    return Check("pending", "ambiguous_sounds")


def teaching_reading(check, text):
    """根据校验后的现象生成两行教学 IPA。"""
    rule = check.code
    if rule == "causal_cause":
        return (*check.detail, None, "这里引导原因从句，Cause 是 because 的非正式缩略。可对照 /bɪˈkɒz/ 与 /kəz/，不代表歌手必然这样读。")
    if rule == "weak":
        careful, spoken = check.detail
        return (careful, spoken, None,
                f"这里不承载重音时可以轻读为 /{spoken}/。先读完整形式，再放回歌词对照。")
    if rule == "reduction":
        careful, spoken = check.detail
        return careful, spoken, None, "先读出完整词组，再对照原文的口语缩读拼写和音标。"
    if rule == "flap":
        before, after = check.detail
        return (before + "t" + after, before + "ɾ" + after, "ɾ",
                "常见美式读法。重读首音节，进入较轻的后一音节时，让舌尖快速轻触上齿龈。")
    first = "".join(map(phoneme, check.left))
    second = "".join(map(phoneme, check.right))
    if text.lower().replace("’", "'") in {"don't you", "won't you"}:
        second = "juː"
    careful = f"{first} {second}"
    if rule == "link_consonant_vowel":
        return careful, first + "‿" + second, "‿", "两词间无停顿时，把前词末尾的辅音直接接到后词元音。"
    if rule == "link_glide":
        glide, = check.detail
        return careful, first + glide + second, glide, f"两词间无停顿时，可轻带 [{glide}] 滑向后词元音。"
    if rule == "cluster_elision":
        phone = phoneme(check.left[-1])
        return careful, f"{first[:-len(phone)]} {second}", None, f"先读出词尾 /{phone}/，再对比快读中省去该音的读法。"
    if rule == "yod":
        phone = phoneme(check.left[-1])
        fused = "tʃ" if phone == "t" else "dʒ"
        tip = f"词尾 /{phone}/ 保留时，连贯快读中可与 /j/ 合成 /{fused}/。先分开读，再练合音。"
        if text.lower().split()[0] == "and":
            tip += "and 已弱读成 /ən/ 时，词尾没有 /d/ 可以合音。"
        return careful, first[:-len(phone)] + fused + second[1:], fused, tip
    if rule == "nasal":
        return (careful, f"{first[:-1]}m {second}", None,
                "快读时，词尾 /n/ 受下一个双唇音影响，可以接近 [m]。先分开读再对照。")
    raise ValueError(f"unsupported verified pronunciation rule: {rule}")


def review_annotations(lyric, annotations):
    """保留每条候选的结果供后台审计，页面只取通过的两行音标。"""
    ready, audit = [], []
    checks = [(item, validate_category(item, lyric)) for item in annotations]
    # 若改类结果与原本正确的候选重复，保留原本正确的那一条。
    unchanged = {(item["start"], item["end"], check.category) for item, check in checks if check.status == "passed"}
    seen = set()
    for index, (item, check) in enumerate(checks):
        key = (item["start"], item["end"], check.category)
        if check.category and (key in seen or (check.status == "reclassified" and key in unchanged)):
            check = Check("removed", "duplicate")
        record = {"index": index, "text": item["text"], "start": item["start"], "end": item["end"],
                  "original_category": item["category"], "category": check.category,
                  "status": check.status, "code": check.code, "reason": REASONS[check.code]}
        audit.append(record)
        if not check.category:
            continue
        seen.add(key)
        approved = with_teaching_ipa(item, check)
        previous_ipa = item.get("ipa") or {}
        record["auto_filled"] = not all(previous_ipa.get(field) for field in ("careful", "spoken"))
        record["ipa"] = approved["ipa"]
        ready.append(approved)
    return {"annotations": ready, "audit": audit}


def with_teaching_ipa(item, check):
    careful, spoken, emphasis, tip = teaching_reading(check, item["text"])
    ipa = {"careful": f"/{careful}/", "spoken": f"/{spoken}/"}
    if emphasis and spoken.count(emphasis) == 1:
        ipa["emphasis"] = emphasis
    return {**item, "category": check.category, "ipa": ipa, "speaking_tip_zh": tip}


def candidate_spans(lyric):
    """逐行扫描整词和空白分隔的相邻词，保留每次出现的原文坐标。"""
    offset = 0
    for line in lyric.split("\n"):
        tokens = list(LYRIC_WORD.finditer(line))
        for index, token in enumerate(tokens):
            word = token[0].lower().replace("’", "'")
            following = tokens[index + 1] if index + 1 < len(tokens) else None
            adjacent = following is not None and line[token.end():following.start()].isspace()
            # 行末功能词可能承担句末重音。只有同一短语内才自动补这类弱读。
            if adjacent and word in AUTO_WEAK:
                yield offset + token.start(), offset + token.end(), "weak_forms"
            if word in REDUCTIONS or is_causal_cause(lyric, offset + token.start(), offset + token.end()):
                yield offset + token.start(), offset + token.end(), "reduction"
            if word in FLAPS:
                yield offset + token.start(), offset + token.end(), "sound_change"
            if adjacent:
                for category in ("linking", "sound_change", "elision"):
                    yield offset + token.start(), offset + following.end(), category
        offset += len(line) + 1


def supported_spans(lyric):
    """类别通过后才生成 IPA。共用模型候选使用的校验器。"""
    sound_changes = set()
    for start, end, category in candidate_spans(lyric):
        item = {"text": lyric[start:end], "start": start, "end": end, "category": category,
                "evidence": "text_observed" if category == "reduction" else "text_candidate",
                "actual_pronunciation": "uncertain", "source": "rule"}
        check = validate_category(item, lyric)
        if check.status != "passed":
            continue
        if check.code == "yod":
            sound_changes.add((start, end))
        # 同一个词界有 /t,d/ + /j/ 时优先教学合音，避免同时建议省掉这个音。
        if category == "elision" and (start, end) in sound_changes:
            continue
        yield with_teaching_ipa(item, check), check.code


def complete_annotations(lyric, model_items):
    """按原文位置补齐漏标。不同类别和重叠词界可以共存。"""
    review = review_annotations(lyric, model_items)
    ready = review["annotations"]
    known = {(item["start"], item["end"], item["category"]) for item in ready}
    supplements = []
    for item, code in supported_spans(lyric):
        key = (item["start"], item["end"], item["category"])
        if key in known:
            continue
        known.add(key)
        ready.append(item)
        supplements.append({**item, "code": code})
    review["annotations"] = sorted(ready, key=lambda item: (item["start"], item["end"], item["category"]))
    review["supplements"] = supplements
    return review
