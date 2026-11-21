"""调用 DeepSeek，并将模型输出校验为项目通用的分析结构。"""

import json
import os
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

from openai import APIConnectionError, APIError, APIStatusError, APITimeoutError, DefaultHttpxClient, OpenAI

if __package__:
    from .analyzer import SOUND_SECTIONS, TEXT_SECTIONS, check_sentence, mark_pronunciation, new_result
else:
    from analyzer import SOUND_SECTIONS, TEXT_SECTIONS, check_sentence, mark_pronunciation, new_result


class ModelError(ValueError):
    """可以安全展示给用户的模型错误。"""


@dataclass(frozen=True)
class DeepSeekReply:
    content: str | None
    model: str | None
    finish_reason: str | None


def request_deepseek(prompt: str, api_key: str, *, sentence: str | None = None) -> DeepSeekReply:
    """发送一次请求。提供 sentence 时，将规则和待分析原句放在不同消息中。"""
    base_url = os.environ.get("DEEPSEEK_BASE_URL", "").strip()
    model = os.environ.get("DEEPSEEK_MODEL", "").strip()
    if not base_url or not model:
        raise ModelError("请在 .env 或进程环境中设置 DEEPSEEK_BASE_URL 和 DEEPSEEK_MODEL。")

    try:
        url = urlsplit(base_url)
        valid_url = (
            url.scheme == "https" and url.hostname and url.username is None
            and not url.query and not url.fragment
            and (url.port is None or 0 < url.port <= 65535)
        )
    except ValueError:
        valid_url = False
    if not valid_url:
        raise ModelError("DEEPSEEK_BASE_URL 必须是有效的 HTTPS 服务地址。")

    messages = [{"role": "user", "content": prompt}]
    client_options = {}
    if sentence is not None:
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": sentence},
        ]
        # 试跑每句只有一次请求，服务地址发生重定向时直接报错。
        client_options["http_client"] = DefaultHttpxClient(follow_redirects=False)

    try:
        # 禁止自动重试，避免同一次分析产生额外请求。
        with OpenAI(api_key=api_key, base_url=base_url, timeout=30.0, max_retries=0, **client_options) as client:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                response_format={"type": "json_object"},
                extra_body={"thinking": {"type": "disabled"}},
                max_tokens=2000,
                stream=False,
            )
    except APITimeoutError:
        raise ModelError("DeepSeek 请求超时。") from None
    except APIConnectionError:
        raise ModelError("无法连接 DeepSeek，请检查网络。") from None
    except APIStatusError as error:
        # 只展示固定文本和 HTTP 状态，避免输出服务返回的原始错误正文。
        status = error.status_code
        if status == 401:
            raise ModelError("DeepSeek 认证失败，请检查 SINGLISH_API_KEY。") from None
        if status == 403:
            raise ModelError("DeepSeek 拒绝访问，请检查账户或模型权限。") from None
        if status == 402:
            raise ModelError("DeepSeek 账户余额不足或可用额度已用尽。") from None
        if status == 429:
            raise ModelError("DeepSeek 请求频率或额度受限。") from None
        raise ModelError(f"DeepSeek 返回 API 错误（HTTP {status}）。") from None
    except APIError:
        raise ModelError("DeepSeek 返回了无法处理的 API 响应。") from None

    choices = getattr(response, "choices", None)
    if not choices:
        raise ModelError("DeepSeek 响应中没有可用的分析结果。")
    choice = choices[0]
    return DeepSeekReply(
        content=getattr(getattr(choice, "message", None), "content", None),
        model=getattr(response, "model", None),
        finish_reason=getattr(choice, "finish_reason", None),
    )


def require_deepseek_content(reply: DeepSeekReply) -> str:
    """校验结束状态和正文。试跑可以在校验前记录服务器返回的原文。"""
    if reply.finish_reason != "stop":
        raise ModelError("DeepSeek 分析未正常完成，可能是内容被截断或过滤。")
    content = reply.content
    if not isinstance(content, str) or not content.strip():
        raise ModelError("DeepSeek 返回的分析内容为空或格式无效。")
    return content


def call_deepseek(prompt: str, api_key: str) -> str:
    """保留词汇和语法分析使用的原有调用入口。"""
    return require_deepseek_content(request_deepseek(prompt, api_key))


def analyze_with_model(
    sentence: str,
    call_model: Callable[[str, str], str] | None = None,
) -> dict:
    """默认调用 DeepSeek，传入本地函数时可模拟模型响应。"""
    check_sentence(sentence)
    api_key = os.environ.get("SINGLISH_API_KEY", "").strip()
    if not api_key:
        raise ModelError("请在 .env 或进程环境中设置 SINGLISH_API_KEY。")
    if call_model is None:
        call_model = call_deepseek

    result = new_result(sentence, "configured_model")
    prompt = (
        "分析下面 JSON 的 input_text，作为英文学习材料。只返回 JSON 对象。"
        "按模板填写 vocabulary、grammar、reduction、weak_forms、linking 和 speaking_tips。"
        "每项标注都包含 text 和 explanation_zh。省略 start 和 end，由程序计算。\n"
        "text 必须逐字复制 input_text 中的一段连续原文，保留大小写、空格和标点。"
        "不得改写、纠正或规范化 text。\n"
        "如果 text 在 input_text 中出现多次，加上 context 指明要标注的那一次。"
        "context 必须逐字复制原文中的一段连续文本，在 input_text 中只出现一次，"
        "并且只包含一次 text。text 只出现一次时，可省略 context。\n"
        "例如，input_text 为 \"Sing softly, then Sing loudly.\"，"
        "标注第二个 Sing 时返回 "
        "{\"text\": \"Sing\", \"context\": \"Sing loudly\", \"explanation_zh\": \"唱歌。\"}。\n"
        "缩读只标记文本中已出现的非正式缩读拼写，evidence 用 text_observed。"
        "弱读和连读仅为文本候选，evidence 用 text_candidate。"
        "三个发音类别都必须提供 condition_zh，说明出现条件或文本证据。"
        "输入只包含文本。即使能在文本中观察到缩读拼写，实际发音也需要音频证据。"
        "三个发音类别的 actual_pronunciation 都必须返回字符串 uncertain。"
        "解释和口语建议只能给出可能的发音及条件，不得断言实际发音或唱法。"
        "speaking_tips 是中文字符串列表。没有可靠标注时使用空列表。\n"
        + json.dumps(result, ensure_ascii=False)
    )
    try:
        raw_result = json.loads(call_model(prompt, api_key))
    except (json.JSONDecodeError, TypeError):
        raise ModelError("模型返回的内容不是有效的 JSON。") from None
    except ModelError:
        raise
    except ValueError:
        # SDK 也可能在处理服务端响应时报告无效数据。
        raise ModelError("模型调用或响应解析失败，请检查服务地址与配置。") from None
    if not isinstance(raw_result, dict):
        raise ModelError("模型必须返回 JSON 对象。")

    # 根据原文生成位置，再校验并整理公开的标注字段。
    for section in TEXT_SECTIONS + SOUND_SECTIONS:
        items = raw_result.get(section)
        if not isinstance(items, list):
            raise ModelError(f"模型字段 {section} 必须是列表。")
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise ModelError(f"{section} 中的标注必须是对象。")
            try:
                start, end = locate_span(sentence, item)
            except ModelError as error:
                log_span_error(sentence, section, {"text": item.get("text")}, index, in_bounds=False)
                raise ModelError(f"{section}[{index}] {error}") from None
            located_item = {**item, "start": start, "end": end}
            result[section].append(check_item(sentence, section, located_item, item_index=index))

    tips = raw_result.get("speaking_tips")
    if not isinstance(tips, list) or not all(isinstance(tip, str) and tip.strip() for tip in tips):
        raise ModelError("speaking_tips 必须是非空字符串组成的列表。")
    result["speaking_tips"] = tips
    return result


def locate_span(sentence: str, item: dict, *, allow_case_mismatch: bool = False) -> tuple[int, int]:
    """查找完整词或词组，优先精确匹配，返回左闭右开的原文位置。"""
    if "token_ids" in item:
        if __package__:
            from .pronunciation_locations import locate_tokens
        else:
            from pronunciation_locations import locate_tokens
        return locate_tokens(sentence, item)
    text = item.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ModelError("缺少非空的原文片段 text。")

    # 词内撇号属于词的一部分，成对引号仍可作为边界。前瞻保留重叠匹配。
    pattern = rf"(?<!\w)(?<!\w['’])(?={re.escape(text)}(?!\w|['’]\w))"
    positions = [match.start() for match in re.finditer(pattern, sentence)]
    if not positions and allow_case_mismatch:
        # 用原文下标查找，只接受大小写差异，保留原来的词边界和消歧逻辑。
        lower_text = text.lower()
        for match in re.finditer(pattern, sentence, re.IGNORECASE):
            start = match.start()
            if sentence[start:start + len(text)].lower() == lower_text:
                positions.append(start)
    if not positions:
        raise ModelError("text 在原文中没有精确匹配的完整词或词组。")
    if len(positions) > 1:
        context = item.get("context")
        if not isinstance(context, str) or not context.strip():
            raise ModelError("text 在原文中重复出现，需要唯一的原文 context。")

        context_start = sentence.find(context)
        if context_start == -1 or sentence.find(context, context_start + 1) != -1:
            raise ModelError("text 在原文中重复出现，提供的 context 无法唯一定位。")
        context_end = context_start + len(context)
        positions = [
            start for start in positions
            if context_start <= start and start + len(text) <= context_end
        ]
        if len(positions) != 1:
            raise ModelError("text 在原文中重复出现，提供的 context 无法唯一定位。")

    start = positions[0]
    # 即使 text 唯一，也不能忽略模型另外提供的错误上下文。
    if "context" in item:
        if __package__:
            from .pronunciation_locations import check_context
        else:
            from pronunciation_locations import check_context
        check_context(sentence, item, start, start + len(text))
    return start, start + len(text)


def log_span_error(
    sentence: str, section: str, item: dict, item_index: int | None, *, in_bounds: bool
) -> None:
    """按需输出有问题的片段，保留空格和其他字符差异。"""
    if os.environ.get("SINGLISH_DEBUG_SPANS") != "1":
        return

    start = item.get("start")
    end = item.get("end")
    value = item.get("text")
    text = value if isinstance(value, str) else "<非字符串或缺失>"
    secret = os.environ.get("SINGLISH_API_KEY", "").strip()
    if secret:
        text = text.replace(secret, "[REDACTED]")
        # 先遮盖再切片。等长遮盖保留原位置，也能遮盖跨过片段边界的密钥。
        sentence = sentence.replace(secret, "*" * len(secret))

    details = {
        "field": f"{section}[{item_index}]" if item_index is not None else section,
        "text": text[:160],
        "start": start if type(start) is int else None,
        "end": end if type(end) is int else None,
        "original_slice": sentence[start:min(end, start + 160)] if in_bounds else None,
    }
    # 转义换行和特殊字符，保证每条诊断只占一行，不影响标准输出的 JSON。
    print("[span-debug] " + json.dumps(details, ensure_ascii=True), file=sys.stderr)


def check_item(
    sentence: str, section: str, item: dict, *, item_index: int | None = None
) -> dict:
    if not isinstance(item, dict):
        raise ModelError(f"{section} 中的标注必须是对象。")
    start = item.get("start")
    end = item.get("end")
    if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(sentence):
        log_span_error(sentence, section, item, item_index, in_bounds=False)
        raise ModelError(f"{section} 中的字符位置无效。")
    if item.get("text") != sentence[start:end]:
        log_span_error(sentence, section, item, item_index, in_bounds=True)
        raise ModelError(f"{section} 中的 text 与原文位置不一致。")
    explanation = item.get("explanation_zh")
    if not isinstance(explanation, str) or not explanation.strip():
        raise ModelError(f"{section} 中缺少中文解释。")

    checked = {"text": item["text"], "start": start, "end": end, "explanation_zh": explanation}
    if section in SOUND_SECTIONS:
        condition = item.get("condition_zh")
        if not isinstance(condition, str) or not condition.strip():
            raise ModelError(f"{section} 中缺少成立条件。")
        pronunciation = item.get("actual_pronunciation")
        if not isinstance(pronunciation, str) or not pronunciation.strip():
            raise ModelError(f"{section} 的 actual_pronunciation 必须是非空字符串。")
        # 字段格式仍需校验。发音状态由程序根据输入只有文本这一事实确定。
        evidence = "text_observed" if section == "reduction" else "text_candidate"
        return mark_pronunciation(checked, evidence, condition)
    return checked
