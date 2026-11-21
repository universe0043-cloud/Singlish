"""管理上传、转写、分析和纠错的任务状态。"""

import json
import logging
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from uuid import uuid4

from web.ipa import complete_annotations
from web.pipeline import StageError, input_summary, lyric_lines, sha, stage_failure
from web.review import apply_timings, read_review, timing_update

MAX_LYRICS = 12_000
TERMINAL = {"success", "partial", "failed"}
LOCATION_ERRORS = ("没有精确匹配", "在原文中重复出现", "位置与原文片段不一致",
                   "line 不是有效的歌词行号", "缺少非空的原文片段 text")


def analysis_counts(analysis):
    """从现有诊断提取页面所需的计数，兼容已缓存的请求记录。"""
    warnings = analysis.get("warnings", [])
    unlocated = sum(any(fragment in warning for fragment in LOCATION_ERRORS) for warning in warnings)
    return unlocated, len(warnings) > unlocated


def reanalyze_edit(analyze, previous, old_line, text, progress):
    """重分析覆盖旧行的请求区间，其他歌词的标注只平移坐标。"""
    diagnostics = previous["diagnostics"]
    requests = diagnostics["requests"]
    affected = [item for item in requests if item["start"] < old_line["end"]
                and item["start"] + item["input"]["characters"] > old_line["start"]]
    if not affected:
        return analyze(text, progress, ipa_focus=old_line["start"])
    start = affected[0]["start"]
    end = affected[-1]["start"] + affected[-1]["input"]["characters"]
    if start > old_line["start"] or end < old_line["end"]:
        return analyze(text, progress, ipa_focus=old_line["start"])

    delta = len(text) - diagnostics["input"]["characters"]
    fresh = analyze(text[start:end + delta], progress, ipa_focus=old_line["start"] - start)
    new_requests = [
        *[item for item in requests if item["start"] < start],
        *[{**item, "start": item["start"] + start} for item in fresh["diagnostics"]["requests"]],
        *[{**item, "start": item["start"] + delta} for item in requests if item["start"] >= end],
    ]
    annotations = [item for item in previous["annotations"] if item["end"] <= start]
    annotations.extend({**item, "start": item["start"] + start, "end": item["end"] + start}
                       for item in fresh["annotations"])
    annotations.extend({**item, "start": item["start"] + delta, "end": item["end"] + delta}
                       for item in previous["annotations"] if item["start"] >= end)

    warnings = []
    for number, item in enumerate(new_requests, 1):
        warnings.extend(f"第 {number} 段{reason}" for reason in item.get("rejected", []))
        if "error" in item:
            warnings.append(f"第 {number} 段：{item['error']}")
    successful = any("error" not in item and (not item.get("rejected") or item["validated_count"])
                     for item in new_requests)
    status = "success" if not warnings else ("partial" if successful else "failed")
    raw_counts = [item["raw_count"] for item in new_requests]
    return {"input_text": text, "annotations": annotations, "status": status, "warnings": warnings,
            "cache_hit": fresh["cache_hit"], "preview_reused": fresh.get("preview_reused", False),
            "diagnostics": {**diagnostics, "input": input_summary(text), "requests": new_requests,
                            "raw_count": None if None in raw_counts else sum(raw_counts),
                            "validated_count": len(annotations), "corrected_region": [start, end + delta]}}


class Jobs:
    def __init__(self, pipeline, analyze=None):
        self.pipeline = pipeline
        self.analyze = analyze or pipeline.analyze
        self.items = {}
        self.lock = Lock()
        self.workers = ThreadPoolExecutor(max_workers=2, thread_name_prefix="singlish")

    def get(self, identifier):
        with self.lock:
            item = self.items.get(identifier)
            return dict(item) if item else None

    def update(self, identifier, **values):
        with self.lock:
            self.items[identifier].update(values)

    def start(self, *, audio=None, segments=None, transcript=None, retry_analysis=False, correction=None):
        identifier = uuid4().hex
        with self.lock:
            if sum(job["status"] not in TERMINAL for job in self.items.values()) >= 6:
                raise StageError("当前分析队列已满，请等已有任务完成。")
            while len(self.items) >= 32:
                oldest = next(key for key, job in self.items.items() if job["status"] in TERMINAL)
                self.items.pop(oldest)
            self.items[identifier] = {"id": identifier, "status": "queued", "message": "已排队。",
                                      "progress": None}
        self.workers.submit(self.run, identifier, audio, segments, transcript, retry_analysis, correction)
        return identifier

    def run(self, identifier, audio, segments, transcript, retry_analysis, correction):
        stage = "queued"
        audio_hash = (transcript or {}).get("audio_sha256")

        def progress(status, message, percent):
            nonlocal stage
            stage = status
            self.update(identifier, status=status, message=message, progress=percent)

        try:
            if audio is not None:
                audio_hash = sha(audio)
                self.update(identifier, audio_sha256=audio_hash)
                transcript = self.pipeline.transcribe(audio, progress)
                transcript = {**transcript, "audio_sha256": audio_hash}
                segments = transcript["segments"]
            stage = "aligning" if audio_hash else "preparing_lyrics"
            if audio_hash:
                registered = read_review(self.pipeline.cache.directory, audio_hash)
                saved = self.pipeline.cache.get("timings:" + audio_hash) or []
                segments = apply_timings(segments, transcript["duration_seconds"], registered.get("timings", []),
                                         saved, registered.get("time_pending", []))
            text, lines = lyric_lines(segments)
            self.update(identifier, input_text=text, lines=lines, transcript=transcript)
            progress("analyzing", "歌词已就绪，正在分析发音…", 0)
        except Exception as error:
            failure = stage_failure(stage, error)
            hints = {"matching_lyrics": "未能读取参考歌词。", "decoding_audio": "未能解码音频。",
                     "transcribing": "本地转写未能完成。", "aligning": "未能整理歌词时间。"}
            message = str(error) if isinstance(error, StageError) else hints.get(stage, "未能整理歌词。")
            self.update(identifier, status="failed", message=message, progress=None, failure=failure, stage=stage)
            self.log_analysis(identifier)
            return

        failure = None
        try:
            if not text.strip() or len(text) > MAX_LYRICS:
                raise StageError(f"请将歌词纠错为 1–{MAX_LYRICS} 个字符后再分析。")
            if correction and correction[0]:
                previous, old_line = correction
                result = reanalyze_edit(self.analyze, previous, old_line, text, progress)
            else:
                result = self.analyze(text, progress, retry=retry_analysis)
        except Exception as error:
            failure = stage_failure("analyzing", error)
            warning = str(error) if isinstance(error, StageError) else "发音分析中断。"
            result = {"status": "failed", "annotations": [], "warnings": [warning],
                      "diagnostics": {"input": input_summary(text), "requests": []}}
        try:
            review = complete_annotations(text, result["annotations"])
        except Exception as error:
            failure = stage_failure("validating_pronunciation", error)
            result = {**result, "status": "failed", "warnings": [*result["warnings"], "发音校验中断。"]}
            review = {"annotations": []}
        status = result["status"]
        if status == "failed" or (transcript and transcript["status"] == "partial"):
            status = "partial" if transcript or review["annotations"] else status
        message = "歌词已保留，发音分析未完成。" if result["status"] == "failed" else "分析完成。"
        self.update(identifier, status=status, message=message, progress=100, analysis=result, review=review,
                    failure=failure, stage=failure["stage"] if failure else stage)
        self.log_analysis(identifier)

    def save_timing(self, identifier, index, start, end):
        with self.lock:
            job = self.items.get(identifier)
            transcript = (job or {}).get("transcript") or {}
            audio_hash = transcript.get("audio_sha256")
            if not audio_hash or job["status"] not in TERMINAL or not 0 <= index < len(job["lines"]):
                raise StageError("找不到这行歌词的音频。请重传歌曲。")
            lines = list(job["lines"])
            updated = timing_update(lines[index], start, end, transcript["duration_seconds"], "manual")
            before = next((row for row in reversed(lines[:index]) if not row.get("needs_review")
                           and row["end_seconds"] is not None), None)
            after = next((row for row in lines[index + 1:] if not row.get("needs_review")
                          and row["start_seconds"] is not None), None)
            if ((before and start + 0.45 < before["end_seconds"])
                    or (after and end > after["start_seconds"] + 0.45)):
                raise StageError("这个范围和相邻已对齐歌词重叠。请缩短试听范围后再保存。")
            key = "timings:" + audio_hash
            saved = self.pipeline.cache.get(key) or []
            saved = [entry for entry in saved if (entry["line"], entry["line_text"]) != (index + 1, updated["text"])]
            saved.append({"line": index + 1, "line_text": updated["text"], "start": updated["start_seconds"],
                          "end": updated["end_seconds"], "method": "manual"})
            self.pipeline.cache.put(key, saved)
            lines[index] = updated
            job["lines"] = lines
            return updated

    def record_render(self, identifier, page_count, page_ipa_count):
        with self.lock:
            job = self.items.get(identifier)
            if not job or not job.get("analysis"):
                return
            job["page_count"] = page_count
        self.log_analysis(identifier, page_count, page_ipa_count)

    def log_analysis(self, identifier, page_count=None, page_ipa_count=None):
        job = self.get(identifier)
        if not job:
            return
        analysis = job.get("analysis", {})
        review = job.get("review", {})
        audit = review.get("audit", [])
        counts = Counter(record["status"] for record in audit)
        transcript = job.get("transcript") or {}
        trace = {"job": identifier, "status": job["status"], "stage": job.get("stage"),
                 "failure": job.get("failure"), "audio_sha256": transcript.get("audio_sha256", job.get("audio_sha256")),
                 "reference_candidates": transcript.get("reference_candidates"),
                 "cache_hit": analysis.get("cache_hit", False),
                 "preview_reused": analysis.get("preview_reused", False),
                 **analysis.get("diagnostics", {}), "page_count": page_count,
                 "page_ipa_count": page_ipa_count,
                 "valid_ipa_count": len(review.get("annotations", [])),
                 "ipa_auto_filled_count": sum(item.get("auto_filled", False) for item in audit),
                 "rule_supplement_count": len(review.get("supplements", [])),
                 "ipa_pending_count": counts["pending"],
                 "ipa_removed_count": counts["removed"],
                 "ipa_reclassified_count": counts["reclassified"],
                 "ipa_reason_counts": dict(Counter(item["code"] for item in audit)),
                 "warnings": analysis.get("warnings", []),
                 "transcript_warning": transcript.get("warning"),
                 "lyric_source": transcript.get("lyric_source"),
                 "transcript_cache_hit": transcript.get("cache_hit"),
                 "transcript_seconds": transcript.get("original_seconds"),
                 "review_line_count": sum(line.get("needs_review", False) for line in job.get("lines", []))}
        if not analysis:
            trace["error"] = job["message"]
        try:
            with self.lock, (self.pipeline.cache.directory / "analysis-trace.jsonl").open(
                "a", encoding="utf-8"
            ) as file:
                file.write(json.dumps(trace, ensure_ascii=False) + "\n")
        except OSError:
            logging.warning("Could not write Singlish analysis trace for %s", identifier)
