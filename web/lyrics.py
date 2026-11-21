"""从本地参考歌词和音频证据生成时间轴。"""

import io
import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from statistics import median

from faster_whisper.audio import decode_audio, pad_or_trim
from faster_whisper.tokenizer import Tokenizer
from mutagen import File, MutagenError

LRC_TIME = re.compile(r"\[(\d{1,3}):(\d{2}(?:[.:]\d{1,3})?)\]")
WORD = re.compile(r"[a-z]+(?:'[a-z]+)?")


@dataclass(frozen=True)
class ReferenceLine:
    text: str
    start: float | None = None


@dataclass(frozen=True)
class Reference:
    source: str
    lines: tuple[ReferenceLine, ...]
    url: str = ""


def words(text):
    return WORD.findall(text.lower().replace("’", "'"))


def parse_lyrics(text):
    timed, plain = [], []
    for row in text.splitlines():
        row = row.strip()
        times = LRC_TIME.findall(row)
        if times:
            content = LRC_TIME.sub("", row).strip()
            if words(content):
                for minute, second in times:
                    timed.append(ReferenceLine(content, int(minute) * 60 + float(second.replace(":", "."))))
        elif row and not row.startswith("[") and words(row):
            plain.append(ReferenceLine(row))
    return tuple(sorted(timed, key=lambda row: row.start) if timed else plain)


def embedded_reference(audio):
    """识别 ID3 USLT/SYLT 与 MP4 的 lyrics 标签。"""
    try:
        file = File(io.BytesIO(audio))
    except (MutagenError, OSError, ValueError):
        return None
    if not file or not file.tags:
        return None
    if hasattr(file.tags, "getall"):
        # SYLT 的歌词内容类型为 1。仅采用毫秒格式，词级片段交回音频对齐。
        for frame in file.tags.getall("SYLT"):
            if frame.type == 1 and frame.format == 2 and frame.lang.lower() in {"eng", "und", "xxx"}:
                text = "".join(fragment for fragment, _ in frame.text)
                if lines := parse_lyrics(text):
                    return Reference("embedded", lines)
        for frame in file.tags.getall("USLT"):
            if frame.lang.lower() in {"eng", "und", "xxx"} and (lines := parse_lyrics(frame.text)):
                return Reference("embedded", lines)
    for text in file.tags.get("\xa9lyr", []):
        if isinstance(text, str) and (lines := parse_lyrics(text)):
            return Reference("embedded", lines)
    return None


def local_reference(path):
    if not path.is_file() or path.stat().st_size > 150_000:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        lines = tuple(ReferenceLine(**row) for row in data["lines"])
        if not lines or any(not words(row.text) or "\n" in row.text or "\r" in row.text for row in lines):
            return None
        times = [row.start for row in lines]
        if any(time is not None for time in times) and (
            not all(type(time) in {float, int} and 0 <= time < 10_800 for time in times)
            or any(left >= right for left, right in zip(times, times[1:]))
        ):
            return None
        url = data.get("source", "")
        return Reference("local_reference", lines, url if isinstance(url, str) else "")
    except (OSError, TypeError, KeyError, ValueError):
        return None


def compare(expected, observed):
    """保留单调的近似匹配；后续仍需用实测词时间或声学结果确认。"""
    match = SequenceMatcher(None, expected, observed, autojunk=False)
    return {block.a + index: block.b + index for block in match.get_matching_blocks()
            for index in range(block.size)}


def line_offsets(lines):
    matched, offset = [], 0
    for row in lines:
        tokens = words(row.text)
        matched.append((row, offset, tokens))
        offset += len(tokens)
    return matched


def match_reference(reference, observed, duration):
    """跨全曲比对连续词锚点。匹配不足或版本节奏明显不符时保留转写。"""
    rows = line_offsets(reference.lines)
    expected = [token for _, _, tokens in rows for token in tokens]
    if not 8 <= len(expected) <= 2500:
        return None
    mapping = compare(expected, [word["token"] for word in observed])
    triples = [i for i in mapping if mapping.get(i + 1) == mapping[i] + 1
               and mapping.get(i + 2) == mapping[i] + 2]
    if len(mapping) / len(expected) < 0.48 or len(triples) < 4:
        return None
    if (triples[-1] - triples[0]) / len(expected) < 0.56:
        return None

    if all(row.start is not None for row, _, _ in rows):
        offsets = [(observed[mapping[index]]["start"] - row.start, row.start)
                   for row, index, tokens in rows if len(tokens) >= 3 and index in triples]
        if len(offsets) < 4:
            return None
        center = median(value for value, _ in offsets)
        inliers = [(value, time) for value, time in offsets if abs(value - center) <= 1.5]
        if len(inliers) < max(4, len(offsets) * 0.65) or inliers[-1][1] - inliers[0][1] < (
            rows[-1][0].start - rows[0][0].start
        ) * 0.53:
            return None
        center = median(value for value, _ in inliers)
        starts = [row.start + center for row, _, _ in rows]
        if starts[0] < -3 or starts[-1] >= duration - 0.25:
            return None
        # 使用参考轴只限定搜索窗。输出时间仍来自实际音频。
        return rows, mapping, starts, round(center, 3)

    # 无时间戳的内嵌歌词只用实际识别到的词定位。
    starts = [observed[mapping[index]]["start"] if index in mapping else None for _, index, _ in rows]
    return rows, mapping, starts, None


def audio_anchor(words_in_line, observed, expected_start):
    all_tokens = [token["token"] for token in observed]
    width = len(words_in_line)
    exact = [i for i in range(len(all_tokens) - width + 1) if all_tokens[i:i + width] == words_in_line]
    if exact:
        closest = min(exact, key=lambda i: abs(observed[i]["start"] - expected_start))
        hits = observed[closest:closest + width]
        if median(word["probability"] for word in hits) >= 0.5:
            return hits[0]["start"], hits[-1]["end"]
    candidates = []
    for first, token in enumerate(all_tokens):
        if token != words_in_line[0]:
            continue
        mapping = compare(words_in_line[1:], all_tokens[first + 1:])
        coverage = (len(mapping) + 1) / width
        if width - 2 not in mapping or coverage < 0.65:
            continue
        hits = [observed[first], *[observed[first + 1 + index] for index in mapping.values()]]
        start, end = hits[0]["start"], hits[-1]["end"]
        if median(word["probability"] for word in hits) >= 0.5 and end - start <= max(4, width * 0.95):
            candidates.append((coverage, -abs(start - expected_start), start, end))
    if candidates:
        return max(candidates)[2:]
    return None


class AudioAligner:
    """在本地音频搜索窗口内对齐已知文字，并检查模型的对齐证据。"""

    def __init__(self, model, audio):
        self.model = model
        self.rate = model.feature_extractor.sampling_rate
        self.samples = decode_audio(io.BytesIO(audio), sampling_rate=self.rate)
        self.tokenizer = Tokenizer(model.hf_tokenizer, model.model.is_multilingual, "transcribe", "en")

    def __call__(self, text, begin, end, prefix="", suffix=""):
        samples = self.samples[round(begin * self.rate):round(end * self.rate)]
        features = self.model.feature_extractor(samples)
        encoded = self.model.encode(pad_or_trim(features))
        tokens = self.tokenizer.encode(" " + " ".join(part for part in (prefix, text, suffix) if part))
        aligned, = self.model.find_alignment(self.tokenizer, [tokens], encoded, features.shape[-1] - 1)
        start_index = len(words(prefix))
        spoken = [item for item in aligned if words(item["word"])][start_index:start_index + len(words(text))]
        if not spoken or median(item["probability"] for item in spoken) < 0.34:
            return None
        # DTW 会尽量把给定文本分配完，边缘吸附或多个词挤在同一帧时证据不足。
        usable = sum(item["end"] - item["start"] >= 0.06 and item["probability"] >= 0.15 for item in spoken)
        first, last = spoken[0], spoken[-1]
        if (usable < len(spoken) * 0.65 or first["start"] < 0.04 or last["end"] > end - begin - 0.05
                or last["end"] - first["start"] < 0.2):
            return None
        return begin + first["start"], begin + last["end"]


def align_reference(reference, observed, duration, force, progress):
    match = match_reference(reference, observed, duration)
    if match is None:
        return None
    rows, _, starts, offset = match
    segments = []
    for index, (row, _, tokens) in enumerate(rows):
        progress("transcribing", f"正在用本地录音对齐歌词（{index + 1}/{len(rows)}）…",
                 int(index * 100 / len(rows)))
        start = starts[index]
        next_start = starts[index + 1] if index + 1 < len(starts) else None
        bounds = None
        search_window = None
        method = "needs_review"
        if start is not None:
            begin = max(0, start - 1.75)
            end = min(duration, (next_start + 0.85) if next_start is not None else duration,
                      start + max(4.5, len(tokens) * 1.08 + 1.0))
            local = [word for word in observed if begin <= word["start"] < end]
            search_window = [round(begin, 3), round(end, 3)]
            bounds = audio_anchor(tokens, local, start)
            if bounds:
                method = "word_anchors"
            elif 0.25 < end - begin <= 29.5:
                prev_start = starts[index - 1] if index else None
                prefix = rows[index - 1][0].text if prev_start is not None and start - prev_start <= 8 else ""
                suffix = rows[index + 1][0].text if next_start is not None and next_start - start <= 8 else ""
                wide_begin = max(0, prev_start - 1.0) if prefix else begin
                wide_end = min(duration, next_start + 4.0) if suffix else end
                if 0.25 < wide_end - wide_begin <= 29.5:
                    bounds = force(row.text, wide_begin, wide_end, prefix, suffix)
                if bounds and begin <= bounds[0] <= start + 1.75 and bounds[1] <= end + 0.55:
                    method = "acoustic_alignment"
                else:
                    bounds = None
        segments.append({
            "text": row.text,
            "start_seconds": round(bounds[0], 3) if bounds else None,
            "end_seconds": round(bounds[1], 3) if bounds else None,
            "needs_review": bounds is None,
            "timing_method": method,
            "search_window": search_window,
        })

    # 邻行如果争夺同一段音频，不能一起当作确定的时间轴。
    previous = None
    for segment in segments:
        if segment["needs_review"]:
            continue
        if previous and (segment["start_seconds"] < previous["start_seconds"] or
                         segment["start_seconds"] + 0.45 < previous["end_seconds"]):
            overlap = previous if previous["timing_method"] == "acoustic_alignment" else segment
            overlap.update(start_seconds=None, end_seconds=None, needs_review=True,
                           timing_method="needs_review")
        if not segment["needs_review"]:
            previous = segment
    if sum(not row["needs_review"] for row in segments) < len(segments) * 0.55:
        return None
    return segments, offset
