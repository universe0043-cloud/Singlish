"""按录音和歌词行应用已经登记的复核决定。"""

import json
import math

from web.pipeline import StageError


def read_review(directory, audio_hash):
    if not audio_hash:
        return {}
    path = directory / "reviews" / (audio_hash + ".json")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) and data.get("audio_sha256") == audio_hash else {}


def timing_update(line, start, end, duration, method):
    if (
        type(start) not in (int, float) or type(end) not in (int, float)
        or not all(map(math.isfinite, (start, end)))
        or not 0 <= start < end <= duration or end - start < 0.15
    ):
        raise StageError("请输入录音范围内的起止时间，片段至少 0.15 秒。")
    return {**line, "start_seconds": round(start, 3), "end_seconds": round(end, 3),
            "needs_review": False, "timing_method": method}


def apply_timings(segments, duration, confirmed, saved, pending=()):
    rows = list(segments)
    for entry in pending:
        index = entry["line"] - 1
        if (0 <= index < len(rows) and rows[index]["text"] == entry["line_text"] and rows[index].get("needs_review")):
            rows[index] = {**rows[index], "search_window": [entry["start"], entry["end"]],
                           "timing_note": entry.get("reason")}
    for edit in (*confirmed, *saved):
        index = edit["line"] - 1
        if 0 <= index < len(rows) and rows[index]["text"] == edit["line_text"]:
            rows[index] = timing_update(rows[index], edit["start"], edit["end"], duration,
                                        edit.get("method", "reviewed_audio"))
    return rows


