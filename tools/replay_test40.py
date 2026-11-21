"""离线复现 55 条冻结参考下的原始评分和修复重放；不请求模型。"""

import argparse
import csv
import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch

from src.model_client import ModelError
from src.pronunciation import build_pronunciation_prompt, validate_pronunciation

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "experiments" / "test40"


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def annotation_keys(text, annotations):
    """用原文切片检查坐标；评分只比较区间和类别，不评分中文提示。"""
    keys = set()
    for item in annotations:
        start, end = item["start"], item["end"]
        assert type(start) is int and type(end) is int and 0 <= start < end <= len(text)
        assert text[start:end] == item["text"]
        key = (start, end, item["category"])
        assert key not in keys, "同类别、同区间重复"
        keys.add(key)
    return keys


def reproduce():
    inputs = read_jsonl(DIRECTORY / "singlish_test40_inputs.jsonl")
    reference_path = DIRECTORY / "singlish_test40_reference_frozen_v0.1.jsonl"
    reference = read_jsonl(reference_path)
    assert [(r["id"], r["input_text"]) for r in inputs] == [(r["id"], r["input_text"]) for r in reference]
    refs = {r["id"]: r for r in reference}
    assert len(refs) == len(inputs) == 40
    assert sum(len(r["annotations"]) for r in reference) == 55
    assert sum(not r["annotations"] for r in reference) == 3
    gold = {r["id"]: annotation_keys(r["input_text"], r["annotations"]) for r in reference}
    records = read_jsonl(DIRECTORY / "singlish_test40_run_01.jsonl")
    manifests = [r for r in records if r.get("record_type") == "manifest"]
    assert len(manifests) == 1
    manifest = manifests[0]
    assert sha(reference_path) == manifest["frozen_reference_sha256"]
    assert sha(DIRECTORY / "singlish_test40_inputs.jsonl") == manifest["inputs_sha256"]
    versions = sorted(manifest["prompt_sha256_by_version"])
    assert len(versions) == 2
    for version in versions:
        prompt_path = ROOT / "experiments" / "prompts" / (version + ".txt")
        assert sha(prompt_path) == manifest["prompt_sha256_by_version"][version]
        assert prompt_path.read_text(encoding="utf-8") == build_pronunciation_prompt(version)

    grouped = defaultdict(list)
    for record in records:
        if record.get("record_type") != "result":
            assert record.get("record_type") == "manifest"
            continue
        assert record["input_text"] == refs[record["id"]]["input_text"]
        assert record["prompt_version"] in versions
        grouped[record["prompt_version"]].append(record)
    assert all(len(grouped[v]) == len({r["id"] for r in grouped[v]}) == 40 for v in versions)

    detail = []
    for version in versions:
        for record in grouped[version]:
            # 原始阶段重新评分当时已保存的校验输出，不假装当前校验器是历史实现。
            # 同一条记录中仍保留原始响应、旧状态和旧错误，便于检查二者的关系。
            historical = record.get("validated_output")
            assert (historical is not None) == (record["status"] in {"valid_empty", "valid_nonempty"})
            if historical is not None:
                assert historical["input_text"] == record["input_text"]
                assert bool(historical["annotations"]) == (record["status"] == "valid_nonempty")
                raw_items = json.loads(record["raw_response"])["annotations"]
                assert len(raw_items) == len(historical["annotations"])
                for raw, kept in zip(raw_items, historical["annotations"]):
                    assert raw["text"] == kept["text"] and raw["category"] == kept["category"]
            try:
                # 修复阶段必须从相同的原始响应重新计算位置及证据校验，不能读取历史分数。
                replayed = validate_pronunciation(record["input_text"], record.get("raw_response"))
                replay_error = None
            except ModelError as error:
                replayed, replay_error = None, str(error)
            for phase, output, error in (
                ("original_evaluation", historical, record.get("error")),
                ("locator_replay_v0.2", replayed, replay_error),
            ):
                prediction = annotation_keys(record["input_text"], output["annotations"]) if output is not None else set()
                expected = gold[record["id"]]
                detail.append({"phase": phase, "prompt_version": version, "id": record["id"],
                               "source_type": refs[record["id"]]["source_type"], "passed": output is not None,
                               "valid_empty": output is not None and not prediction,
                               "TP": len(expected & prediction), "FP": len(prediction - expected),
                               "FN": len(expected - prediction), "error": error})

    rows = []
    with (ROOT / "experiments" / "main_results.csv").open(encoding="utf-8", newline="") as handle:
        expected_rows = {(r["phase"], r["prompt_version"], r["subset"]): r for r in csv.DictReader(handle)}
    assert len(expected_rows) == 12
    for phase in ("original_evaluation", "locator_replay_v0.2"):
        for version in versions:
            for subset in ("all", "daily_dialogue", "song_lyric"):
                selected = [r for r in detail if r["phase"] == phase and r["prompt_version"] == version
                            and (subset == "all" or r["source_type"] == subset)]
                tp, fp, fn = (sum(r[name] for r in selected) for name in ("TP", "FP", "FN"))
                result = {"phase": phase, "prompt_version": version, "subset": subset, "item_count": len(selected),
                          "reference_annotation_count": tp + fn, "predicted_label_count": tp + fp,
                          "TP": tp, "FP": fp, "FN": fn, "Precision": tp / (tp + fp) if tp + fp else 0,
                          "Recall": tp / (tp + fn) if tp + fn else 0,
                          "F1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0,
                          "validation_pass_count": sum(r["passed"] for r in selected),
                          "valid_empty_count": sum(r["valid_empty"] for r in selected)}
                stored = expected_rows[(phase, version, subset)]
                for name, value in result.items():
                    if isinstance(value, (int, float)):
                        assert math.isclose(value, float(stored[name]), rel_tol=0, abs_tol=1e-12), (name, value, stored[name])
                rows.append(result)
    return {"api_requests": 0, "reference_status": "preliminary_pending_human_review_original55",
            "question_count": 40, "reference_annotation_count": 55, "empty_reference_questions": 3,
            "saved_response_count": 80, "all_12_result_rows_match": True, "results": rows,
            "focus": [r for r in detail if r["id"] in {"test-019", "test-021"}]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="可选：另存完整重放结果；拒绝覆盖已有文件")
    args = parser.parse_args()
    # 本工具即便误加网络代码也应立即失败，不读取 .env、不请求 API。
    with patch("socket.socket.connect", side_effect=RuntimeError("离线复现禁止网络请求")), \
         patch("socket.create_connection", side_effect=RuntimeError("离线复现禁止网络请求")):
        report = reproduce()
    for row in report["results"]:
        print(f"{row['phase']} | {row['prompt_version']} | {row['subset']} | "
              f"TP={row['TP']} FP={row['FP']} FN={row['FN']} "
              f"P={row['Precision']:.6f} R={row['Recall']:.6f} F1={row['F1']:.6f} "
              f"通过={row['validation_pass_count']}/{row['item_count']}")
    print("12 行指标与 main_results.csv 一致；40 题、55 条参考、3 道空答案、80 条响应；API 请求 0 次。")
    if args.output:
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
            handle.write("\n")


if __name__ == "__main__":
    main()
