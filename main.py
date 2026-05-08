import os
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Set


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

from crewai import Agent, Task, Crew, Process
from crewai.llm import LLM


# =========================
# 1. LLM 配置
# =========================
llm = LLM(
    model="deepseek-v4-pro",
    api_key="sk-7b1e03be1758400d84adc4dcb30bcb01",
    api_base="https://api.deepseek.com",
    temperature=0.3,
    max_tokens=10000,
    timeout=180,
)

llm_json = LLM(
    model="deepseek-v4-pro",
    api_key="sk-7b1e03be1758400d84adc4dcb30bcb01",
    api_base="https://api.deepseek.com",
    temperature=0.0,
    max_tokens=98192,
    timeout=180,
    response_format={"type": "json_object"},
)
# llm = LLM(
#     model="deepseek-v3",
#     api_key="sk-9g8dxedtsALsLdeJv4XLx01rR1OxD88R57GOYjByoq6wCNKI",
#     api_base="https://api.chat.csu.edu.cn/v1",
#     temperature=0.3,
#     max_tokens=10000,
#     timeout=180,
# )
#
# llm_json = LLM(
#     model="deepseek-v3",
#     api_key="sk-9g8dxedtsALsLdeJv4XLx01rR1OxD88R57GOYjByoq6wCNKI",
#     api_base="https://api.chat.csu.edu.cn/v1",
#     temperature=0.0,
#     max_tokens=98192,
#     timeout=180,
#     response_format={"type": "json_object"},
# )

# =========================
# 2. Agents
# =========================
user_agent = Agent(
    role="资深微信小程序需求分析师",
    goal="通过与用户交互，明确小程序需求，并输出结构化需求文档",
    backstory="""
你是一位经验丰富的微信小程序需求分析师，擅长通过多轮交流把模糊需求整理成清晰的开发需求。
""",
    llm=llm,
    verbose=True,
    allow_delegation=False,
    system_prompt="""
你是一位经验丰富的微信小程序需求分析师。

要求：
1. 与用户多轮交互，逐步明确需求。
2. 问题聚焦开发实现，不讨论无关商业背景。
3. 最终输出结构化需求总结，包含：
   - 项目目标
   - 用户角色
   - 功能模块
   - 页面与跳转逻辑
   - 数据字段建议
   - 技术实现要点
   - 待确认项
4. 每轮提问 2~5 个关键问题。
5. 在最终一轮输出结构化总结，而不是一直提问不收束。
""",
)

organizer_agent = Agent(
    role="资深微信小程序架构师",
    goal="把需求转为清晰的系统架构、页面设计和模块划分",
    backstory="""
你是一位资深微信小程序架构师，擅长输出结构化架构文档，为代码生成提供依据。
""",
    llm=llm,
    verbose=True,
    allow_delegation=False,
    system_prompt="""
你是一位微信小程序架构师。

输出必须包含：
【项目架构设计】
【功能模块拆解】
【页面结构设计】
【数据结构设计】
【API设计】
【用户流程】
【技术选型说明】
【风险与优化建议】

额外要求：
1. 页面设计必须尽量精简，避免一个小功能拆一个页面
2. 一个页面可以承载多个功能模块
3. 相近场景优先合并为通用页，例如：
   - 新增/编辑 -> 通用表单页
   - 多类详情 -> 通用详情页
   - 多类列表 -> 通用列表页
4. 可复用 UI 优先抽为组件，而不是页面
5. 中小型项目优先控制在 5~8 个页面内

内容必须具体，可直接指导开发。
""",
)

file_planner_agent = Agent(
    role="微信小程序工程目录规划师",
    goal="根据架构设计产出尽可能精简但完整可运行的文件路径清单",
    backstory="""
你擅长将小程序架构设计转换成完整且尽量精简的工程文件列表。
""",
    llm=llm_json,
    verbose=False,
    allow_delegation=False,
    system_prompt="""
你负责根据架构设计输出完整项目文件清单。

只能输出 JSON，格式如下：
{
  "files": [
    {
      "path": "app.js",
      "type": "config",
      "purpose": "小程序入口逻辑"
    }
  ]
}

要求：
1. 只能输出合法 JSON
2. 必须列出完整路径
3. 必须包含 app.js / app.json / app.wxss
4. 页面默认应包含：
   - .js
   - .wxml
   - .wxss
   - .json
5. 不需要输出 project.config.json 和 sitemap.json，它们由系统模板生成
6. 每个文件对象必须包含：
   - path
   - type
   - purpose
7. 不允许解释性文字

压缩要求（非常重要）：
8. 优先减少页面数量，避免过度拆分
9. 相似功能页面优先合并为通用页面
10. 可复用 UI 块优先设计为 components，而不是 pages
11. 对中小型项目，pages 数量尽量控制在 5~8 个
12. 非核心功能不要单独拆页，优先并入已有页面
13. 对新增/编辑/详情等相近场景，优先复用通用页面
14. 不允许生成明显重复用途的页面
""",
)

codegen_context_agent = Agent(
    role="代码生成上下文压缩师",
    goal="将需求分析与架构设计整理为信息充分但不冗余的代码生成上下文",
    backstory="""
你擅长把长篇需求文档和架构设计文档压缩成短小、结构化、可复用的代码生成上下文。
你非常清楚哪些信息对代码生成真正有帮助，哪些只是冗余说明。
""",
    llm=llm_json,
    verbose=False,
    allow_delegation=False,
    system_prompt="""
你负责把“需求分析结果 + 架构设计结果”整理成“代码生成专用上下文”。

只能输出合法 JSON，格式如下：
{
  "project_summary": "一句话项目概述",
  "pages": [
    {
      "path": "pages/index/index",
      "purpose": "页面用途",
      "core_logic": "页面核心逻辑",
      "ui_notes": "页面结构或UI重点"
    }
  ],
  "data_model": "关键数据结构摘要",
  "navigation": "页面跳转关系摘要",
  "constraints": "代码实现必须遵守的重要约束"
}

要求：
1. 只能输出 JSON
2. 不要过度压缩，必须保留会影响代码质量的业务规则、字段、状态、页面交互和边界流程
3. 删除重复叙述和泛泛而谈内容，但不要删除具体功能细节
4. pages 中尽量覆盖文件清单可能出现的页面
5. 字段内容要具体、可直接指导代码生成
6. constraints 要强调页面路径一致、跳转一致、数据字段一致、mock 数据结构一致等工程约束
""",
)

code_agent = Agent(
    role="微信小程序开发工程师",
    goal="生成微信小程序文件内容，并保持页面四件套与项目上下文一致",
backstory="""
你擅长在上下文充分但不冗余的情况下生成微信小程序页面和文件，并保持项目整体一致。
""",
    llm=llm_json,
    verbose=False,
    allow_delegation=False,
    system_prompt="""
你是一位微信小程序开发工程师。

任务要求：
1. 严格按任务要求生成一个文件或一个页面四件套
2. 严格依据：
   - 项目核心上下文
   - 项目文件清单
   - 当前文件路径与用途
   - 当前文件的直接依赖文件
3. 只能输出 JSON，格式如下：
{
  "path": "pages/index/index.js",
  "content": "完整代码"
}
4. 不允许输出解释文字
5. 不允许输出 markdown
6. content 必须完整，不能省略
7. 若依赖文件未提供，不要臆造复杂耦合，只实现当前文件能独立成立的部分
8. 如果任务要求生成页面四件套，必须一次性保证 js/wxml/wxss/json 相互匹配
9. 必须保持：
   - 页面路径与 app.json 一致
   - 页面四件套（js/wxml/wxss/json）之间一致
   - 页面跳转路径一致
10. 不要自行额外创建文件清单外的路径
""",
)

# =========================
# 3. 配置
# =========================
OUTPUT_DIR = "generated_mini_program"
QUALITY_PRESETS = {
    "fast": {
        "max_dep_context": 4,
        "retry_times": 2,
        "max_page_count": 8,
        "context_limits": {
            "project_summary": 500,
            "pages": 18,
            "data_model": 1200,
            "navigation": 1000,
            "constraints": 1000,
            "dependency_excerpt": 900,
        },
        "validation": "basic",
    },
    "balanced": {
        "max_dep_context": 6,
        "retry_times": 3,
        "max_page_count": 10,
        "context_limits": {
            "project_summary": 800,
            "pages": 30,
            "data_model": 2000,
            "navigation": 1800,
            "constraints": 1800,
            "dependency_excerpt": 1200,
        },
        "validation": "balanced",
    },
    "quality": {
        "max_dep_context": 8,
        "retry_times": 4,
        "max_page_count": 14,
        "context_limits": {
            "project_summary": 1200,
            "pages": 50,
            "data_model": 3200,
            "navigation": 2800,
            "constraints": 2800,
            "dependency_excerpt": 1600,
        },
        "validation": "strict",
    },
}
QUALITY_LEVEL = os.getenv("GENERATION_QUALITY", "balanced").strip().lower()
if QUALITY_LEVEL not in QUALITY_PRESETS:
    print(f"[WARN] 未知 GENERATION_QUALITY={QUALITY_LEVEL}，已回退为 balanced。")
    QUALITY_LEVEL = "balanced"
QUALITY_CONFIG = QUALITY_PRESETS[QUALITY_LEVEL]
MAX_DEP_CONTEXT = int(QUALITY_CONFIG["max_dep_context"])
RETRY_TIMES = int(QUALITY_CONFIG["retry_times"])
MAX_PAGE_COUNT = int(QUALITY_CONFIG["max_page_count"])
CONTEXT_LIMITS = QUALITY_CONFIG["context_limits"]
VALIDATION_LEVEL = str(QUALITY_CONFIG["validation"])
ARTIFACT_DIR = Path(".crew_state") / "latest_generation"

user_requirement = os.getenv("USER_REQUIREMENT", "我想开发一款微信小程序。")


def configure_quality(quality_level: Optional[str] = None):
    global QUALITY_LEVEL, QUALITY_CONFIG, MAX_DEP_CONTEXT, RETRY_TIMES
    global MAX_PAGE_COUNT, CONTEXT_LIMITS, VALIDATION_LEVEL

    selected = (quality_level or os.getenv("GENERATION_QUALITY", QUALITY_LEVEL)).strip().lower()
    if selected not in QUALITY_PRESETS:
        print(f"[WARN] 未知质量档位 {selected}，已回退为 balanced。")
        selected = "balanced"

    QUALITY_LEVEL = selected
    QUALITY_CONFIG = QUALITY_PRESETS[selected]
    MAX_DEP_CONTEXT = int(QUALITY_CONFIG["max_dep_context"])
    RETRY_TIMES = int(QUALITY_CONFIG["retry_times"])
    MAX_PAGE_COUNT = int(QUALITY_CONFIG["max_page_count"])
    CONTEXT_LIMITS = QUALITY_CONFIG["context_limits"]
    VALIDATION_LEVEL = str(QUALITY_CONFIG["validation"])


# =========================
# 4. Task 构造
# =========================
def build_requirement_task(user_requirement: str, human_input: bool = True) -> Task:
    interaction_note = (
        "请与用户进行多轮交互，逐步明确需求，最终输出结构化需求分析结果。"
        if human_input
        else "这是从 Web UI 提交的一次性完整需求。不要继续向用户追问；请基于现有信息合理补全默认假设，并直接输出结构化需求分析结果。"
    )

    return Task(
        description=f"""
用户提出的初步需求如下：
{user_requirement}

{interaction_note}
""",
        expected_output="""
完整需求分析报告，包含：
- 项目目标
- 用户角色
- 功能模块
- 页面设计
- 交互逻辑
- 数据字段建议
- 技术实现要点
- 待确认项
""",
        agent=user_agent,
        human_input=human_input,
        async_execution=False,
    )


def build_architecture_task(requirement_result: str) -> Task:
    return Task(
        description=f"""
请基于以下需求分析结果，输出完整微信小程序架构设计。

【需求分析结果】
{requirement_result}
""",
        expected_output="结构化架构设计文档",
        agent=organizer_agent,
        async_execution=False,
    )


def build_file_plan_task(architecture_result: str) -> Task:
    return Task(
        description=f"""
请根据以下架构设计输出完整项目文件清单。

【架构设计结果】
{architecture_result}

只能输出 JSON，格式如下：
{{
  "files": [
    {{
      "path": "app.js",
      "type": "config",
      "purpose": "小程序入口逻辑"
    }}
  ]
}}

要求：
1. 页面默认输出四件套：js / wxml / wxss / json
2. 不需要输出 project.config.json 和 sitemap.json
3. 必须输出 path/type/purpose
4. 不允许解释性文字
5. pages 数量建议控制在 6~{MAX_PAGE_COUNT} 个以内；简单项目可以更少，复杂项目不要为了压缩而丢掉核心流程
6. 相似功能页面可以合并，但必须覆盖需求中的主要用户角色、关键业务状态和核心流程
7. 可复用内容优先放 components，但只有多个页面确实复用时才新增组件
8. app.js / app.json / app.wxss 可列出，但最终会由系统模板固定生成
""",
        expected_output="项目文件清单 JSON",
        agent=file_planner_agent,
        async_execution=False,
    )


def build_codegen_context_task(
    requirement_result: str, architecture_result: str
) -> Task:
    return Task(
        description=f"""
请将以下“需求分析结果”和“架构设计结果”整理为代码生成专用上下文。

【需求分析结果】
{requirement_result}

【架构设计结果】
{architecture_result}

输出要求：
1. 只能输出 JSON
2. 严格按以下格式输出：
{{
  "project_summary": "一句话项目概述",
  "pages": [
    {{
      "path": "pages/index/index",
      "purpose": "页面用途",
      "core_logic": "页面核心逻辑",
      "ui_notes": "页面结构或UI重点"
    }}
  ],
  "data_model": "关键数据结构摘要",
  "navigation": "页面跳转关系摘要",
  "constraints": "代码实现必须遵守的重要约束"
}}
3. 中等压缩，保留会影响代码实现的业务细节、字段、页面交互和状态流转
4. 删除冗余解释、长篇背景、泛化建议
5. 内容具体，可直接指导页面四件套生成
""",
        expected_output="代码生成专用上下文 JSON",
        agent=codegen_context_agent,
        async_execution=False,
    )


def build_single_file_task(
    file_info: Dict[str, Any],
    file_specific_context: str,
    file_plan_raw: str,
    dependency_context_text: str,
) -> Task:
    path = file_info["path"]
    purpose = file_info.get("purpose", "")
    ftype = file_info.get("type", "file")

    return Task(
        description=f"""
你现在需要生成微信小程序项目中的一个文件。

【项目核心上下文】
{file_specific_context}

【项目文件清单】
{file_plan_raw}

【当前要生成的文件】
路径：{path}
类型：{ftype}
用途：{purpose}

【当前文件的直接依赖上下文】
{dependency_context_text}

请只生成当前这个文件，并输出严格 JSON：
{{
  "path": "{path}",
  "content": "完整文件内容"
}}
""",
        expected_output=f"{path} 的完整代码 JSON",
        agent=code_agent,
        async_execution=False,
    )


def build_page_bundle_task(
    page_dir: str,
    page_files: List[Dict[str, Any]],
    page_context: str,
    file_plan_raw: str,
    dependency_context_text: str,
    validation_feedback: str = "",
) -> Task:
    expected_paths = [item["path"] for item in page_files]
    purposes = {
        item["path"]: item.get("purpose", "")
        for item in page_files
    }

    return Task(
        description=f"""
你现在需要一次生成微信小程序的一个页面四件套。

【项目核心上下文】
{page_context}

【项目文件清单】
{file_plan_raw}

【当前页面】
页面目录：{page_dir}
必须生成这些文件：
{json.dumps(expected_paths, ensure_ascii=False, indent=2)}

【文件用途】
{json.dumps(purposes, ensure_ascii=False, indent=2)}

【当前页面可参考的依赖上下文】
{dependency_context_text}

【上一轮校验反馈】
{validation_feedback or "无"}

请一次性生成当前页面四件套，并输出严格 JSON：
{{
  "files": [
    {{"path": "{page_dir}.js", "content": "完整 JS 代码"}},
    {{"path": "{page_dir}.wxml", "content": "完整 WXML 代码"}},
    {{"path": "{page_dir}.wxss", "content": "完整 WXSS 代码"}},
    {{"path": "{page_dir}.json", "content": "完整 JSON 配置"}}
  ]
}}

要求：
1. 只能输出 JSON，不允许 markdown 或解释文字
2. files 必须且只能包含上面列出的路径
3. js / wxml / wxss / json 必须相互匹配
4. 事件名、data 字段、列表字段、跳转路径必须一致
5. 可以使用合理 mock 数据，但 mock 字段必须符合项目数据模型
6. 不要引用文件清单外的页面或组件
7. 如果有上一轮校验反馈，必须优先修复反馈中的全部问题
""",
        expected_output=f"{page_dir} 页面四件套 JSON",
        agent=code_agent,
        async_execution=False,
    )


# =========================
# 5. 文件与 JSON 工具
# =========================
def safe_json_loads(text):
    if isinstance(text, dict):
        return text
    text = str(text).strip()
    if text.startswith("```"):
        text = text.replace("```json", "").replace("```", "").strip()
    return json.loads(text)


def save_artifact_text(name: str, content: Any):
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / name).write_text(str(content), encoding="utf-8")


def save_artifact_json(name: str, data: Any):
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / name).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def init_artifact_dir():
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    save_artifact_json(
        "manifest.json",
        {
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "quality": QUALITY_LEVEL,
            "max_dep_context": MAX_DEP_CONTEXT,
            "retry_times": RETRY_TIMES,
            "max_page_count": MAX_PAGE_COUNT,
            "validation_level": VALIDATION_LEVEL,
            "output_dir": OUTPUT_DIR,
        },
    )


def ensure_dir(path: str) -> Path:
    full_path = Path(OUTPUT_DIR) / path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    return full_path


def save_one_file(path: str, content: str):
    full_path = ensure_dir(path)
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[OK] 已写入: {full_path}")


def read_file(path: str) -> Optional[str]:
    full_path = Path(OUTPUT_DIR) / path
    if not full_path.exists():
        return None
    return full_path.read_text(encoding="utf-8")


def write_project_config(
    output_dir: str,
    projectname: str = "generated_mini_program",
    appid: str = "touristappid",
    miniprogram_root: str = "./",
):
    config = {
        "description": "微信小程序项目",
        "packOptions": {"ignore": []},
        "setting": {
            "urlCheck": False,
            "es6": True,
            "enhance": True,
            "postcss": True,
            "minified": True,
            "compileHotReLoad": False,
        },
        "compileType": "miniprogram",
        "libVersion": "trial",
        "appid": appid,
        "projectname": projectname,
        "simulatorType": "wechat",
        "simulatorPluginLibVersion": {},
        "condition": {},
        "miniprogramRoot": miniprogram_root,
    }

    full_path = Path(output_dir) / "project.config.json"
    full_path.parent.mkdir(parents=True, exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    print(f"[OK] 已生成: {full_path}")


def write_sitemap_json(output_dir: str):
    sitemap = {"desc": "site map", "rules": [{"action": "allow", "page": "*"}]}

    full_path = Path(output_dir) / "sitemap.json"
    full_path.parent.mkdir(parents=True, exist_ok=True)
    with open(full_path, "w", encoding="utf-8") as f:
        json.dump(sitemap, f, ensure_ascii=False, indent=2)
    print(f"[OK] 已生成: {full_path}")


def page_dirs_from_file_plan(files: List[Dict[str, Any]]) -> List[str]:
    page_dirs = sorted(collect_page_dirs(files).keys())
    if "pages/index/index" in page_dirs:
        page_dirs.remove("pages/index/index")
        page_dirs.insert(0, "pages/index/index")
    return page_dirs


def write_app_templates(output_dir: str, files: List[Dict[str, Any]]):
    page_dirs = page_dirs_from_file_plan(files)
    if not page_dirs:
        page_dirs = ["pages/index/index"]

    app_json = {
        "pages": page_dirs,
        "window": {
            "navigationBarTitleText": "小程序",
            "navigationBarBackgroundColor": "#176bff",
            "navigationBarTextStyle": "white",
            "backgroundColor": "#f5f7fb",
            "backgroundTextStyle": "light",
        },
        "style": "v2",
        "sitemapLocation": "sitemap.json",
    }

    app_js = """App({
  globalData: {
    userInfo: null,
    isLoggedIn: false
  },

  onLaunch() {
    const userInfo = wx.getStorageSync('userInfo') || null;
    this.globalData.userInfo = userInfo;
    this.globalData.isLoggedIn = !!userInfo;
  },

  setUserInfo(userInfo) {
    this.globalData.userInfo = userInfo;
    this.globalData.isLoggedIn = !!userInfo;
    wx.setStorageSync('userInfo', userInfo);
  },

  clearUserInfo() {
    this.globalData.userInfo = null;
    this.globalData.isLoggedIn = false;
    wx.removeStorageSync('userInfo');
  }
});
"""

    app_wxss = """page {
  min-height: 100vh;
  background: #f5f7fb;
  color: #172033;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
  font-size: 28rpx;
  line-height: 1.5;
}

view,
text,
button,
input,
textarea {
  box-sizing: border-box;
}

button {
  border-radius: 12rpx;
}

.page {
  min-height: 100vh;
  padding: 24rpx;
}

.card {
  border-radius: 16rpx;
  background: #ffffff;
  box-shadow: 0 8rpx 24rpx rgba(23, 32, 51, 0.06);
}

.muted {
  color: #667085;
}
"""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "app.json").write_text(
        json.dumps(app_json, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_path / "app.js").write_text(app_js, encoding="utf-8")
    (output_path / "app.wxss").write_text(app_wxss, encoding="utf-8")
    print("[OK] 已生成固定模板: app.json / app.js / app.wxss")


# =========================
# 6. 文件压缩与依赖系统
# =========================
def get_page_base(path: str) -> Optional[str]:
    if not path.startswith("pages/"):
        return None
    suffixes = [".js", ".wxml", ".wxss", ".json"]
    for s in suffixes:
        if path.endswith(s):
            return path[: -len(s)]
    return None


def get_extension(path: str) -> str:
    return Path(path).suffix.lower()


def infer_type_from_path(path: str) -> str:
    ext = get_extension(path)
    if ext == ".js":
        return "js"
    if ext == ".wxml":
        return "wxml"
    if ext == ".wxss":
        return "wxss"
    if ext == ".json":
        return "json"
    return "file"


def page_dir_from_path(path: str) -> Optional[str]:
    return get_page_base(path)


def purpose_score(purpose: str, page_dir: str) -> int:
    text = f"{purpose} {page_dir}".lower()

    keywords_rank = [
        ["首页", "home", "index", "main"],
        ["登录", "login", "auth"],
        ["列表", "list"],
        ["详情", "detail"],
        ["表单", "form", "edit", "create", "publish"],
        ["个人", "user", "profile", "mine", "me"],
        ["记录", "history", "record"],
        ["设置", "setting", "config"],
        ["搜索", "search"],
    ]

    for idx, group in enumerate(keywords_rank):
        if any(k in text for k in group):
            return idx
    return 100


def normalize_file_item(item: Dict[str, Any]) -> Dict[str, Any]:
    path = item["path"].strip().replace("\\", "/")
    path = path.lstrip("/")
    purpose = item.get("purpose", "").strip()
    ftype = item.get("type", infer_type_from_path(path))
    return {"path": path, "type": ftype, "purpose": purpose}


def dedupe_file_items(files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    seen = set()
    for item in files:
        norm = normalize_file_item(item)
        if norm["path"] not in seen:
            seen.add(norm["path"])
            out.append(norm)
    return out


def collect_page_dirs(files: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    page_map: Dict[str, Dict[str, Any]] = {}
    for item in files:
        path = item["path"]
        page_dir = page_dir_from_path(path)
        if not page_dir:
            continue

        if page_dir not in page_map:
            page_map[page_dir] = {
                "page_dir": page_dir,
                "paths": [],
                "purpose": item.get("purpose", ""),
            }
        page_map[page_dir]["paths"].append(path)
        if not page_map[page_dir]["purpose"] and item.get("purpose"):
            page_map[page_dir]["purpose"] = item.get("purpose", "")
    return page_map


def validate_file_plan_schema(files: List[Dict[str, Any]]) -> Dict[str, Any]:
    report = {"errors": [], "warnings": [], "repairs": []}
    normalized: List[Dict[str, Any]] = []
    skip_paths = {"project.config.json", "sitemap.json"}
    allowed_prefixes = ("app.", "pages/", "components/", "utils/", "cloudfunctions/")

    if not isinstance(files, list):
        raise RuntimeError("文件清单 schema 错误：files 必须是数组。")

    for idx, item in enumerate(files):
        if not isinstance(item, dict):
            report["errors"].append(f"第 {idx + 1} 项不是对象。")
            continue

        raw_path = str(item.get("path", "")).strip()
        if not raw_path:
            report["errors"].append(f"第 {idx + 1} 项缺少 path。")
            continue

        path = raw_path.replace("\\", "/").lstrip("/")
        if path != raw_path:
            report["repairs"].append(f"{raw_path} -> {path}")
        if path in skip_paths:
            report["warnings"].append(f"忽略系统模板文件：{path}")
            continue
        if ".." in Path(path).parts or ":" in path:
            report["errors"].append(f"非法路径：{path}")
            continue
        if not path.startswith(allowed_prefixes):
            report["warnings"].append(f"路径 {path} 不在常见小程序目录中，仍保留。")

        ext = get_extension(path)
        if not ext:
            report["errors"].append(f"路径缺少扩展名：{path}")
            continue
        if ext not in {".js", ".json", ".wxml", ".wxss", ".wxs", ".md"}:
            report["warnings"].append(f"路径 {path} 使用非常规扩展名 {ext}，仍保留。")

        purpose = str(item.get("purpose", "")).strip() or "未说明用途"
        if purpose == "未说明用途":
            report["repairs"].append(f"{path} 缺少 purpose，已补默认用途。")
        normalized.append(
            {
                "path": path,
                "type": str(item.get("type") or infer_type_from_path(path)).strip(),
                "purpose": purpose,
            }
        )

    normalized = dedupe_file_items(normalized)
    existing = {item["path"] for item in normalized}
    required_globals = [
        {"path": "app.js", "type": "js", "purpose": "小程序入口逻辑（系统模板生成）"},
        {"path": "app.json", "type": "json", "purpose": "全局页面与窗口配置（系统模板生成）"},
        {"path": "app.wxss", "type": "wxss", "purpose": "全局样式（系统模板生成）"},
    ]
    for item in reversed(required_globals):
        if item["path"] not in existing:
            normalized.insert(0, item)
            existing.add(item["path"])
            report["repairs"].append(f"补齐必需全局文件：{item['path']}")

    normalized = complete_page_quadruplets(normalized)
    existing = {item["path"] for item in normalized}

    component_bases = sorted(
        {
            path.rsplit(".", 1)[0]
            for path in existing
            if path.startswith("components/") and get_extension(path) in {".js", ".json", ".wxml", ".wxss"}
        }
    )
    for component_base in component_bases:
        for ext in [".js", ".wxml", ".wxss", ".json"]:
            path = f"{component_base}{ext}"
            if path not in existing:
                normalized.append(
                    {
                        "path": path,
                        "type": infer_type_from_path(path),
                        "purpose": "组件四件套补齐文件",
                    }
                )
                existing.add(path)
                report["repairs"].append(f"补齐组件四件套：{path}")

    cloud_roots = sorted(
        {
            path.split("/")[1]
            for path in existing
            if path.startswith("cloudfunctions/") and len(path.split("/")) >= 2
        }
    )
    for name in cloud_roots:
        index_path = f"cloudfunctions/{name}/index.js"
        if index_path not in existing:
            normalized.append(
                {
                    "path": index_path,
                    "type": "js",
                    "purpose": f"{name} 云函数入口",
                }
            )
            existing.add(index_path)
            report["repairs"].append(f"补齐云函数入口：{index_path}")

    if report["errors"]:
        raise RuntimeError(
            "文件清单 schema 校验失败：\n"
            + "\n".join(f"- {error}" for error in report["errors"])
        )

    report["file_count"] = len(normalized)
    report["page_count"] = len(collect_page_dirs(normalized))
    report["component_count"] = len(component_bases)
    report["cloud_function_count"] = len(cloud_roots)
    return {"files": normalized, "report": report}


def choose_core_pages(page_map: Dict[str, Dict[str, Any]], max_pages: int) -> Set[str]:
    page_infos = list(page_map.values())

    def page_sort_key(info):
        page_dir = info["page_dir"]
        purpose = info.get("purpose", "")
        special_bonus = 0
        if page_dir == "pages/index/index":
            special_bonus = -100
        return (
            special_bonus + purpose_score(purpose, page_dir),
            len(page_dir),
            page_dir,
        )

    page_infos.sort(key=page_sort_key)

    selected = []
    for info in page_infos:
        if len(selected) >= max_pages:
            break
        selected.append(info["page_dir"])

    if "pages/index/index" in page_map and "pages/index/index" not in selected:
        if selected:
            selected[-1] = "pages/index/index"
        else:
            selected.append("pages/index/index")

    return set(selected)


def build_page_quadruplet(page_dir: str, purpose: str = "") -> List[Dict[str, Any]]:
    return [
        {"path": f"{page_dir}.js", "type": "js", "purpose": purpose},
        {"path": f"{page_dir}.wxml", "type": "wxml", "purpose": purpose},
        {"path": f"{page_dir}.wxss", "type": "wxss", "purpose": purpose},
        {"path": f"{page_dir}.json", "type": "json", "purpose": purpose},
    ]


def complete_page_quadruplets(files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    files = dedupe_file_items(files)
    page_map = collect_page_dirs(files)
    existing_paths = {item["path"] for item in files}
    completed = list(files)

    for page_dir, info in page_map.items():
        purpose = info.get("purpose", "")
        for item in build_page_quadruplet(page_dir, purpose):
            if item["path"] not in existing_paths:
                completed.append(item)
                existing_paths.add(item["path"])

    return dedupe_file_items(completed)


def compress_file_plan(
    files: List[Dict[str, Any]], max_pages: int = MAX_PAGE_COUNT
) -> List[Dict[str, Any]]:
    files = complete_page_quadruplets(files)
    page_map = collect_page_dirs(files)

    required_globals = [
        {"path": "app.js", "type": "js", "purpose": "小程序入口逻辑（系统模板生成）"},
        {"path": "app.json", "type": "json", "purpose": "全局页面与窗口配置（系统模板生成）"},
        {"path": "app.wxss", "type": "wxss", "purpose": "全局样式（系统模板生成）"},
    ]
    existing_paths = {x["path"] for x in files}
    for item in reversed(required_globals):
        if item["path"] not in existing_paths:
            files.insert(0, item)
            existing_paths.add(item["path"])

    if len(page_map) <= max_pages:
        return dedupe_file_items(files)

    keep_pages = choose_core_pages(page_map, max_pages=max_pages)

    trimmed = []
    for item in files:
        page_dir = page_dir_from_path(item["path"])
        if page_dir and page_dir not in keep_pages:
            continue
        trimmed.append(item)

    print(
        f"[WARN] 文件规划页面数 {len(page_map)} 超过上限 {max_pages}，仅裁剪低优先级页面，保留核心页面四件套。"
    )
    return dedupe_file_items(trimmed)


# =========================
# 7. 代码生成上下文压缩
# =========================
def trim_text(text: str, max_len: int) -> str:
    text = str(text).strip()
    if len(text) <= max_len:
        return text
    return text[:max_len]


def normalize_codegen_context(raw: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "project_summary": trim_text(raw.get("project_summary", ""), CONTEXT_LIMITS["project_summary"]),
        "pages": raw.get("pages", [])[: CONTEXT_LIMITS["pages"]],
        "data_model": trim_text(raw.get("data_model", ""), CONTEXT_LIMITS["data_model"]),
        "navigation": trim_text(raw.get("navigation", ""), CONTEXT_LIMITS["navigation"]),
        "constraints": trim_text(raw.get("constraints", ""), CONTEXT_LIMITS["constraints"]),
    }


def find_page_summary_for_file(
    path: str, codegen_context: Dict[str, Any]
) -> Dict[str, Any]:
    page_base = get_page_base(path)
    if not page_base:
        return {}

    for p in codegen_context.get("pages", []):
        if p.get("path") == page_base:
            return p
    return {}


def build_file_specific_context(
    path: str, file_info: Dict[str, Any], codegen_context: Dict[str, Any]
) -> str:
    """
    第二层压缩：
    根据当前文件类型，从 codegen_context 中再裁剪出更小的上下文。
    """
    page_summary = find_page_summary_for_file(path, codegen_context)
    ext = get_extension(path)

    compact: Dict[str, Any] = {
        "project_summary": codegen_context.get("project_summary", ""),
        "current_file": {
            "path": path,
            "type": file_info.get("type", infer_type_from_path(path)),
            "purpose": file_info.get("purpose", ""),
        },
        "page_summary": page_summary,
    }

    if ext == ".js":
        compact["data_model"] = codegen_context.get("data_model", "")
        compact["navigation"] = codegen_context.get("navigation", "")
        compact["constraints"] = codegen_context.get("constraints", "")
    elif ext == ".wxml":
        compact["data_model"] = trim_text(codegen_context.get("data_model", ""), 1200)
        compact["navigation"] = codegen_context.get("navigation", "")
        compact["constraints"] = codegen_context.get("constraints", "")
    elif ext == ".wxss":
        compact["navigation"] = trim_text(codegen_context.get("navigation", ""), 900)
        compact["constraints"] = trim_text(codegen_context.get("constraints", ""), 900)
    elif ext == ".json":
        compact["navigation"] = trim_text(codegen_context.get("navigation", ""), 900)
        compact["constraints"] = trim_text(codegen_context.get("constraints", ""), 900)
    else:
        compact["data_model"] = trim_text(codegen_context.get("data_model", ""), 1200)
        compact["navigation"] = trim_text(codegen_context.get("navigation", ""), 900)
        compact["constraints"] = trim_text(codegen_context.get("constraints", ""), 900)

    return json.dumps(compact, ensure_ascii=False, separators=(",", ":"))


def build_page_bundle_context(
    page_dir: str, page_files: List[Dict[str, Any]], codegen_context: Dict[str, Any]
) -> str:
    page_summary = {}
    for p in codegen_context.get("pages", []):
        if p.get("path") == page_dir:
            page_summary = p
            break

    compact = {
        "project_summary": codegen_context.get("project_summary", ""),
        "current_page": {
            "path": page_dir,
            "files": page_files,
            "summary": page_summary,
        },
        "all_pages": codegen_context.get("pages", []),
        "data_model": codegen_context.get("data_model", ""),
        "navigation": codegen_context.get("navigation", ""),
        "constraints": codegen_context.get("constraints", ""),
    }
    return json.dumps(compact, ensure_ascii=False, separators=(",", ":"))


# =========================
# 8. 依赖上下文构造
# =========================
def dependency_candidates_for_path(current_path: str) -> List[str]:
    candidates: List[str] = []

    if current_path != "app.json":
        candidates.append("app.json")

    if current_path not in ["app.js", "app.wxss"]:
        candidates.append("app.js")
        candidates.append("app.wxss")

    page_base = get_page_base(current_path)
    if page_base:
        same_page_files = [
            f"{page_base}.json",
            f"{page_base}.wxml",
            f"{page_base}.wxss",
            f"{page_base}.js",
        ]
        for p in same_page_files:
            if p != current_path:
                candidates.append(p)

    if current_path.startswith("pages/user/"):
        candidates.extend(
            [
                "pages/index/index.json",
                "pages/index/index.js",
                "pages/index/index.wxml",
            ]
        )

    if "detail" in current_path:
        candidates.extend(
            [
                current_path.replace("detail", "list"),
                "pages/list/list.js",
                "pages/list/list.wxml",
                "pages/index/index.js",
            ]
        )
    elif "list" in current_path:
        candidates.extend(
            [
                "pages/index/index.js",
                "pages/index/index.wxml",
            ]
        )

    deduped = []
    seen = set()
    for c in candidates:
        if c not in seen:
            seen.add(c)
            deduped.append(c)
    return deduped


def build_dependency_context(
    current_path: str,
    generated_files_map: Dict[str, Dict[str, Any]],
    max_files: int = MAX_DEP_CONTEXT,
) -> str:
    candidates = dependency_candidates_for_path(current_path)

    selected: List[Dict[str, Any]] = []
    for path in candidates:
        if path in generated_files_map:
            selected.append(generated_files_map[path])
        if len(selected) >= max_files:
            break

    if not selected:
        return "暂无可用依赖文件。请根据项目核心上下文独立生成当前文件。"

    chunks = []
    for item in selected:
        content = item.get("content", "")
        trimmed = content[: CONTEXT_LIMITS["dependency_excerpt"]]
        chunks.append(
            f"【依赖文件】\n"
            f"路径：{item['path']}\n"
            f"用途：{item.get('purpose', '')}\n"
            f"内容（节选）：\n{trimmed}\n"
        )
    return "\n".join(chunks)


def build_page_dependency_context(
    page_dir: str,
    generated_files_map: Dict[str, Dict[str, Any]],
    max_files: int = MAX_DEP_CONTEXT,
) -> str:
    candidates = [
        "app.json",
        "app.js",
        "app.wxss",
        "pages/index/index.js",
        "pages/index/index.wxml",
    ]

    if "detail" in page_dir:
        candidates.extend(["pages/list/list.js", "pages/list/list.wxml"])
    if "profile" in page_dir or "user" in page_dir:
        candidates.extend(["pages/index/index.js", "pages/index/index.wxml"])

    selected = []
    seen = set()
    for path in candidates:
        if path in seen or path.startswith(page_dir):
            continue
        seen.add(path)
        if path in generated_files_map:
            selected.append(generated_files_map[path])
        if len(selected) >= max_files:
            break

    if not selected:
        return "暂无可用依赖文件。请根据项目核心上下文独立生成当前页面。"

    chunks = []
    for item in selected:
        content = item.get("content", "")
        chunks.append(
            f"【依赖文件】\n"
            f"路径：{item['path']}\n"
            f"用途：{item.get('purpose', '')}\n"
            f"内容（节选）：\n{content[: CONTEXT_LIMITS['dependency_excerpt']]}\n"
        )
    return "\n".join(chunks)


# =========================
# 9. 排序与路径修正
# =========================
def sort_file_plan(files: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    ext_order = {".json": 0, ".js": 1, ".wxml": 2, ".wxss": 3}

    def page_rank(path: str, purpose: str = "") -> int:
        page_dir = page_dir_from_path(path) or path
        text = f"{page_dir} {purpose}".lower()
        if page_dir == "pages/index/index" or any(k in text for k in ["首页", "home", "index"]):
            return 0
        if any(k in text for k in ["login", "auth", "登录", "授权"]):
            return 1
        if any(k in text for k in ["list", "search", "列表", "搜索", "首页列表"]):
            return 2
        if any(k in text for k in ["detail", "详情"]):
            return 3
        if any(k in text for k in ["form", "edit", "create", "publish", "upload", "表单", "编辑", "发布", "新增", "上传"]):
            return 4
        if any(k in text for k in ["message", "comment", "order", "record", "消息", "评论", "工单", "订单", "记录"]):
            return 5
        if any(k in text for k in ["profile", "user", "mine", "个人", "我的", "用户"]):
            return 6
        if any(k in text for k in ["admin", "manage", "dashboard", "管理员", "管理", "统计"]):
            return 7
        return 8

    def score(item):
        path = item["path"]
        purpose = item.get("purpose", "")

        if path == "app.json":
            return (0, path)
        if path == "app.js":
            return (1, path)
        if path == "app.wxss":
            return (2, path)
        if path.startswith("pages/"):
            page_dir = page_dir_from_path(path) or path
            return (3, page_rank(path, purpose), page_dir, ext_order.get(get_extension(path), 99), path)
        if path.startswith("components/"):
            return (4, path)
        if path.startswith("utils/"):
            return (5, path)
        if path.startswith("cloudfunctions/"):
            return (6, path)
        return (10, path)

    return sorted(files, key=score)


def normalize_generated_path(expected_path: str, model_path: Optional[str]) -> str:
    if not model_path:
        return expected_path
    model_path = str(model_path).strip().replace("\\", "/")
    if model_path != expected_path:
        print(
            f"[WARN] 模型返回路径与目标路径不一致：{model_path} -> 强制改为 {expected_path}"
        )
    return expected_path


def normalize_page_bundle_result(
    page_dir: str, page_files: List[Dict[str, Any]], result: Any
) -> List[Dict[str, str]]:
    data = safe_json_loads(result)
    files = data.get("files", [])
    expected_paths = [item["path"] for item in page_files]
    expected_set = set(expected_paths)

    by_path: Dict[str, str] = {}
    for item in files:
        path = str(item.get("path", "")).strip().replace("\\", "/")
        if path in expected_set and "content" in item:
            by_path[path] = str(item["content"])

    missing = [path for path in expected_paths if path not in by_path]
    if missing:
        raise RuntimeError(f"页面四件套缺少文件：{', '.join(missing)}")

    return [{"path": path, "content": by_path[path]} for path in expected_paths]


def content_by_path(files: List[Dict[str, str]]) -> Dict[str, str]:
    return {item["path"]: item.get("content", "") for item in files}


def strip_wxml_mustache(value: str) -> str:
    value = value.strip()
    if value.startswith("{{") or value.endswith("}}"):
        return ""
    return value


def extract_wxml_event_handlers(wxml: str) -> Set[str]:
    handlers: Set[str] = set()
    pattern = re.compile(
        r"\b(?:bind|catch|capture-bind|capture-catch)(?::?[A-Za-z][\w-]*)?\s*=\s*['\"]([^'\"]+)['\"]"
    )
    for match in pattern.finditer(wxml):
        handler = strip_wxml_mustache(match.group(1))
        if re.match(r"^[A-Za-z_$][\w$]*$", handler):
            handlers.add(handler)
    return handlers


def extract_js_page_methods(js: str) -> Set[str]:
    methods: Set[str] = set()
    page_match = re.search(r"Page\s*\(\s*\{(?P<body>.*)\}\s*\)\s*;?\s*$", js, re.S)
    body = page_match.group("body") if page_match else js
    for match in re.finditer(r"\b([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{", body):
        methods.add(match.group(1))
    for match in re.finditer(
        r"\b([A-Za-z_$][\w$]*)\s*:\s*(?:async\s+)?function\s*\(", body
    ):
        methods.add(match.group(1))
    for match in re.finditer(
        r"\b([A-Za-z_$][\w$]*)\s*:\s*(?:async\s*)?\([^)]*\)\s*=>", body
    ):
        methods.add(match.group(1))
    return methods


def normalize_mini_program_path(raw_path: str, current_page_dir: str) -> Optional[str]:
    path = raw_path.strip()
    if not path or path.startswith(("http://", "https://", "weixin://")):
        return None
    path = path.split("?")[0].split("#")[0]
    if not path or "{{" in path:
        return None
    if path.startswith("/"):
        path = path[1:]
    elif path.startswith("./") or path.startswith("../"):
        base = Path(current_page_dir).parent
        path = str((base / path).as_posix())
        parts = []
        for part in path.split("/"):
            if part == "..":
                if parts:
                    parts.pop()
            elif part and part != ".":
                parts.append(part)
        path = "/".join(parts)
    if path.endswith((".js", ".wxml", ".wxss", ".json")):
        path = path.rsplit(".", 1)[0]
    return path or None


def extract_navigation_paths(text: str, current_page_dir: str) -> Set[str]:
    paths: Set[str] = set()
    for match in re.finditer(r"\burl\s*:\s*['\"]([^'\"]+)['\"]", text):
        path = normalize_mini_program_path(match.group(1), current_page_dir)
        if path:
            paths.add(path)
    for match in re.finditer(r"\burl\s*=\s*['\"]([^'\"]+)['\"]", text):
        path = normalize_mini_program_path(match.group(1), current_page_dir)
        if path:
            paths.add(path)
    return paths


def extract_component_paths(json_text: str, current_file: str) -> Dict[str, str]:
    try:
        data = json.loads(json_text or "{}")
    except json.JSONDecodeError:
        return {"__json_error__": f"{current_file} 不是合法 JSON"}
    using = data.get("usingComponents", {})
    if not isinstance(using, dict):
        return {"__json_error__": f"{current_file} 的 usingComponents 必须是对象"}
    return {str(name): str(path) for name, path in using.items()}


def normalize_component_file_path(raw_path: str, current_file: str) -> Optional[str]:
    path = raw_path.strip()
    if not path or path.startswith(("plugin://", "weui-miniprogram/")):
        return None
    if path.startswith("/"):
        path = path[1:]
    else:
        path = str((Path(current_file).parent / path).as_posix())
    parts = []
    for part in path.split("/"):
        if part == "..":
            if parts:
                parts.pop()
        elif part and part != ".":
            parts.append(part)
    path = "/".join(parts)
    if path.endswith((".js", ".json", ".wxml", ".wxss")):
        path = path.rsplit(".", 1)[0]
    return path or None


def extract_cloud_functions(text: str) -> Set[str]:
    return set(
        match.group(1)
        for match in re.finditer(r"callFunction\s*\(\s*\{[^{}]*?\bname\s*:\s*['\"]([^'\"]+)['\"]", text, re.S)
    )


def extract_db_collections(text: str) -> Set[str]:
    return set(
        match.group(1)
        for match in re.finditer(r"\.collection\s*\(\s*['\"]([^'\"]+)['\"]\s*\)", text)
    )


def validate_page_bundle(
    page_dir: str,
    generated_page_files: List[Dict[str, str]],
    file_list: List[Dict[str, Any]],
) -> List[str]:
    errors: List[str] = []
    files = content_by_path(generated_page_files)
    js_path = f"{page_dir}.js"
    wxml_path = f"{page_dir}.wxml"
    json_path = f"{page_dir}.json"
    js = files.get(js_path, "")
    wxml = files.get(wxml_path, "")
    page_json = files.get(json_path, "{}")

    planned_paths = {item["path"] for item in file_list}
    planned_pages = set(collect_page_dirs(file_list).keys())
    planned_component_bases = {
        path.rsplit(".", 1)[0]
        for path in planned_paths
        if path.startswith("components/")
    }
    planned_cloud_functions = {
        path.split("/")[1]
        for path in planned_paths
        if path.startswith("cloudfunctions/") and len(path.split("/")) >= 2
    }

    handlers = extract_wxml_event_handlers(wxml)
    methods = extract_js_page_methods(js)
    missing_handlers = sorted(handler for handler in handlers if handler not in methods)
    if missing_handlers:
        errors.append(
            f"事件一致性错误：{wxml_path} 绑定了 {missing_handlers}，但 {js_path} 中没有同名方法。"
        )

    nav_paths = extract_navigation_paths(js, page_dir) | extract_navigation_paths(wxml, page_dir)
    bad_nav_paths = sorted(path for path in nav_paths if path not in planned_pages)
    if bad_nav_paths:
        errors.append(
            f"路径一致性错误：页面跳转引用了未在 app.json/file_plan 中声明的页面 {bad_nav_paths}。"
        )

    if VALIDATION_LEVEL in {"balanced", "strict"}:
        components = extract_component_paths(page_json, json_path)
        if "__json_error__" in components:
            errors.append(f"组件一致性错误：{components['__json_error__']}。")
        else:
            bad_components = []
            for name, raw_path in components.items():
                component_base = normalize_component_file_path(raw_path, json_path)
                if component_base and component_base not in planned_component_bases:
                    bad_components.append(f"{name}: {raw_path}")
            if bad_components:
                errors.append(
                    f"组件一致性错误：usingComponents 引用了文件清单外组件 {bad_components}。"
                )

        called_functions = extract_cloud_functions(js)
        bad_functions = sorted(
            name for name in called_functions if name not in planned_cloud_functions
        )
        if bad_functions:
            errors.append(
                f"云函数一致性错误：调用了未在文件清单中声明的云函数 {bad_functions}。"
            )

    if VALIDATION_LEVEL in {"balanced", "strict"}:
        collections = sorted(extract_db_collections(js))
        max_collections = 6 if VALIDATION_LEVEL == "strict" else 8
        if len(collections) > max_collections:
            errors.append(
                f"数据库集合一致性错误：单页引用集合过多 {collections}，请复用核心集合并保持字段一致。"
            )

    return errors


def format_validation_feedback(errors: List[str]) -> str:
    if not errors:
        return ""
    return "上一轮生成未通过一致性校验，请修复以下问题：\n" + "\n".join(
        f"{idx}. {error}" for idx, error in enumerate(errors, start=1)
    )


def group_page_files(files: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for item in files:
        page_dir = page_dir_from_path(item["path"])
        if page_dir:
            grouped.setdefault(page_dir, []).append(item)

    ext_order = {".js": 0, ".wxml": 1, ".wxss": 2, ".json": 3}
    for page_dir, items in grouped.items():
        items.sort(key=lambda x: ext_order.get(get_extension(x["path"]), 99))
    return grouped


def register_generated_file(
    generated_files_map: Dict[str, Dict[str, Any]],
    path: str,
    content: str,
    purpose: str = "",
):
    generated_files_map[path] = {
        "path": path,
        "purpose": purpose,
        "type": infer_type_from_path(path),
        "content": content,
    }


# =========================
# 10. 运行工具
# =========================
def run_single_task(task: Task, agent, verbose: bool = False):
    crew = Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        verbose=verbose,
        memory=False,
    )
    return crew.kickoff()


# =========================
# 11. 主流程
# =========================
def run_generation(
    initial_requirement: Optional[str] = None,
    interactive_requirement: bool = True,
    output_dir: Optional[str] = None,
    quality_level: Optional[str] = None,
):
    global OUTPUT_DIR

    configure_quality(quality_level)

    if output_dir:
        OUTPUT_DIR = output_dir

    requirement_text = (initial_requirement or user_requirement).strip()
    if not requirement_text:
        requirement_text = user_requirement

    init_artifact_dir()
    save_artifact_text("input_requirement.md", requirement_text)
    print(
        f"==== 质量档位：{QUALITY_LEVEL} | max_pages={MAX_PAGE_COUNT} | deps={MAX_DEP_CONTEXT} | retries={RETRY_TIMES} ===="
    )

    # -------- Stage 1: 需求分析（只跑一次）--------
    requirement_task = build_requirement_task(
        requirement_text, human_input=interactive_requirement
    )
    stage_1_label = "交互式需求分析" if interactive_requirement else "需求分析"
    print(f"==== Stage 1：开始{stage_1_label} ====")
    requirement_result = run_single_task(requirement_task, user_agent, verbose=True)
    save_artifact_text("requirement_analysis.md", requirement_result)
    print("\n==== 需求分析完成 ====\n")

    # -------- Stage 2: 架构设计（只跑一次）--------
    architecture_task = build_architecture_task(str(requirement_result))
    print("==== Stage 2：开始架构设计 ====")
    architecture_result = run_single_task(
        architecture_task, organizer_agent, verbose=True
    )
    save_artifact_text("architecture.md", architecture_result)
    print("\n==== 架构设计完成 ====\n")

    # -------- Stage 3: 文件清单（只跑一次）--------
    file_plan_task = build_file_plan_task(str(architecture_result))
    print("==== Stage 3：生成文件清单 ====")
    file_plan_result = run_single_task(
        file_plan_task, file_planner_agent, verbose=False
    )
    file_plan_data = safe_json_loads(file_plan_result)
    save_artifact_json("file_plan_raw.json", file_plan_data)
    file_list = file_plan_data.get("files", [])

    if not file_list:
        raise RuntimeError("文件清单为空，程序终止。")

    for f in file_list:
        if "type" not in f:
            f["type"] = infer_type_from_path(f["path"])

    schema_result = validate_file_plan_schema(file_list)
    file_list = schema_result["files"]
    save_artifact_json("file_plan_schema_report.json", schema_result["report"])

    raw_page_dirs = collect_page_dirs(dedupe_file_items(file_list))
    print(f"模型规划页面数：{len(raw_page_dirs)}")

    file_list = compress_file_plan(file_list, max_pages=MAX_PAGE_COUNT)

    compressed_page_dirs = collect_page_dirs(dedupe_file_items(file_list))
    print(f"最终页面数：{len(compressed_page_dirs)}")

    file_list = sort_file_plan(file_list)
    save_artifact_json("file_plan_validated.json", {"files": file_list})

    print("\n==== 文件清单获取完成（轻度整理后） ====\n")
    print(json.dumps({"files": file_list}, ensure_ascii=False, indent=2))

    # -------- Stage 3.5: 压缩代码生成上下文 --------
    print("\n==== Stage 3.5：压缩需求与架构上下文 ====\n")
    codegen_context_task = build_codegen_context_task(
        requirement_result=str(requirement_result),
        architecture_result=str(architecture_result),
    )
    codegen_context_result = run_single_task(
        codegen_context_task, codegen_context_agent, verbose=False
    )
    save_artifact_json("codegen_context_raw.json", safe_json_loads(codegen_context_result))
    codegen_context = normalize_codegen_context(safe_json_loads(codegen_context_result))
    save_artifact_json("codegen_context.json", codegen_context)

    print("==== 代码生成上下文压缩完成 ====")
    print(json.dumps(codegen_context, ensure_ascii=False, indent=2))

    # -------- Stage 4: 根级工程配置模板 --------
    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    write_app_templates(OUTPUT_DIR, file_list)
    write_project_config(
        output_dir=OUTPUT_DIR,
        projectname="generated_mini_program",
        appid="touristappid",
        miniprogram_root="./",
    )
    write_sitemap_json(OUTPUT_DIR)

    # -------- Stage 5: 页面四件套成组生成 --------
    print("\n==== Stage 5：开始页面四件套成组生成 ====\n")

    generated_files_map: Dict[str, Dict[str, Any]] = {}
    validation_reports: List[Dict[str, Any]] = []
    file_info_by_path = {item["path"]: item for item in file_list}
    for root_path in ["app.json", "app.js", "app.wxss"]:
        content = read_file(root_path)
        if content is not None:
            register_generated_file(
                generated_files_map,
                root_path,
                content,
                file_info_by_path.get(root_path, {}).get("purpose", ""),
            )

    file_plan_raw = json.dumps(
        {"files": file_list}, ensure_ascii=False, separators=(",", ":")
    )

    page_groups = group_page_files(file_list)
    save_artifact_json(
        "page_generation_order.json",
        [{"page_dir": page_dir, "files": [item["path"] for item in page_files]} for page_dir, page_files in page_groups.items()],
    )
    for idx, (page_dir, page_files) in enumerate(page_groups.items(), start=1):
        existing_contents = {item["path"]: read_file(item["path"]) for item in page_files}
        if all(content is not None for content in existing_contents.values()):
            print(f"[SKIP] 跳过已存在页面四件套: {page_dir}")
            validation_reports.append(
                {
                    "page_dir": page_dir,
                    "status": "skipped_existing",
                    "attempts": 0,
                    "errors": [],
                }
            )
            save_artifact_json("validation_report.json", validation_reports)
            for item in page_files:
                register_generated_file(
                    generated_files_map,
                    item["path"],
                    existing_contents[item["path"]] or "",
                    item.get("purpose", ""),
                )
            continue

        dependency_context_text = build_page_dependency_context(
            page_dir=page_dir,
            generated_files_map=generated_files_map,
            max_files=MAX_DEP_CONTEXT,
        )
        page_context = build_page_bundle_context(
            page_dir=page_dir, page_files=page_files, codegen_context=codegen_context
        )
        success = False
        last_error = None
        validation_feedback = ""
        for retry in range(RETRY_TIMES):
            try:
                print(
                    f"[{idx}/{len(page_groups)}] 正在生成页面四件套: {page_dir} (尝试 {retry + 1}/{RETRY_TIMES})"
                )
                page_task = build_page_bundle_task(
                    page_dir=page_dir,
                    page_files=page_files,
                    page_context=page_context,
                    file_plan_raw=file_plan_raw,
                    dependency_context_text=dependency_context_text,
                    validation_feedback=validation_feedback,
                )
                result = run_single_task(page_task, code_agent, verbose=False)
                generated_page_files = normalize_page_bundle_result(
                    page_dir, page_files, result
                )
                validation_errors = validate_page_bundle(
                    page_dir, generated_page_files, file_list
                )
                if validation_errors:
                    validation_reports.append(
                        {
                            "page_dir": page_dir,
                            "status": "retry",
                            "attempt": retry + 1,
                            "errors": validation_errors,
                        }
                    )
                    save_artifact_json("validation_report.json", validation_reports)
                    validation_feedback = format_validation_feedback(validation_errors)
                    raise RuntimeError(validation_feedback)

                for generated in generated_page_files:
                    file_info = file_info_by_path.get(generated["path"], {})
                    save_one_file(generated["path"], generated["content"])
                    register_generated_file(
                        generated_files_map,
                        generated["path"],
                        generated["content"],
                        file_info.get("purpose", ""),
                    )

                success = True
                validation_reports.append(
                    {
                        "page_dir": page_dir,
                        "status": "passed",
                        "attempts": retry + 1,
                        "errors": [],
                    }
                )
                save_artifact_json("validation_report.json", validation_reports)
                break
            except Exception as e:
                last_error = e
                print(f"[ERROR] 页面生成失败: {page_dir}，错误: {e}")

        if not success:
            validation_reports.append(
                {
                    "page_dir": page_dir,
                    "status": "failed",
                    "attempts": RETRY_TIMES,
                    "errors": [str(last_error)],
                }
            )
            save_artifact_json("validation_report.json", validation_reports)
            raise RuntimeError(f"页面生成失败，程序终止：{page_dir}") from last_error

    remaining_files = [
        item
        for item in file_list
        if item["path"] not in ["app.json", "app.js", "app.wxss"]
        and not page_dir_from_path(item["path"])
    ]

    if remaining_files:
        print("\n==== Stage 6：生成组件和非页面文件 ====\n")

    for idx, file_info in enumerate(remaining_files, start=1):
        path = file_info["path"]

        existing = read_file(path)
        if existing is not None:
            print(f"[SKIP] 跳过已存在文件: {path}")
            register_generated_file(
                generated_files_map, path, existing, file_info.get("purpose", "")
            )
            continue

        dependency_context_text = build_dependency_context(
            current_path=path,
            generated_files_map=generated_files_map,
            max_files=MAX_DEP_CONTEXT,
        )

        file_specific_context = build_file_specific_context(
            path=path, file_info=file_info, codegen_context=codegen_context
        )

        single_task = build_single_file_task(
            file_info=file_info,
            file_specific_context=file_specific_context,
            file_plan_raw=file_plan_raw,
            dependency_context_text=dependency_context_text,
        )

        success = False
        last_error = None

        for retry in range(RETRY_TIMES):
            try:
                print(
                    f"[{idx}/{len(file_list)}] 正在生成: {path} (尝试 {retry + 1}/{RETRY_TIMES})"
                )
                result = run_single_task(single_task, code_agent, verbose=False)

                data = safe_json_loads(result)
                model_path = data.get("path")
                content = data["content"]

                file_path = normalize_generated_path(path, model_path)
                save_one_file(file_path, content)

                register_generated_file(
                    generated_files_map, file_path, content, file_info.get("purpose", "")
                )

                success = True
                break

            except Exception as e:
                last_error = e
                print(f"[ERROR] 生成失败: {path}，错误: {e}")

        if not success:
            raise RuntimeError(f"文件生成失败，程序终止：{path}") from last_error

    save_artifact_json(
        "generated_files_summary.json",
        [
            {
                "path": item["path"],
                "type": item.get("type", ""),
                "purpose": item.get("purpose", ""),
                "content_chars": len(item.get("content", "")),
            }
            for item in generated_files_map.values()
        ],
    )
    print("\n[DONE] 项目生成完成！")


if __name__ == "__main__":
    run_generation()
