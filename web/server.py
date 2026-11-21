"""运行 Singlish 的本地歌词练习页面。"""

import argparse
import io
import json
import os
import re
import wave
from functools import partial
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv
from faster_whisper.audio import decode_audio

from src.analyzer import PROJECT_ROOT
from src.pronunciation import PILOT_02_VERSION
from web.jobs import Jobs, MAX_LYRICS, TERMINAL, analysis_counts
from web.ipa_display import display_annotation
from web.pipeline import Pipeline, ResultCache, StageError, input_summary, stage_failure, validate_batch

ASSETS = Path(__file__).resolve().parent
ROUTES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/assets/singlish.svg": ("assets/singlish.svg", "image/svg+xml"),
    "/assets/headphone-note.svg": ("assets/headphone-note.svg", "image/svg+xml"),
}
MAX_AUDIO = 30 * 1024 * 1024
MAX_JSON = 128 * 1024
JOB_PATH = re.compile(r"/api/jobs/([0-9a-f]{32})(?:/(correct|rendered|retry|timing))?")


def playable_audio(upload):
    """为浏览器无法直接解码的容器返回单声道试听音轨。"""
    try:
        samples = decode_audio(io.BytesIO(upload), sampling_rate=16000)
    except (OSError, RuntimeError, ValueError) as error:
        raise StageError("音频解码失败。") from error
    if not 0 < len(samples) <= 16000 * 60 * 30:
        raise StageError("试听转换支持 30 分钟以内的录音。")
    output = io.BytesIO()
    with wave.open(output, "wb") as track:
        track.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
        track.writeframes((samples.clip(-1, 1) * 32767).astype("<i2").tobytes())
    return output.getvalue()


def public_job(job):
    """浏览器只需要歌词、教学结果和简短的处理状态。"""
    public = {name: job[name] for name in ("id", "status", "progress", "message", "lines") if name in job}
    if analysis := job.get("analysis"):
        unlocated, other_errors = analysis_counts(analysis)
        lyric = job.get("input_text", "\n".join(row["text"] for row in job.get("lines", [])))
        annotations = [display_annotation(lyric, item) for item in job["review"]["annotations"]]
        public["analysis"] = {"status": analysis["status"], "unlocated_count": unlocated,
                              "has_other_errors": other_errors, "annotations": annotations}
    transcript = job.get("transcript")
    public["transcript_partial"] = bool(transcript and transcript["status"] == "partial")
    if transcript:
        public["lyric_source"] = transcript.get("lyric_source", "whisper")
        public["audio_duration"] = transcript["duration_seconds"]
    return public


def demo_analyzer():
    archive_path = PROJECT_ROOT / "experiments" / "pilot" / "deepseek_pronunciation_pilot_run_02.json"
    archive = json.loads(archive_path.read_text(encoding="utf-8"))
    responses = {row["input_text"]: row["raw_response"] for row in archive["results"]}

    def analyze(text, progress, *, retry=False, ipa_focus=None):
        raw = responses.get(text)
        if raw is None:
            raise StageError("离线回放仅支持已有例句。可粘贴 I'm gonna buy a better seat. 进行验证。")
        count, annotations, errors = validate_batch(text, raw)
        return {"annotations": annotations, "status": "partial" if errors else "success",
                "warnings": errors, "cache_hit": False, "diagnostics": {
                    "input": input_summary(text), "prompt_version": PILOT_02_VERSION,
                    "analysis_version": "archived_response", "fallback": False,
                    "requests": [], "raw_count": count, "validated_count": len(annotations),
                }}

    return analyze


class Handler(BaseHTTPRequestHandler):
    def __init__(self, *args, jobs, demo, **kwargs):
        self.jobs = jobs
        self.demo = demo
        super().__init__(*args, **kwargs)

    def respond(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def respond_json(self, status, data):
        self.respond(status, "application/json; charset=utf-8",
                     json.dumps(data, ensure_ascii=False).encode("utf-8"))

    def read_body(self, maximum, description):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if not 0 < length <= maximum:
            raise StageError(description)
        body = self.rfile.read(length)
        if len(body) != length:
            raise StageError("上传中断，请重新提交。")
        return body

    def read_json(self):
        if self.headers.get_content_type() != "application/json":
            raise StageError("请通过页面提交文本。")
        try:
            data = json.loads(self.read_body(MAX_JSON, "文本请求过长或为空。").decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError):
            raise StageError("无法读取提交的文本。") from None
        if not isinstance(data, dict):
            raise StageError("文本请求格式不正确。")
        return data

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in ROUTES:
            filename, content_type = ROUTES[path]
            self.respond(200, content_type, (ASSETS / filename).read_bytes())
        elif path == "/api/config":
            self.respond_json(200, {"demo": self.demo, "max_audio_bytes": MAX_AUDIO, "max_characters": MAX_LYRICS})
        else:
            match = JOB_PATH.fullmatch(path)
            job = self.jobs.get(match[1]) if match and not match[2] else None
            self.respond_json(200 if job else 404, public_job(job) if job else {"error": "找不到该任务，请重新提交。"})

    def do_POST(self):
        path = urlsplit(self.path).path
        stage = "upload_validation"
        try:
            if path in {"/api/jobs/audio", "/api/preview"}:
                if self.headers.get_content_type() not in {"audio/mpeg", "audio/mp3", "audio/mp4",
                                                           "application/octet-stream"}:
                    raise StageError("请选择 MP3 文件。")
                audio = self.read_body(MAX_AUDIO, "请选择不超过 30 MB 的非空 MP3。")
                if path == "/api/preview":
                    stage = "decoding_audio"
                    self.respond(200, "audio/wav", playable_audio(audio))
                    return
                # 以解码器识别的音轨为准，也兼容扩展名写作 MP3 的 AAC 封装。
                identifier = self.jobs.start(audio=audio)
            elif path == "/api/jobs/text":
                raw = self.read_json().get("text")
                if not isinstance(raw, str) or len(raw) > MAX_LYRICS or not raw.strip():
                    raise StageError(f"请输入 1–{MAX_LYRICS} 个字符的歌词。")
                lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
                segments = [{"text": line, "start_seconds": None, "end_seconds": None} for line in lines]
                identifier = self.jobs.start(segments=segments)
            else:
                match = JOB_PATH.fullmatch(path)
                job = self.jobs.get(match[1]) if match and match[2] else None
                if not job:
                    self.respond_json(404, {"error": "找不到该任务，请重新提交。"})
                    return
                payload = self.read_json()
                if match[2] == "timing":
                    index = payload.get("line")
                    if type(index) is not int:
                        raise StageError("请指定要对齐的歌词行。")
                    updated = self.jobs.save_timing(match[1], index, payload.get("start"), payload.get("end"))
                    self.respond_json(200, updated)
                    return
                if match[2] == "rendered":
                    count = payload.get("page_count")
                    ipa_count = payload.get("page_ipa_count")
                    if (type(count) is not int or not 0 <= count <= 100_000 or not job.get("analysis")
                            or type(ipa_count) is not int or not 0 <= ipa_count <= count):
                        raise StageError("页面标注计数无效。")
                    self.jobs.record_render(match[1], count, ipa_count)
                    self.respond_json(200, {"recorded": True})
                    return
                lines = job.get("lines", [])
                if match[2] == "retry":
                    if not lines or job.get("analysis", {}).get("status") not in {"partial", "failed"}:
                        raise StageError("该任务没有需要重试的发音分析。")
                    identifier = self.jobs.start(segments=lines, transcript=job.get("transcript"), retry_analysis=True)
                    self.respond_json(202, {"id": identifier})
                    return
                if "line" in payload:
                    index, new_text = payload["line"], payload.get("text")
                    if (job["status"] not in TERMINAL or type(index) is not int or not 0 <= index < len(lines)
                            or not isinstance(new_text, str) or not new_text.strip()
                            or "\n" in new_text or "\r" in new_text):
                        raise StageError("请输入一行非空歌词。")
                    old_line = lines[index]
                    if len(job["input_text"]) - len(old_line["text"]) + len(new_text) > MAX_LYRICS:
                        raise StageError("修改后歌词总长度不能超过 12000 字符。")
                    if new_text == old_line["text"]:
                        self.respond_json(202, {"id": match[1]})
                        return
                    segments = list(lines)
                    segments[index] = {**old_line, "text": new_text}
                    identifier = self.jobs.start(segments=segments, transcript=job.get("transcript"),
                                                 correction=(job.get("analysis"), old_line))
                    self.respond_json(202, {"id": identifier})
                    return
                texts = payload.get("texts")
                if not isinstance(texts, list) or len(texts) != len(lines) or not all(
                    isinstance(text, str) and "\n" not in text and "\r" not in text for text in texts
                ) or len("\n".join(texts)) > MAX_LYRICS or not any(text.strip() for text in texts):
                    raise StageError("请按原行修改歌词，保留至少一行，并确保总长度不超过 12000 字符。")
                segments = [{**line, "text": text} for line, text in zip(lines, texts)]
                identifier = self.jobs.start(segments=segments, transcript=job.get("transcript"))
        except StageError as error:
            if path in {"/api/jobs/audio", "/api/preview"}:
                stage_failure(stage, error)
            self.respond_json(400, {"error": str(error)})
        else:
            self.respond_json(202, {"id": identifier})


def main():
    parser = argparse.ArgumentParser(description="启动 Singlish 本地网页。")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--demo", action="store_true", help="离线回放 pilot-02 已保存的例句")
    args = parser.parse_args()
    if not args.demo:
        load_dotenv(PROJECT_ROOT / ".env", override=False, interpolate=False)
    pipeline = Pipeline(ResultCache(PROJECT_ROOT / ".singlish-cache"), os.environ.get("SINGLISH_API_KEY", "").strip())
    jobs = Jobs(pipeline, demo_analyzer() if args.demo else None)
    handler = partial(Handler, jobs=jobs, demo=args.demo)
    with ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
        print(f"Singlish http://127.0.0.1:{server.server_port}/", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
