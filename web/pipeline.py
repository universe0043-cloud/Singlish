"""本地音频转写、发音分析及各阶段的缓存。"""

import hashlib
import io
import json
import logging
import os
import sqlite3
import time
import traceback
from contextlib import closing
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from threading import Lock

from faster_whisper.audio import decode_audio

from src.model_client import ModelError, request_deepseek, require_deepseek_content
from src.pronunciation import PILOT_02_VERSION, build_pronunciation_prompt, validate_pronunciation
from src.pronunciation_locations import (LOCATION_SCHEMA, LOCATION_PROMPT_VERSION,
                                         build_location_prompt, prepare_input)
from web.lyrics import AudioAligner, align_reference, embedded_reference, local_reference, words

MODEL_NAME = "small.en"
MODEL_REVISION = "d1d751a5f8271d482d14ca55d9e2deeebbae577f"
WHISPER_OPTIONS = {"language": "en", "beam_size": 5, "temperature": 0,
                   "word_timestamps": True, "vad_filter": False,
                   "condition_on_previous_text": False}
CHUNK_SIZE = 200
IPA_INSTRUCTION = """

本轮用户消息的每行都以「[行号] 」开头。这是定位标记，后面才是原文。
逐行检查，每个标注必须返回所在行的整数 line（例如 2）。
text 逐字复制该行里的连续片段，不带行号。只有同一行内重复的片段才需要
该行内能唯一定位的 context。同一句歌词唱多次时，各行分别标注。
对有可靠口语示范的条目附上可选字段
"ipa": {"careful": "分开读的 IPA", "spoken": "口语示范 IPA", "emphasis": "spoken 中需要注意的连续片段"}。
示例：[2] We can sing. 中可返回 {"line": 2, "text": "can", "category": "weak_forms",
"evidence": "text_candidate", "speaking_tip_zh": "不强调能力时把 can 轻读为 /kən/。",
"ipa": {"careful": "/kæn/", "spoken": "/kən/", "emphasis": "ə"}}。
用常见美式英语作为口语示范，保留分开读与口语读法的区别。
emphasis 必须只在 spoken 中出现一次，无法唯一指出时省略 emphasis。
IPA 是教学示范，不能据此声称录音中的歌手实际这么读。没有可靠示范时省略 ipa。
"""
EDIT_IPA_INSTRUCTION = (
    "\n本次用户修订了标记为 [{line}] 的歌词行。请优先检查该行的全部发音标注，"
    "对该行每个可可靠示范的标注直接返回结构化 ipa，填写 careful 和 spoken。"
    "适合强调且在 spoken 中唯一的音写入 emphasis。请勿让 ipa 只出现在中文提示里。"
)


def sha(value):
    if isinstance(value, str):
        value = value.encode("utf-8")
    return hashlib.sha256(value).hexdigest()


def input_summary(text):
    return {"sha256": sha(text), "characters": len(text), "lines": len(text.splitlines())}


class StageError(ValueError):
    """可在页面上解释的失败。"""


def stage_failure(stage, error):
    """记录阶段和异常来源，避免把请求内容或密钥写入日志。"""
    cause = error.__cause__ or error
    origin = traceback.extract_tb(cause.__traceback__)[-1:]
    details = {"stage": stage, "exception": type(cause).__name__}
    if origin:
        frame = origin[0]
        details["origin"] = f"{Path(frame.filename).name}:{frame.lineno} ({frame.name})"
    if isinstance(cause, sqlite3.Error):
        details["sqlite_code"] = getattr(cause, "sqlite_errorname", None)
    logging.warning("Singlish failure: %s", details)
    return details


class ResultCache:
    def __init__(self, directory):
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)
        self.database = directory / "results.sqlite3"
        try:
            with closing(self.connect()) as database, database:
                database.execute("CREATE TABLE IF NOT EXISTS results (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        except sqlite3.Error as error:
            stage_failure("cache_setup", error)

    def connect(self):
        return sqlite3.connect(self.database)

    def get(self, key):
        try:
            with closing(self.connect()) as database:
                row = database.execute("SELECT value FROM results WHERE key = ?", (key,)).fetchone()
            return json.loads(row[0]) if row else None
        except (sqlite3.Error, ValueError) as error:
            stage_failure("cache_read:" + key.partition(":")[0], error)
            return None

    def put(self, key, value):
        with closing(self.connect()) as database, database:
            database.execute("INSERT OR REPLACE INTO results VALUES (?, ?)",
                             (key, json.dumps(value, ensure_ascii=False)))

    def remember(self, key, value):
        """缓存是可重算的。写入失败时，已生成的结果仍应交给用户。"""
        try:
            self.put(key, value)
        except sqlite3.Error as error:
            stage_failure("cache_write:" + key.partition(":")[0], error)


def lyric_lines(segments):
    """原样用换行连接转写行，同时记录 Python 字符区间。"""
    offset = 0
    lines = []
    for segment in segments:
        text = segment["text"]
        lines.append({**segment, "start": offset, "end": offset + len(text)})
        offset += len(text) + 1
    return "\n".join(row["text"] for row in lines), lines


def chunks(text, limit=CHUNK_SIZE):
    """优先在行尾分段，其次在空白处分段，保留偏移与标点。"""
    start = 0
    while start < len(text):
        end = min(start + limit, len(text))
        if end < len(text):
            boundary = text.rfind("\n", start + limit // 2, end)
            if boundary < 0:
                boundary = max(text.rfind(" ", start + limit // 2, end),
                               text.rfind("\t", start + limit // 2, end))
            if boundary >= 0:
                end = boundary + 1
        part = text[start:end]
        if part.strip():
            yield start, part
        start = end


def optional_ipa(value):
    if not isinstance(value, dict):
        return None
    careful, spoken = (value.get(name) for name in ("careful", "spoken"))
    if not all(isinstance(part, str) and part.strip() and len(part) <= 240 and "\n" not in part
               for part in (careful, spoken)):
        return None
    output = {"careful": careful, "spoken": spoken}
    emphasis = value.get("emphasis")
    if isinstance(emphasis, str) and emphasis.strip():
        first = spoken.find(emphasis)
        if first >= 0 and spoken.find(emphasis, first + 1) < 0:
            output["emphasis"] = emphasis
    return output


def numbered_lines(text):
    offset = 0
    for number, line in enumerate(text.split("\n"), 1):
        yield number, offset, line
        offset += len(line) + 1


def validate_batch(text, raw):
    """沿用现有单条校验。坏条目单独记录，保留其他可用条目。"""
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        raise StageError("模型响应不是完整的 JSON。") from None
    items = data.get("annotations") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise StageError("模型响应缺少 annotations 数组。")
    protocol = data.get("schema_version")
    if protocol is not None and protocol != LOCATION_SCHEMA:
        raise StageError("模型响应的 schema_version 不受支持。")
    annotations = []
    rejected = []
    seen = set()
    lines = {number: (offset, line) for number, offset, line in numbered_lines(text)}
    for index, item in enumerate(items):
        try:
            wrapped = json.dumps({"annotations": [item]}, ensure_ascii=False)
            number = item.get("line") if isinstance(item, dict) else None
            if isinstance(item, dict):
                if "token_ids" in item and number is None:
                    raise ModelError("token_ids 必须同时提供 line。")
                if protocol == LOCATION_SCHEMA and (number is None or not any(key in item for key in ("token_ids", "context"))):
                    raise ModelError("新定位协议必须提供 line 与 token_ids 或唯一 context。")
                if (protocol == LOCATION_SCHEMA and item.get("category") == "reduction"
                        and str(item.get("text", "")).lower().lstrip("'’") == "cause"
                        and item.get("expansion") != "because"):
                    raise ModelError("新协议的 Cause 缩读必须明确 expansion=because。")
            offset = 0
            segment = text
            if number is not None:
                if type(number) is not int or number not in lines or not lines[number][1].strip():
                    raise ModelError("line 不是有效的歌词行号。")
                offset, segment = lines[number]
            annotation, = validate_pronunciation(segment, wrapped, allow_causal_cause=True)["annotations"]
            if protocol == LOCATION_SCHEMA:
                if item.get("text") != annotation["text"]:
                    raise ModelError("新协议的 text 必须逐字保留原文大小写。")
                if any(key in item for key in ("start", "end")) and any(
                    type(item.get(key)) is not int or item[key] != annotation[key]
                    for key in ("start", "end")
                ):
                    raise ModelError("额外字符位置与原文计算的位置不一致。")
            annotation["start"] += offset
            annotation["end"] += offset
        except ModelError as error:
            rejected.append(f"第 {index + 1} 项：{error}")
            continue
        key = (annotation["start"], annotation["end"], annotation["category"])
        if key in seen:
            rejected.append(f"第 {index + 1} 项：类别和区间重复。")
            continue
        seen.add(key)
        ipa = optional_ipa(item.get("ipa"))
        if ipa:
            annotation["ipa"] = ipa
        annotations.append(annotation)
    return len(items), annotations, rejected


class Pipeline:
    def __init__(self, cache, api_key):
        self.cache = cache
        self.api_key = api_key
        self.model = None
        self.transcription_lock = Lock()
        self.analysis_lock = Lock()
        self.prompt = build_location_prompt(build_pronunciation_prompt(PILOT_02_VERSION) + IPA_INSTRUCTION)
        try:
            packages = "-".join(version(name) for name in ("faster-whisper", "ctranslate2", "av"))
        except PackageNotFoundError:
            packages = "missing"
        self.transcription_version = f"asr-v2:{MODEL_NAME}:{MODEL_REVISION}:{packages}:cpu-int8"
        components = (
            LOCATION_PROMPT_VERSION, self.prompt, os.environ.get("DEEPSEEK_MODEL", ""),
            os.environ.get("DEEPSEEK_BASE_URL", ""), CHUNK_SIZE, "lyrics-validation-v2",
        )
        self.analysis_version = "lyrics-ipa-v1:" + sha(json.dumps(components, ensure_ascii=False))[:16]

    def transcribe(self, audio, progress):
        audio_hash = sha(audio)
        reference_path = self.cache.directory / "references" / (audio_hash + ".json")
        progress("matching_lyrics", "正在检查是否有可用的参考歌词…", None)
        references = []
        for reader, value in ((embedded_reference, audio), (local_reference, reference_path)):
            try:
                references.append(reader(value))
            except (OSError, TypeError, ValueError, AttributeError) as error:
                stage_failure("matching_lyrics", error)
                references.append(None)
        key = "transcript:" + sha(self.transcription_version + ":" + audio_hash + ":" + repr(references))
        with self.transcription_lock:
            saved = self.cache.get(key)
            if saved is not None:
                return {**saved, "cache_hit": True, "elapsed_seconds": 0}

            started = time.perf_counter()
            progress("decoding_audio", "正在解码音频…", None)
            try:
                samples = decode_audio(io.BytesIO(audio), sampling_rate=16000)
                if not len(samples):
                    raise ValueError("No audio samples")
            except (OSError, RuntimeError, ValueError) as error:
                raise StageError("无法解码上传的音频。请确认 MP3 能正常播放。") from error

            progress("transcribing", "正在准备本地转写模型。首次使用可能需要下载。", None)
            try:
                from faster_whisper import WhisperModel
                if self.model is None:
                    self.model = WhisperModel(
                        MODEL_NAME, device="cpu", compute_type="int8", revision=MODEL_REVISION,
                        cpu_threads=min(6, os.cpu_count() or 1),
                        download_root=str(self.cache.directory / "models"),
                    )
                segments, info = self.model.transcribe(samples, **WHISPER_OPTIONS)
            except (ImportError, OSError, RuntimeError, ValueError) as error:
                raise StageError("无法开始本地转写。请检查 faster-whisper 和本地英文模型。") from error

            duration = float(info.duration)
            transcription_message = ("正在转写英文歌词…" if any(references)
                                     else "未找到参考歌词，正在本地转写英文歌词…")
            progress("transcribing", transcription_message, 0)
            lines = []
            recognized_words = []
            warning = None
            try:
                for segment in segments:
                    if segment.text.strip():
                        word_timestamps = getattr(segment, "words", None) or []
                        recognized_words.extend(
                            {"token": token, "start": item.start, "end": item.end,
                             "probability": item.probability}
                            for item in word_timestamps for token in words(item.word)
                        )
                        needs_review = bool(getattr(segment, "avg_logprob", 0) < -0.75 or (
                            bool(word_timestamps) and sum(item.probability for item in word_timestamps)
                            / len(word_timestamps) < 0.52
                        ))
                        lines.append({"text": segment.text.strip(),
                                      "start_seconds": round(float(segment.start), 3),
                                      "end_seconds": round(float(segment.end), 3),
                                      "needs_review": needs_review,
                                      "timing_method": "asr"})
                    if duration:
                        progress("transcribing", transcription_message, min(99, int(segment.end / duration * 100)))
            except Exception as error:
                warning = "转写中断。页面只显示中断前已得到的歌词。"
                if not lines:
                    raise StageError("本地转写中断，未生成可显示的歌词。") from error
                stage_failure("transcribing", error)
            if not lines:
                raise StageError("没有转写出歌词。请试试人声更清楚的英文录音。")
            source = "whisper"
            offset = None
            if not warning and any(references):
                progress("aligning", "正在核对参考歌词和音频时间…", None)
                aligner = None

                def force(text, begin, end, prefix, suffix):
                    nonlocal aligner
                    if aligner is None:
                        aligner = AudioAligner(self.model, audio)
                    return aligner(text, begin, end, prefix, suffix)

                for reference in filter(None, references):
                    try:
                        aligned = align_reference(reference, recognized_words, duration, force,
                                                  lambda _, message, percent: progress("aligning", message, percent))
                    except (OSError, RuntimeError, ValueError, IndexError) as error:
                        stage_failure("aligning", error)
                        continue
                    if aligned:
                        lines, offset = aligned
                        source = reference.source
                        break
            elapsed = round(time.perf_counter() - started, 2)
            result = {"segments": lines, "duration_seconds": round(duration, 3),
                      "version": self.transcription_version, "original_seconds": elapsed,
                      "status": "partial" if warning else "success", "warning": warning,
                      "lyric_source": source, "reference_offset": offset,
                      "reference_candidates": sum(item is not None for item in references)}
            if not warning:
                self.cache.remember(key, result)
            return {**result, "cache_hit": False, "elapsed_seconds": elapsed}

    def analysis_key(self, text):
        return sha(self.analysis_version + ":" + sha(text))

    def analyze(self, text, progress, *, retry=False, ipa_focus=None):
        key = self.analysis_key(text)
        if ipa_focus is not None:
            key = sha(f"{key}:{ipa_focus}:{EDIT_IPA_INSTRUCTION}")
        with self.analysis_lock:
            saved = self.cache.get("analysis:" + key)
            if saved is not None:
                return {**saved, "cache_hit": True}
            preview = self.cache.get("preview:" + key)
            if preview is not None and not retry:
                return {**preview, "cache_hit": False, "preview_reused": True}
            return self.analyze_uncached(text, progress, key, ipa_focus, preview)

    def analyze_uncached(self, text, progress, key, ipa_focus, preview=None):
        completed = {}
        truncated = []
        parts = []
        if preview:
            for row in preview["diagnostics"]["requests"]:
                start = row["start"]
                part = text[start:start + row["input"]["characters"]]
                if row.get("finish_reason") == "length" and len(part) > 70:
                    truncated.append(row)
                    parts.extend((start + offset, piece) for offset, piece in chunks(part, len(part) // 2 + 1))
                else:
                    parts.append((start, part))
                    if not row.get("error") and not row.get("rejected"):
                        completed[start] = row
        if not parts:
            parts = list(chunks(text))
        annotations = []
        requests = []
        diagnosed = []
        good_chunks = 0
        for number, (offset, part) in enumerate(parts, 1):
            progress("analyzing", f"正在分析发音（{number}/{len(parts)}）…", int((number - 1) * 100 / len(parts)))
            if offset in completed:
                requests.append(completed[offset])
                annotations.extend(item for item in preview["annotations"]
                                   if offset <= item["start"] and item["end"] <= offset + len(part))
                good_chunks += 1
                continue
            request = {"start": offset, "input": input_summary(part), "raw_count": None,
                       "validated_count": 0, "finish_reason": None,
                       "prompt_version": LOCATION_PROMPT_VERSION, "location_schema": LOCATION_SCHEMA}
            try:
                if not self.api_key:
                    raise StageError("转写可离线使用。生成发音标注需要在 .env 中配置 SINGLISH_API_KEY。")
                numbered = prepare_input(part)
                request["submitted"] = input_summary(numbered)
                prompt = self.prompt
                if ipa_focus is not None and offset <= ipa_focus < offset + len(part):
                    edited_line = part.count("\n", 0, ipa_focus - offset) + 1
                    prompt += EDIT_IPA_INSTRUCTION.format(line=edited_line)
                    request["ipa_focus_line"] = edited_line
                reply = request_deepseek(prompt, self.api_key, sentence=numbered)
                request["finish_reason"] = reply.finish_reason
                request["model"] = reply.model
                # 即使响应被截断，也尽可能记录可解析的原始条数。
                if reply.content:
                    try:
                        body = json.loads(reply.content)
                        if isinstance(body, dict) and isinstance(body.get("annotations"), list):
                            request["raw_count"] = len(body["annotations"])
                    except json.JSONDecodeError:
                        pass
                count, accepted, rejected = validate_batch(part, require_deepseek_content(reply))
                request["raw_count"] = count
                request["validated_count"] = len(accepted)
                for annotation in accepted:
                    annotations.append({**annotation, "start": annotation["start"] + offset,
                                        "end": annotation["end"] + offset})
                if not rejected or accepted:
                    good_chunks += 1
                if rejected:
                    diagnosed.extend(f"第 {number} 段{reason}" for reason in rejected)
                request["rejected"] = rejected
            except (StageError, ModelError) as error:
                request["error"] = str(error)
                diagnosed.append(f"第 {number} 段：{error}")
            requests.append(request)
        status = "success" if not diagnosed else ("partial" if good_chunks else "failed")
        # 完整结果和部分预览分开保存。合法空数组属于完整结果。
        result = {
            "input_text": text, "annotations": annotations, "status": status, "warnings": diagnosed,
            "diagnostics": {
                "input": input_summary(text), "prompt_version": LOCATION_PROMPT_VERSION,
                "analysis_version": self.analysis_version, "fallback": False, "requests": requests,
                "retried_truncated_requests": [item["start"] for item in truncated],
                "raw_count": (sum(req["raw_count"] for req in requests)
                              if all(req["raw_count"] is not None for req in requests) else None),
                "validated_count": len(annotations),
            },
        }
        if status == "success":
            self.cache.remember("analysis:" + key, result)
        elif status == "partial" and annotations:
            # 留下已通过的预览。同一文件重传时维持结果，用户仍可明确发起重试。
            self.cache.remember("preview:" + key, result)
        return {**result, "cache_hit": False}
