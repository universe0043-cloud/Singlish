"""英式学习词典式展示层。原始模型、规则 IPA 和缓存均保持原样。"""

import re
from functools import cache
from pathlib import Path

from web.ipa import LYRIC_WORD, validate_category

PROFILE = "gb-learner-display-v1"
LEXICON_PATH = Path(__file__).resolve().parents[1] / "data" / "en_UK.txt"
VOWEL = re.compile(r"eɪ|aɪ|ɔɪ|əʊ|aʊ|ɪə|eə|ʊə|[iɪeæɑɒɔʊuʌəɜɐɛ](?:ː)?")
ONSETS = frozenset(
    "p b t d k ɡ f v θ ð s z ʃ ʒ h m n l r w j tʃ dʒ "
    "pl pr bl br tr dr kl kr ɡl ɡr fl fr θr sl sm sn sw sp st sk "
    "tw dw kw ɡw ʃr spr str skr spl skw pj bj tj dj kj ɡj fj vj mj nj hj".split()
)
# 对功能词、常见缩约形式及来源词库中的歧义项使用逐词核对的读法。
# 词汇源及核对依据见 data/ipa_lexicon_source.json 和 README。
WORDS = {
    "a": "eɪ", "am": "æm", "an": "æn", "are": "ɑː", "as": "æz",
    "be": "biː", "been": "biːn", "can": "kæn", "can't": "kɑːnt", "do": "duː",
    "don't": "dəʊnt", "won't": "wəʊnt", "i": "aɪ", "i'd": "aɪd", "i'll": "aɪl",
    "i'm": "aɪm", "i've": "aɪv", "is": "ɪz", "it's": "ɪts", "of": "ɒv",
    "the": "ðiː", "that's": "ðæts", "there's": "ðeəz", "wouldn't": "ˈwʊdnt",
    "you'd": "juːd", "you're": "jɔː", "ain't": "eɪnt", "upset": "ʌpˈset",
    "again": "əˈɡen", "someone": "ˈsʌmwʌn", "nobody": "ˈnəʊbədi",
    "anything": "ˈeniθɪŋ", "everything": "ˈevriθɪŋ", "balcony": "ˈbælkəni",
    "kaleidoscope": "kəˈlaɪdəskəʊp", "teacher": "ˈtiːtʃə",
    "beautiful": "ˈbjuːtɪfəl", "important": "ɪmˈpɔːtənt", "water": "ˈwɔːtə",
    "better": "ˈbetə", "gonna": "ˈɡənə", "gotta": "ˈɡɒtə",
    "gimme": "ˈɡɪmi", "lemme": "ˈlemi", "wanna": "ˈwɒnə",
    "our": "aʊə", "tired": "taɪəd",
}
WEAK = {
    "a": ("eɪ", "ə"), "an": ("æn", "ən"), "and": ("ænd", "ən"),
    "at": ("æt", "ət"), "can": ("kæn", "kən"), "her": ("hɜː", "hə"),
    "me": ("miː", "mi"), "of": ("ɒv", "əv"), "some": ("sʌm", "səm"),
    "them": ("ðem", "ðəm"), "will": ("wɪl", "wəl"), "you": ("juː", "jə"),
    "your": ("jɔː", "jə"), "for": ("fɔː", "fə"), "as": ("æz", "əz"),
    "or": ("ɔː", "ə"), "would": ("wʊd", "wəd"), "the": ("ðiː", "ðə"),
    "to": ("tuː", "tə"),
}
REDUCTIONS = {
    "wanna": ("wɒnt tuː", "ˈwɒnə"), "gonna": ("ˈɡəʊɪŋ tuː", "ˈɡənə"),
    "gotta": ("ɡɒt tuː", "ˈɡɒtə"), "gimme": ("ɡɪv miː", "ˈɡɪmi"),
    "lemme": ("let miː", "ˈlemi"),
}
# /ɾ/ 属于真实的美式音值，不把它替换成英式 /r/ 或伪装成英式音变。
US_FLAPS = {
    "water": ("ˈwɔːtər", "ˈwɔːɾər"),
    "better": ("ˈbetər", "ˈbeɾər"),
    "gotta": ("ˈɡɑːtə", "ˈɡɑːɾə"),
}


@cache
def lexicon():
    return dict(line.split("\t", 1) for line in LEXICON_PATH.read_text(encoding="utf-8").splitlines())


def familiar_symbols(value):
    """只做记号统一。ɾ、长音、重音及不同元音均保持独立。"""
    return value.replace("ɹ", "r").replace("ɛ", "e")


def dictionary_stress(value):
    """RP 源将部分重音置于元音前，按最大合法声母移回音节开头。"""
    output = value
    for position in reversed([match.start() for match in re.finditer("[ˈˌ]", value)]):
        if not VOWEL.match(output, position + 1):
            continue
        before = output[:position]
        previous = list(VOWEL.finditer(before))
        boundary = previous[-1].end() if previous else 0
        cluster = before[boundary:].replace("ˈ", "").replace("ˌ", "")
        onset = max((part for part in ONSETS if cluster.endswith(part)), key=len, default="")
        target = position - len(onset)
        output = output[:target] + output[position] + output[target:position] + output[position + 1:]
    if len(VOWEL.findall(output)) == 1:
        output = output.replace("ˈ", "").replace("ˌ", "")
    return output


def word_reading(word, before="", after=""):
    word = word.lower().replace("’", "'")
    if word in WORDS:
        return WORDS[word]
    # close 的动词、形容词读法不同，不能只凭美式字符串替换。
    if word == "close":
        if re.match(r"\s+(?:your|my|his|her|the|our|their)\b", after, re.I):
            return "kləʊz"
        if re.match(r"\s+to\b", after, re.I):
            return "kləʊs"
        return None
    if word.endswith("'s"):
        stem = word_reading(word[:-2], before, after)
        if stem:
            suffix = "ɪz" if re.search(r"(?:s|z|ʃ|ʒ|tʃ|dʒ)$", stem) else (
                "s" if re.search(r"(?:p|t|k|f|θ)$", stem) else "z"
            )
            return stem + suffix
    raw = lexicon().get(word)
    if raw is None:
        return None
    choices = {part.strip().strip("/") for part in raw.split(",")}
    if len(choices) != 1:
        return None
    value, = choices
    # 只对这个 RP 来源的非重读 ɐ 采用学习词典的 schwa 写法。
    if re.search("[ˈˌ]ɐ", value) or any(symbol in value for symbol in ("ɚ", "ɝ", "ɾ")):
        return None
    value = familiar_symbols(value).replace("ɐ", "ə")
    return dictionary_stress(value)


def display_reading(lyric, annotation):
    """按已通过的类别重新组合 UK 词条，保持原来的可选口语现象。"""
    check = validate_category(annotation, lyric)
    if not check.category:
        return None
    text = annotation["text"].lower().replace("’", "'")
    rule = check.code
    if rule == "causal_cause":
        return ("bɪˈkɒz", "kəz", None, "gb",
                "这里引导原因从句，Cause 是 because 的非正式缩略。口语示范 /kəz/ 是可选读法，实际演唱仍需听音频确认。")
    if rule == "weak":
        forms = WEAK.get(text)
        if forms:
            return (*forms, None, "gb",
                    f"不强调这个词时，可轻读为 /{forms[1]}/。先练常规读法，再放回原句对照。")
        return None
    if rule == "reduction":
        forms = REDUCTIONS.get(text)
        if forms:
            return (*forms, None, "gb", "先练完整词组，再对照这种可选的非正式口语缩读。")
        return None
    if rule == "flap":
        forms = US_FLAPS.get(text)
        if forms:
            return (*forms, "ɾ", "us-flap",
                    "这条保留常见美式轻弹音示范，两行均采用美式读法。"
                    "[ɾ] 表示舌尖快速轻触，与 /r/ 不同。它是一种可选读法，英式通常保留 /t/。")
        return None
    tokens = list(LYRIC_WORD.finditer(annotation["text"]))
    if len(tokens) != 2:
        return None
    start = annotation["start"]
    readings = [
        word_reading(token[0], lyric[:start + token.start()], lyric[start + token.end():])
        for token in tokens
    ]
    if any(value is None for value in readings):
        return None
    first, second = readings
    careful = first + " " + second
    if rule == "link_consonant_vowel":
        # UK 非卷舌词尾的 r 只在词典词条及后续元音共同支持时接回。
        if text.split()[0].endswith(("r", "re")) and VOWEL.search(first) and VOWEL.match(second.lstrip("ˈˌ")):
            if VOWEL.search(first) and first[-1] in "ːə":
                first += "r"
        return careful, first + "‿" + second, "‿", "gb", "两词之间无停顿时，可把词尾与后词元音连起来；停顿时分开读。"
    if rule == "link_glide":
        glide, = check.detail
        return careful, first + glide + second, glide, "gb", f"两词之间无停顿时，可轻带 [{glide}] 过渡；不需要把它重读。"
    if rule == "cluster_elision" and first[-1] in "td":
        phone = first[-1]
        return careful, first[:-1] + " " + second, None, "gb", f"连贯快读时，辅音丛里的 /{phone}/ 有时可省去；清晰慢读时保留。"
    if rule == "yod" and first[-1] in "td" and second.startswith("j"):
        fused = "tʃ" if first.endswith("t") else "dʒ"
        tip = f"无停顿且词尾 /{first[-1]}/ 保留时，可与后面的 /j/ 合为 /{fused}/；也可以分开读。"
        if text.startswith("and "):
            tip += "and 弱读成 /ən/ 时没有 /d/，不再做这次合音。"
        return careful, first[:-1] + fused + second[1:], fused, "gb", tip
    if rule == "nasal" and first.endswith("n"):
        return careful, first[:-1] + "m " + second, None, "gb", "连贯快读时，/n/ 在后面的双唇音前可以接近 [m]；清晰读时保留 /n/。"
    return None


def display_annotation(lyric, annotation):
    """添加可追溯的视图字段，不覆盖 ipa、speaking_tip_zh 或历史分析。"""
    result = {**annotation}
    reading = display_reading(lyric, annotation)
    metadata = {"profile": PROFILE, "lexicon": "ipa-dict/en_UK", "status": "needs_review"}
    result["ipa_display"] = None
    result["ipa_display_note"] = "这处英式示范尚需核对，可先听原句。"
    if reading:
        careful, spoken, emphasis, accent, tip = reading
        ipa = {"careful": f"/{careful}/", "spoken": f"/{spoken}/"}
        if accent == "us-flap":
            ipa["spoken"] = f"[{spoken}]"
        if emphasis and emphasis != "‿" and spoken.count(emphasis) == 1:
            ipa["emphasis"] = emphasis
        metadata.update(status="ready", accent=accent)
        if accent == "us-flap":
            metadata["lexicon"] = "checked-us-flap-exceptions"
        result["ipa_display"] = ipa
        result["ipa_display_note"] = tip
    result["ipa_display_metadata"] = metadata
    return result
