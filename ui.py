import json
import os
import re
import sys
import threading
import traceback
import webbrowser
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from pathlib import Path
from urllib.parse import urlparse


HOST = "127.0.0.1"
PORT = 7860
OUTPUT_DIR = "generated_mini_program"
MAX_LOG_CHARS = 200_000
DEFAULT_LLM_API_BASE = "https://api.deepseek.com"
DEFAULT_LLM_MODEL = "deepseek-v4-pro"

PROJECT_ROOT = Path(__file__).resolve().parent
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
os.environ.setdefault("CREWAI_STORAGE_DIR", str(PROJECT_ROOT / ".crew_state" / "crewai"))
os.environ["LOCALAPPDATA"] = str(PROJECT_ROOT / ".crew_state" / "localappdata")
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("CREWAI_DISABLE_TRACKING", "true")

ANSI_ESCAPE_RE = re.compile(
    r"(?:\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07]*(?:\x07|\x1b\\))"
)
CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
MOJIBAKE_MARKERS = ("Ã", "Â", "â", "ä", "å", "æ", "ç", "è", "é", "ï¼", "涓", "鎴", "绛", "宸", "鐢")
PROGRESS_RULES = [
    ("quality", re.compile(r"==== 质量档位：(.+?) ===="), lambda m: f"进度：已采用 {m.group(1)} 配置，开始生成。"),
    ("stage1", re.compile(r"==== Stage 1：开始"), lambda m: "进度：开始需求分析。"),
    ("stage1done", re.compile(r"==== 需求分析完成 ===="), lambda m: "进度：需求分析完成。"),
    ("stage2", re.compile(r"==== Stage 2：开始架构设计 ===="), lambda m: "进度：开始架构设计。"),
    ("stage2done", re.compile(r"==== 架构设计完成 ===="), lambda m: "进度：架构设计完成。"),
    ("stage3", re.compile(r"==== Stage 3：生成文件清单 ===="), lambda m: "进度：开始生成文件清单。"),
    ("fileplan", re.compile(r"==== 文件清单获取完成"), lambda m: "进度：文件清单已完成并通过轻度整理。"),
    ("stage35", re.compile(r"==== Stage 3\.5："), lambda m: "进度：开始整理代码生成上下文。"),
    ("contextdone", re.compile(r"==== 代码生成上下文压缩完成 ===="), lambda m: "进度：代码生成上下文已整理完成。"),
    ("templates", re.compile(r"已生成固定模板: app\.json / app\.js / app\.wxss"), lambda m: "进度：全局 app 模板已生成。"),
    ("stage5", re.compile(r"==== Stage 5：开始页面四件套成组生成 ===="), lambda m: "进度：开始按页面四件套生成代码。"),
    ("stage6", re.compile(r"==== Stage 6：生成组件和非页面文件 ===="), lambda m: "进度：开始生成组件和非页面文件。"),
    ("validation_retry", re.compile(r"上一轮生成未通过一致性校验|页面生成失败:"), lambda m: "进度：发现一致性问题，正在把错误反馈给模型重试。"),
    ("done", re.compile(r"\[DONE\] 项目生成完成"), lambda m: "进度：项目生成流程完成。"),
]
PAGE_PROGRESS_RE = re.compile(r"正在生成页面四件套:\s*([^\s(]+)")

INITIAL_ASSISTANT_MESSAGE = (
    "你好，我是 WeCraft AI。你可以先粗略说想做什么小程序，"
    "我会和你一起梳理需求、补齐关键细节，最后整理出一份可直接用于生成代码的完整方案。"
)

REQUIREMENT_CHAT_SYSTEM = """
你是一位资深微信小程序产品经理和需求分析师，正在通过 Web UI 与用户多轮交流。

你的目标：
1. 通过自然对话理解用户真实需求，不要用固定模板机械追问。
2. 每轮先简短总结你当前理解，再提出最有价值的 2~4 个追问。
3. 追问要聚焦能影响代码生成的内容：用户角色、核心场景、页面结构、数据模型、权限、数据来源、技术限制、边界流程。
4. 当信息已经足够，或用户表达“可以了/按你理解/开始生成/生成方案/直接做”等意图时，输出一份完整生成方案。
5. 不要生成代码，不要讨论无关商业背景。

你必须只返回 JSON，不要 markdown，不要解释 JSON 外的文字：
{
  "status": "ask" 或 "plan",
  "reply": "给用户看的自然语言回复。ask 时包含当前理解和追问；plan 时说明方案已整理完成。",
  "plan": "status=plan 时填写完整方案；status=ask 时为空字符串"
}

完整方案必须包含：
- 项目目标
- 用户角色
- 核心功能模块
- 页面结构与跳转
- 关键数据模型字段
- 权限与业务规则
- 技术实现建议
- 仍需默认假设的事项
"""

job_lock = threading.Lock()
job_state = {
    "running": False,
    "status": "idle",
    "message": "准备就绪",
    "logs": "",
    "output_dir": OUTPUT_DIR,
    "quality": "balanced",
    "progress_keys": [],
    "conversation": [{"role": "assistant", "text": INITIAL_ASSISTANT_MESSAGE}],
    "draft_requirement": "",
    "plan_text": "",
    "ready_to_generate": False,
}


class LogBuffer(StringIO):
    def write(self, text):
        append_log(text)
        return super().write(text)


def set_state(**kwargs):
    with job_lock:
        job_state.update(kwargs)


def _mojibake_score(text):
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    markers = sum(text.count(marker) for marker in MOJIBAKE_MARKERS)
    replacements = text.count("\ufffd")
    return cjk * 2 - markers * 3 - replacements * 5


def repair_mojibake(text):
    if not any(marker in text for marker in MOJIBAKE_MARKERS):
        return text

    best = text
    best_score = _mojibake_score(text)
    for encoding in ("cp1252", "latin1", "gbk"):
        try:
            candidate = text.encode(encoding).decode("utf-8")
        except UnicodeError:
            continue
        score = _mojibake_score(candidate)
        if score > best_score:
            best = candidate
            best_score = score
    return best


def clean_log_text(text):
    text = repair_mojibake(str(text))
    text = ANSI_ESCAPE_RE.sub("", text)
    text = CONTROL_CHAR_RE.sub("", text)
    return text.replace("\r\n", "\n").replace("\r", "\n")


def append_log(text):
    cleaned = clean_log_text(text)
    if not cleaned:
        return
    with job_lock:
        job_state["logs"] = (job_state["logs"] + cleaned)[-MAX_LOG_CHARS:]
        append_progress_from_log_unlocked(cleaned)


def append_progress_message_unlocked(key, text):
    progress_keys = job_state.setdefault("progress_keys", [])
    if key in progress_keys:
        return
    progress_keys.append(key)
    job_state["conversation"].append({"role": "assistant", "text": text})


def append_progress_from_log_unlocked(log_text):
    for key, pattern, formatter in PROGRESS_RULES:
        match = pattern.search(log_text)
        if match:
            append_progress_message_unlocked(key, formatter(match))

    for match in PAGE_PROGRESS_RE.finditer(log_text):
        page_dir = match.group(1)
        append_progress_message_unlocked(
            f"page:{page_dir}", f"进度：正在生成页面 {page_dir}。"
        )


def compile_requirement_unlocked():
    user_messages = [
        item["text"].strip()
        for item in job_state["conversation"]
        if item.get("role") == "user" and item.get("text", "").strip()
    ]
    return "\n\n".join(
        f"第 {idx} 轮补充：\n{text}" for idx, text in enumerate(user_messages, start=1)
    ).strip()


def update_requirement_state_unlocked():
    draft = compile_requirement_unlocked()
    job_state["draft_requirement"] = draft
    job_state["ready_to_generate"] = bool(job_state.get("plan_text"))
    return draft


def parse_ai_json(text):
    raw = str(text).strip()
    if raw.startswith("```"):
        raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            return json.loads(raw[start : end + 1])
        raise


def get_requirement_llm():
    """Use main.py's JSON LLM so UI startup follows the same provider adapter."""
    try:
        from main import llm_json as generation_llm
    except Exception as exc:
        append_log(f"\n[WARN] 无法读取 main.py 中的大模型配置，使用 UI 默认配置：{exc}\n")
        from crewai.llm import LLM

        generation_llm = LLM(
            model=DEFAULT_LLM_MODEL,
            api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            api_base=DEFAULT_LLM_API_BASE,
            temperature=0.0,
            max_tokens=5000,
            timeout=180,
            response_format={"type": "json_object"},
        )

    model = os.getenv("DEEPSEEK_MODEL")
    api_base = os.getenv("DEEPSEEK_API_BASE")
    api_key = os.getenv("DEEPSEEK_API_KEY")

    if not any((model, api_base, api_key)):
        return generation_llm

    from crewai.llm import LLM

    return LLM(
        model=model or getattr(generation_llm, "model", None) or DEFAULT_LLM_MODEL,
        api_key=api_key or getattr(generation_llm, "api_key", None) or "",
        api_base=api_base
        or getattr(generation_llm, "api_base", None)
        or DEFAULT_LLM_API_BASE,
        temperature=getattr(generation_llm, "temperature", 0.0),
        max_tokens=getattr(generation_llm, "max_tokens", None) or 5000,
        timeout=getattr(generation_llm, "timeout", None) or 180,
        response_format=getattr(generation_llm, "response_format", None)
        or {"type": "json_object"},
    )


def call_requirement_ai(conversation, force_plan=False):
    requirement_llm = get_requirement_llm()
    api_key = getattr(requirement_llm, "api_key", None)
    if not api_key:
        raise RuntimeError("未找到可用的大模型 API Key，请检查 main.py 的 llm 配置或 DEEPSEEK_API_KEY。")

    messages = [{"role": "system", "content": REQUIREMENT_CHAT_SYSTEM}]
    for item in conversation:
        role = item.get("role")
        text = item.get("text", "").strip()
        if not text:
            continue
        if role == "user":
            messages.append({"role": "user", "content": text})
        elif role == "assistant":
            messages.append({"role": "assistant", "content": text})

    if force_plan:
        messages.append(
            {
                "role": "user",
                "content": "请基于目前全部对话，整理完整生成方案。如果仍有缺失，请给出合理默认假设，不要继续追问。",
            }
        )

    try:
        content = requirement_llm.call(messages)
    except Exception as exc:
        raise RuntimeError(f"AI 需求对话请求失败：{exc}") from exc

    if not isinstance(content, str):
        content = (
            getattr(content, "raw", None)
            or getattr(content, "content", None)
            or str(content)
        )
    result = parse_ai_json(content)
    status = str(result.get("status", "ask")).strip().lower()
    reply = str(result.get("reply", "")).strip()
    plan = str(result.get("plan", "")).strip()
    if status not in {"ask", "plan"}:
        status = "ask"
    if status == "plan" and not plan:
        plan = reply
    if not reply:
        reply = "我已经根据当前对话更新了需求理解。"
    return {"status": status, "reply": reply, "plan": plan}


def add_chat_message(role, text):
    text = str(text).strip()
    if not text:
        return None
    with job_lock:
        item = {"role": role, "text": text}
        job_state["conversation"].append(item)
        update_requirement_state_unlocked()
        return item


def handle_user_chat(text):
    text = str(text).strip()
    if not text:
        return {"ok": False, "message": "请输入要补充的需求。"}

    with job_lock:
        job_state["plan_text"] = ""
        job_state["ready_to_generate"] = False
        job_state["conversation"].append({"role": "user", "text": text})
        update_requirement_state_unlocked()
        conversation = list(job_state["conversation"])

    try:
        ai_result = call_requirement_ai(conversation)
        reply = ai_result["reply"]
    except Exception as exc:
        reply = f"AI 需求对话暂时不可用：{exc}"
        ai_result = {"status": "ask", "reply": reply, "plan": ""}

    with job_lock:
        if ai_result["status"] == "plan":
            job_state["plan_text"] = ai_result["plan"]
            job_state["ready_to_generate"] = True
            reply = f"{reply}\n\n{ai_result['plan']}"
        else:
            job_state["ready_to_generate"] = False
        job_state["conversation"].append({"role": "assistant", "text": reply})
        update_requirement_state_unlocked()
        return {
            "ok": True,
            "reply": reply,
            "conversation": list(job_state["conversation"]),
            "draft_requirement": job_state["draft_requirement"],
            "plan_text": job_state["plan_text"],
            "ready_to_generate": job_state["ready_to_generate"],
        }


def run_job(requirement, quality):
    set_state(
        running=True,
        status="running",
        message=f"正在生成微信小程序（{quality} 档），请保持此窗口打开。",
        logs="",
        output_dir=OUTPUT_DIR,
        quality=quality,
        progress_keys=[],
    )

    buffer = LogBuffer()
    try:
        from main import run_generation

        with redirect_stdout(buffer), redirect_stderr(buffer):
            run_generation(
                initial_requirement=requirement,
                interactive_requirement=False,
                output_dir=OUTPUT_DIR,
                quality_level=quality,
            )
        set_state(
            running=False,
            status="done",
            message=f"生成完成，结果已写入 {OUTPUT_DIR}。",
        )
    except Exception:
        error = traceback.format_exc()
        append_log("\n" + error)
        set_state(
            running=False,
            status="error",
            message="生成失败，请查看日志并检查 API Key、依赖和需求描述。",
        )


def json_response(handler, data, status=200):
    payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(payload)))
    handler.end_headers()
    handler.wfile.write(payload)


def read_json_body(handler):
    length = int(handler.headers.get("Content-Length", "0"))
    if length <= 0:
        return {}
    try:
        return json.loads(handler.rfile.read(length).decode("utf-8"))
    except json.JSONDecodeError:
        return {}


class UIHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/":
            payload = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if path == "/api/status":
            with job_lock:
                state = dict(job_state)
                state["conversation"] = list(job_state["conversation"])
            json_response(self, state)
            return

        self.send_error(404)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/chat":
            data = read_json_body(self)
            message = str(data.get("message", "")).strip()
            response = handle_user_chat(message)
            status = 200 if response.get("ok") else 400
            json_response(self, response, status)
            return

        if path != "/api/generate":
            self.send_error(404)
            return

        with job_lock:
            if job_state["running"]:
                json_response(self, {"ok": False, "message": "已有任务正在运行。"}, 409)
                return

        data = read_json_body(self)
        message = str(data.get("message", "")).strip()
        quality = str(data.get("quality", "balanced")).strip().lower()
        if quality not in {"fast", "balanced", "quality"}:
            quality = "balanced"
        explicit_requirement = str(data.get("requirement", "")).strip()
        with job_lock:
            if message:
                job_state["plan_text"] = ""
                job_state["ready_to_generate"] = False
                job_state["conversation"].append({"role": "user", "text": message})
            if explicit_requirement and not any(
                item.get("role") == "user" for item in job_state["conversation"]
            ):
                job_state["conversation"].append(
                    {"role": "user", "text": explicit_requirement}
                )
            update_requirement_state_unlocked()
            conversation = list(job_state["conversation"])
            requirement = explicit_requirement or job_state["plan_text"]

        if not requirement:
            try:
                ai_result = call_requirement_ai(conversation, force_plan=True)
                if ai_result["status"] != "plan":
                    ai_result["status"] = "plan"
                requirement = ai_result["plan"] or ai_result["reply"]
                with job_lock:
                    job_state["plan_text"] = requirement
                    job_state["ready_to_generate"] = True
                    job_state["conversation"].append(
                        {
                            "role": "assistant",
                            "text": f"{ai_result['reply']}\n\n{requirement}",
                        }
                    )
                    update_requirement_state_unlocked()
            except Exception as exc:
                json_response(
                    self,
                    {"ok": False, "message": f"生成前需要先由 AI 整理完整方案，但请求失败：{exc}"},
                    500,
                )
                return

        if len(requirement) < 20:
            json_response(
                self,
                {"ok": False, "message": "请先和 AI 多聊一轮，让它整理出可生成的完整方案。"},
                400,
            )
            return

        Path(".crew_state").mkdir(exist_ok=True)
        Path(".crew_state/ui_requirement.txt").write_text(requirement, encoding="utf-8")
        with job_lock:
            job_state["conversation"].append(
                {
                    "role": "assistant",
                    "text": "将使用上面的完整方案开始生成微信小程序。右侧会持续显示运行日志。",
                }
            )
            update_requirement_state_unlocked()

        thread = threading.Thread(target=run_job, args=(requirement, quality), daemon=True)
        thread.start()
        json_response(self, {"ok": True, "message": "任务已开始。"})

    def log_message(self, format, *args):
        return


HTML = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>WeCraft AI | 微信小程序共创生成台</title>
  <style>
    * { box-sizing: border-box; }
    :root {
      --ink: #172033;
      --muted: #657084;
      --line: #dce3ea;
      --surface: #ffffff;
      --soft: #f5f7f8;
      --blue: #2563eb;
      --blue-dark: #1e4fd0;
      --green: #0f8f72;
      --amber: #b7791f;
    }
    html,
    body {
      height: 100%;
    }
    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
      color: var(--ink);
      background: #edf1f3;
      overflow: hidden;
    }
    .app {
      height: 100vh;
      overflow: hidden;
      display: grid;
      grid-template-columns: minmax(0, 1fr) 400px;
      gap: 0;
    }
    .chat {
      display: flex;
      flex-direction: column;
      height: 100vh;
      min-height: 0;
      overflow: hidden;
      border-right: 1px solid var(--line);
      background: var(--surface);
    }
    .topbar {
      flex: 0 0 auto;
      padding: 16px 30px;
      border-bottom: 1px solid var(--line);
      background: #fbfcfc;
    }
    .brand-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      min-width: 0;
    }
    .brand-mark {
      width: 42px;
      height: 42px;
      flex: 0 0 auto;
    }
    .brand-mark svg {
      display: block;
      width: 100%;
      height: 100%;
    }
    .brand-name {
      font-size: 18px;
      font-weight: 700;
      color: var(--ink);
    }
    .messages {
      flex: 1 1 auto;
      min-height: 0;
      padding: 26px 30px 18px;
      overflow-y: auto;
    }
    .row {
      display: flex;
      margin-bottom: 18px;
    }
    .row.user { justify-content: flex-end; }
    .bubble {
      max-width: 760px;
      padding: 14px 16px;
      border-radius: 8px;
      font-size: 15px;
      line-height: 1.7;
      white-space: pre-wrap;
    }
    .assistant .bubble {
      border: 1px solid #dfe6ec;
      background: #f7f9fa;
      color: #243044;
    }
    .user .bubble {
      background: var(--blue);
      color: #ffffff;
    }
    .composer {
      flex: 0 0 auto;
      padding: 18px 30px 24px;
      border-top: 1px solid var(--line);
      background: #fbfcfc;
    }
    textarea {
      width: 100%;
      min-height: 132px;
      resize: vertical;
      border: 1px solid #cad4de;
      border-radius: 8px;
      padding: 14px;
      font: inherit;
      line-height: 1.6;
      color: var(--ink);
      outline: none;
      background: var(--surface);
    }
    textarea:focus {
      border-color: var(--blue);
      box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.12);
    }
    .actions {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-top: 12px;
    }
    .buttons {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    select {
      min-width: 118px;
      border: 1px solid #cad4de;
      border-radius: 8px;
      padding: 10px 12px;
      font: inherit;
      color: #243044;
      background: var(--surface);
    }
    .status {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      min-height: 22px;
      color: var(--muted);
      font-size: 13px;
    }
    .status.loading {
      color: #1f4fbf;
      font-weight: 600;
    }
    .status.loading::before {
      content: "";
      width: 13px;
      height: 13px;
      border: 2px solid #b9c9f5;
      border-top-color: var(--blue);
      border-radius: 50%;
      animation: status-spin 0.8s linear infinite;
    }
    @keyframes status-spin {
      to { transform: rotate(360deg); }
    }
    button {
      border: 0;
      border-radius: 8px;
      padding: 11px 18px;
      font: inherit;
      font-weight: 600;
      cursor: pointer;
      background: var(--blue);
      color: #ffffff;
    }
    button:hover:not(:disabled) {
      background: var(--blue-dark);
    }
    button:disabled {
      cursor: not-allowed;
      background: #a8b5c9;
    }
    button.secondary {
      border: 1px solid #cad4de;
      background: var(--surface);
      color: #243044;
    }
    button.secondary:hover:not(:disabled) {
      background: #eef4f6;
    }
    button.secondary:disabled {
      color: #7a8699;
      background: #eef2f7;
    }
    .side {
      height: 100vh;
      min-height: 0;
      display: flex;
      flex-direction: column;
      gap: 18px;
      padding: 24px;
      background: #f3f6f6;
      overflow: hidden;
    }
    .panel {
      flex: 0 0 auto;
      padding: 18px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--surface);
    }
    .panel:last-child {
      flex: 1 1 auto;
      min-height: 0;
      display: flex;
      flex-direction: column;
    }
    .panel h2 {
      margin: 0 0 12px;
      font-size: 16px;
      letter-spacing: 0;
      color: #223047;
    }
    .tip {
      margin: 0 0 10px;
      color: #4b5870;
      font-size: 14px;
      line-height: 1.65;
    }
    .tip strong {
      color: var(--green);
      font-weight: 700;
    }
    .sample {
      display: block;
      width: 100%;
      margin-top: 10px;
      padding: 12px;
      border: 1px solid #d8e0e6;
      border-radius: 8px;
      background: var(--surface);
      color: #243044;
      text-align: left;
      font-size: 13px;
      font-weight: 500;
    }
    .sample:hover {
      border-color: #9fb4c8;
      background: #f7faf9;
    }
    .sample span {
      display: block;
      margin-top: 4px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 400;
      line-height: 1.45;
    }
    .logs {
      flex: 1 1 auto;
      min-height: 0;
      overflow: auto;
      padding: 12px;
      border-radius: 8px;
      background: #121820;
      color: #d1d5db;
      font-family: Consolas, "SFMono-Regular", monospace;
      font-size: 12px;
      line-height: 1.55;
      white-space: pre-wrap;
    }
    @media (max-width: 960px) {
      body { overflow: auto; }
      .app { height: auto; min-height: 100vh; overflow: visible; grid-template-columns: 1fr; }
      .chat { height: auto; min-height: auto; border-right: 0; overflow: visible; }
      .side { height: auto; min-height: auto; overflow: visible; }
      .actions { align-items: stretch; flex-direction: column; }
      .buttons { justify-content: stretch; }
      .buttons button, .buttons select { flex: 1 1 140px; }
      .logs { min-height: 300px; max-height: 50vh; }
      .messages { flex: 0 0 auto; max-height: 300px; }
      .messages, .topbar, .composer { padding-left: 18px; padding-right: 18px; }
    }
  </style>
</head>
<body>
  <main class="app">
    <section class="chat">
      <header class="topbar">
        <div class="brand-row">
          <div class="brand">
            <div class="brand-mark" aria-hidden="true">
              <svg viewBox="0 0 512 512" focusable="false">
                <rect width="512" height="512" rx="92" fill="#172033"></rect>
                <path
                  d="M116 178 L160 334 L230 220 L282 334 L396 178"
                  fill="none"
                  stroke="#ffffff"
                  stroke-width="54"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                ></path>
              </svg>
            </div>
            <div class="brand-name">WeCraft AI</div>
          </div>
        </div>
      </header>

      <div class="messages" id="messages">
        <div class="row assistant">
          <div class="bubble">你好，我是 WeCraft AI。你可以先粗略说想做什么小程序，我会和你一起梳理需求、补齐关键细节，最后整理出一份可直接用于生成代码的完整方案。</div>
        </div>
      </div>

      <section class="composer">
        <textarea id="requirement" placeholder="输入你的想法，或继续回答 AI 的追问。例如：我想做一个校园二手书交换小程序，学生可以发布书籍、搜索书籍、收藏、留言，管理员可以处理举报。希望使用微信云开发。"></textarea>
        <div class="actions">
          <div class="status" id="status">准备就绪</div>
          <div class="buttons">
            <select id="quality" title="生成质量档位">
              <option value="balanced" selected>均衡</option>
              <option value="fast">省 token</option>
              <option value="quality">高质量</option>
            </select>
            <button class="secondary" id="sendBtn" onclick="sendMessage()">继续共创</button>
            <button id="generateBtn" onclick="startGenerate()">生成小程序</button>
          </div>
        </div>
      </section>
    </section>

    <aside class="side">
      <div class="panel">
        <h2>共创清单</h2>
        <p class="tip"><strong>先说目标：</strong>用户是谁，要完成什么核心流程。</p>
        <p class="tip"><strong>补齐结构：</strong>页面、数据字段、权限和边界状态越清楚，生成结果越稳。</p>
        <p class="tip"><strong>确认后生成：</strong>方案成形后点击“生成小程序”，系统会用这份方案输出代码。</p>
        <p class="tip">如果使用微信云开发，请说明集合名称、云函数名称、权限规则和是否需要上传图片。</p>
        <p class="tip">生成后仍需在微信开发者工具中配置 envId，并部署云函数、创建数据库集合。</p>
      </div>

      <div class="panel">
        <h2>示例灵感</h2>
        <button class="sample" onclick="useSample(0)">校园二手书交换<span>发布、搜索、收藏、留言和管理员审核</span></button>
        <button class="sample" onclick="useSample(1)">健身打卡与计划管理<span>训练计划、打卡记录、连续天数和统计</span></button>
        <button class="sample" onclick="useSample(2)">社区维修报修<span>图片报修、进度跟踪、接单处理和评价</span></button>
      </div>

      <div class="panel">
        <h2>生成日志</h2>
        <div class="logs" id="logs">暂无日志</div>
      </div>
    </aside>
  </main>

  <script>
    const samples = [
      "我想做一个校园二手书交换微信小程序。学生可以发布书籍、浏览和搜索书籍、查看详情、收藏、留言联系；管理员可以查看举报并处理违规书籍。需要首页推荐、搜索列表、书籍详情、发布/编辑、消息或评论、个人中心。优先使用微信云开发。",
      "我想做一个健身打卡小程序。用户可以创建训练计划、每日打卡、查看连续打卡天数和周统计，也可以记录体重变化。需要首页今日任务、计划管理、打卡记录、数据统计、个人中心。可以先用本地存储或 mock 数据。",
      "我想做一个社区维修报修小程序。住户可以提交报修单、上传图片、查看处理进度和评价；维修人员可以接单、更新状态；管理员可以分配工单和查看统计。需要报修首页、工单列表、工单详情、提交表单、个人中心。"
    ];

    let polling = null;
    let conversationLength = 1;
    let serverConversationLength = 1;
    const READY_STATUS = "准备就绪";

    function appendMessage(role, text) {
      const messages = document.getElementById("messages");
      const row = document.createElement("div");
      row.className = "row " + role;
      const bubble = document.createElement("div");
      bubble.className = "bubble";
      bubble.textContent = text;
      row.appendChild(bubble);
      messages.appendChild(row);
      messages.scrollTop = messages.scrollHeight;
      conversationLength += 1;
    }

    function renderConversation(items) {
      if (!Array.isArray(items)) return;
      const messages = document.getElementById("messages");
      messages.innerHTML = "";
      conversationLength = 0;
      items.forEach(item => appendMessage(item.role, item.text));
      serverConversationLength = items.length;
    }

    function syncConversation(items) {
      if (!Array.isArray(items) || items.length <= serverConversationLength) return;
      for (let i = serverConversationLength; i < items.length; i += 1) {
        appendMessage(items[i].role, items[i].text);
      }
      serverConversationLength = items.length;
    }

    function useSample(index) {
      document.getElementById("requirement").value = samples[index];
    }

    function setStatus(text, isLoading = false) {
      const status = document.getElementById("status");
      status.textContent = text || READY_STATUS;
      status.classList.toggle("loading", isLoading);
    }

    function setBusy(isBusy, statusText = "") {
      document.getElementById("sendBtn").disabled = isBusy;
      document.getElementById("generateBtn").disabled = isBusy;
      document.getElementById("quality").disabled = isBusy;
      if (statusText || !isBusy) {
        setStatus(statusText || READY_STATUS, Boolean(isBusy && statusText));
      }
    }

    async function sendMessage() {
      const textarea = document.getElementById("requirement");
      const message = textarea.value.trim();
      if (message.length < 2) {
        appendMessage("assistant", "先写一点想法吧，我会基于上下文继续分析和追问。");
        return;
      }

      setBusy(true, "正在共创中…");
      try {
        const res = await fetch("/api/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message })
        });
        const data = await res.json();
        if (res.ok) {
          textarea.value = "";
          renderConversation(data.conversation);
        } else {
          appendMessage("assistant", data.message || "发送失败。");
        }
      } catch (error) {
        appendMessage("assistant", "发送失败，请检查本地服务是否仍在运行。");
      } finally {
        setBusy(false, READY_STATUS);
      }
    }

    async function startGenerate() {
      const textarea = document.getElementById("requirement");
      const message = textarea.value.trim();
      const quality = document.getElementById("quality").value;
      setBusy(true, "正在启动生成…");

      let res;
      let data;
      try {
        res = await fetch("/api/generate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message, quality })
        });
        data = await res.json();
      } catch (error) {
        appendMessage("assistant", "启动失败，请检查本地服务是否仍在运行。");
        setBusy(false, READY_STATUS);
        return;
      }
      if (!res.ok) {
        appendMessage("assistant", data.message || "启动失败。");
        setBusy(false, READY_STATUS);
        return;
      }
      textarea.value = "";
      pollStatus();
      polling = setInterval(pollStatus, 1500);
    }

    async function pollStatus() {
      const res = await fetch("/api/status");
      const data = await res.json();
      setStatus(data.message, data.running);
      document.getElementById("logs").textContent = data.logs || "暂无日志";
      document.getElementById("logs").scrollTop = document.getElementById("logs").scrollHeight;
      syncConversation(data.conversation);

      if (!data.running) {
        setBusy(false);
        if (polling) clearInterval(polling);
        polling = null;
        if (data.status === "done") {
          appendMessage("assistant", "生成完成。你可以在 generated_mini_program 目录中查看结果，并用微信开发者工具导入调试。");
        }
        if (data.status === "error") {
          appendMessage("assistant", "生成过程出错了。请先看右侧日志，常见原因是 main.py 大模型配置不可用、依赖未安装或模型接口不可用。");
        }
      }
    }

    pollStatus();
  </script>
</body>
</html>
"""


def main():
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    server = ThreadingHTTPServer((HOST, PORT), UIHandler)
    server.daemon_threads = True
    url = f"http://{HOST}:{PORT}"
    print(f"UI 已启动: {url}")
    print("按 Ctrl+C 停止服务。")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    server.serve_forever()


if __name__ == "__main__":
    main()
