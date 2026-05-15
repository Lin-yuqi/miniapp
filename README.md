# CrewAI 微信小程序生成器

本项目是一个基于 `CrewAI` 与 `DeepSeek` 的微信小程序生成工具。系统接收自然语言需求，通过多 Agent 协作完成需求分析、架构设计、文件规划、上下文整理、页面生成与一致性校验，最终输出一个可导入微信开发者工具的小程序工程。

项目同时提供本地 Web UI 与命令行两种使用方式。Web UI 支持与 AI 多轮交流，先将模糊想法整理为完整生成方案，再按所选质量档位执行生成；命令行模式保留 CrewAI 原生的人机交互流程，适合调试提示词与观察各阶段输出。

## 功能概览

- 多轮需求澄清：在 Web UI 中通过 AI 对话逐步明确项目目标、用户角色、页面结构、数据模型与技术约束。
- 分阶段生成：依次执行需求分析、架构设计、文件规划、上下文整理、页面四件套生成与一致性校验。
- 页面级代码生成：全局 `app.js`、`app.json`、`app.wxss` 使用固定模板生成；页面代码按 `.js/.wxml/.wxss/.json` 四件套成组生成，以提升页面内部一致性。
- 文件清单校验：对模型输出的文件清单进行 schema 校验、轻度修复与必要补齐。
- 一致性校验与重试：检查事件、页面路径、组件、云函数和数据库集合等常见硬性错误，并将错误反馈给模型重试生成。
- 质量档位控制：提供 `fast`、`balanced`、`quality` 三档，以便在 token 消耗与生成质量之间进行取舍。
- 中间产物留存：生成过程中的关键文档、文件清单、上下文、校验报告和生成摘要会保存到本地，便于复盘与调试。

## 项目优势

- 需求输入门槛较低：用户可以先描述一个粗略想法，再通过 AI 追问逐步形成完整方案。
- 生成结果更易维护：页面按四件套成组生成，减少事件名、数据字段、页面结构和样式之间的不一致。
- 质量可控：通过质量档位在生成速度、token 消耗、上下文长度和校验强度之间做取舍。
- 错误可追踪：中间产物和校验报告会完整保存，便于定位问题发生在需求、架构、文件规划还是代码生成阶段。
- 面向微信小程序工程约束：内置页面路径、组件引用、云函数调用和数据库集合等一致性检查。
- 本地运行、便于二次开发：核心逻辑集中在 `main.py` 和 `ui.py`，可按实际模型、生成规则和校验策略继续扩展。

## 快速上手

以下步骤适合首次在 Windows 本地运行项目：

1. 进入项目根目录。

```powershell
cd C:\path\to\miniapp
```

2. 配置 DeepSeek API Key。

```powershell
$env:DEEPSEEK_API_KEY="your_api_key"
```

3. 安装并同步依赖。项目推荐使用 `uv`，并将虚拟环境固定在项目内的 `.uv-env/` 目录。

```powershell
$env:UV_PROJECT_ENVIRONMENT="$PWD\.uv-env"
uv sync
```

4. 启动 Web UI。

```powershell
uv run python ui.py
```

也可以在项目根目录直接双击：

```text
start_ui.bat
```

5. 打开本地页面并开始描述小程序需求。

```text
http://127.0.0.1:7860
```

生成完成后，默认小程序工程会输出到：

```text
generated_mini_program/
```

生成过程记录、需求分析、文件规划和校验报告会保存在：

```text
.crew_state/latest_generation/
```

如果只想在命令行观察 CrewAI 原生流程，可以运行：

```powershell
$env:UV_PROJECT_ENVIRONMENT="$PWD\.uv-env"
uv run python main.py
```

## 生成流程

系统默认执行以下 6 个阶段：

1. 需求分析：将用户输入整理为结构化需求。Web UI 模式会先通过 AI 对话形成完整生成方案。
2. 架构设计：规划页面、模块、数据结构、接口、用户流程与技术选型。
3. 文件规划：生成小程序工程文件清单，并执行 schema 校验和轻度修复。
4. 上下文整理：提取代码生成所需的核心业务信息、数据模型、页面关系和工程约束。
5. 页面生成：固定生成全局三件套，并按页面四件套成组生成页面代码。
6. 一致性校验：检查页面内部及文件清单相关的一致性问题；失败时将错误信息反馈给模型并重试。

默认输出目录为：

```text
generated_mini_program/
```

系统会自动生成或补齐以下基础文件：

- `app.js`
- `app.json`
- `app.wxss`
- `project.config.json`
- `sitemap.json`

## 中间产物

每次生成都会将关键中间产物写入：

```text
.crew_state/latest_generation/
```

常见文件如下：

- `manifest.json`：本次生成的时间、质量档位、页面上限、重试次数等运行参数。
- `input_requirement.md`：输入生成流程的原始需求或 Web UI 汇总方案。
- `requirement_analysis.md`：需求分析阶段输出。
- `architecture.md`：架构设计阶段输出。
- `file_plan_raw.json`：模型原始文件清单。
- `file_plan_schema_report.json`：文件清单 schema 校验和自动修复报告。
- `file_plan_validated.json`：校验、补齐和排序后的最终文件清单。
- `codegen_context_raw.json`：模型原始代码生成上下文。
- `codegen_context.json`：规范化后的代码生成上下文。
- `page_generation_order.json`：实际页面生成顺序。
- `validation_report.json`：页面一致性校验与重试记录。
- `generated_files_summary.json`：生成文件摘要。

这些产物用于定位生成质量问题。例如，可以判断问题来自需求分析、架构设计、文件规划、上下文整理，还是页面代码生成阶段。

## 目录结构

```text
.
├─ assets/                         # 项目图标和通用静态资源
├─ docs/                           # 设计文档、作品介绍、示例输出和演示资料
├─ main.py                         # CrewAI 生成主流程
├─ ui.py                           # 本地 Web UI 和需求对话服务
├─ start_ui.bat                    # Windows 一键启动脚本
├─ pyproject.toml                  # uv 项目配置和依赖声明
├─ requirements.txt                # pip 兼容依赖列表
├─ uv.lock                         # uv 锁定文件
├─ .gitignore                      # Git 忽略规则，已排除视频和本地运行产物
├─ .crew_state/                    # 本地生成记录，运行后产生，不上传
├─ .tmp/                           # 临时文件目录，不上传
├─ .venv/ 或 .uv-env/              # 本地 Python 虚拟环境，不上传
└─ generated_mini_program/         # 默认生成的小程序工程目录，运行后产生
```

核心文件说明：

- `main.py`：负责需求分析、架构设计、文件规划、页面生成、校验、重试与中间产物保存。
- `ui.py`：提供本地 Web UI、AI 需求对话、任务状态轮询、日志清洗和对话区进度通知。
- `start_ui.bat`：设置 Windows 启动环境并优先使用项目内 `.uv-env` 运行 Web UI。
- `docs/`：保存项目说明文档、演示材料、示例小程序输出和作品介绍资料；视频文件已通过 `.gitignore` 排除，不会上传到 GitHub。
- `assets/`：保存项目展示或界面中复用的图片、图标等资源。

## 环境要求

建议使用以下环境：

- Python 3.10 至 3.13
- `uv`
- 可访问 DeepSeek API 的网络环境
- 已配置 `DEEPSEEK_API_KEY`

相关官方入口：

- [`uv` 官方文档](https://docs.astral.sh/uv/)
- [`uv` 安装说明](https://docs.astral.sh/uv/getting-started/installation/)
- [DeepSeek API 文档](https://api-docs.deepseek.com/)
- [DeepSeek API 参考](https://api-docs.deepseek.com/api/deepseek-api)
- [DeepSeek 开放平台入口](https://www.deepseek.com/api-docs)

检查 `uv`：

```powershell
uv --version
```

## 安装依赖

推荐使用 `uv` 安装和同步依赖：

```powershell
$env:UV_PROJECT_ENVIRONMENT="$PWD\.uv-env"
uv sync
```

也可以直接运行 Web UI，首次运行时 `uv` 会根据 `pyproject.toml` 创建或同步环境：

```powershell
$env:UV_PROJECT_ENVIRONMENT="$PWD\.uv-env"
uv run python ui.py
```

`requirements.txt` 保留用于传统 pip 工作流兼容，但推荐优先使用 `uv`。

## 环境变量

运行前必须设置 DeepSeek API Key：

```powershell
$env:DEEPSEEK_API_KEY="your_api_key"
```

可选配置：

```powershell
$env:GENERATION_QUALITY="balanced"
```

质量档位说明：

| 档位 | 页面上限 | 依赖上下文 | 重试次数 | 校验强度 | 适用场景 |
| --- | ---: | ---: | ---: | --- | --- |
| `fast` | 8 | 4 | 2 | 基础校验 | 节省 token，快速试跑 |
| `balanced` | 10 | 6 | 3 | 常规校验 | 默认推荐，质量与消耗均衡 |
| `quality` | 14 | 8 | 4 | 严格校验 | 更关注完整性和一致性 |

当前默认模型配置：

- 模型：`deepseek-v4-flash`
- Base URL：`https://api.deepseek.com/v1`
- 输出目录：`generated_mini_program`
- 默认质量档位：`balanced`

## 启动 Web UI

### 双击启动

在项目根目录双击：

```text
start_ui.bat
```

启动脚本会执行以下处理：

- 设置 `PYTHONUTF8=1` 和 `PYTHONIOENCODING=UTF8`
- 设置 `UV_PROJECT_ENVIRONMENT=%CD%\.uv-env`
- 优先使用 `.uv-env\Scripts\python.exe ui.py`
- 如果项目环境不可用，则回退到 `uv run python ui.py`
- 再依次尝试 `.venv\Scripts\python.exe`、`python` 和 `py`

### 命令启动

```powershell
$env:UV_PROJECT_ENVIRONMENT="$PWD\.uv-env"
uv run python ui.py
```

启动后访问：

```text
http://127.0.0.1:7860
```

Web UI 提供以下能力：

- 与 AI 多轮交流并整理完整生成方案
- 选择质量档位：省 token、均衡、高质量
- 按方案启动生成任务
- 查看实时运行日志
- 在对话区同步显示关键生成进度
- 查看生成完成或失败状态

## 命令行运行

命令行模式适合开发调试或观察 CrewAI 原生输出。

```powershell
$env:UV_PROJECT_ENVIRONMENT="$PWD\.uv-env"
uv run python main.py
```

可以通过环境变量传入初始需求：

```powershell
$env:UV_PROJECT_ENVIRONMENT="$PWD\.uv-env"
$env:USER_REQUIREMENT="我想开发一个健身打卡微信小程序，支持计划、打卡、统计和个人中心。"
uv run python main.py
```

注意：命令行模式下，需求分析阶段默认 `human_input=True`，运行过程中可能需要在终端继续补充需求。

## Web UI 与命令行差异

| 模式 | 特点 | 适用场景 |
| --- | --- | --- |
| Web UI | 先与 AI 多轮沟通，生成阶段不会卡在 CrewAI 人工输入；支持质量档位、日志清洗和对话区进度通知 | 面向普通使用者或快速生成完整项目 |
| 命令行 | 保留 CrewAI 原生交互，更便于观察 Agent 输出和调试提示词 | 面向开发者调试、提示词优化和流程验证 |

## 文件清单校验

文件清单阶段会执行 schema 校验和轻度修复：

- 检查 `files` 是否为数组。
- 检查每个文件项是否包含合法 `path`。
- 自动补齐 `app.js`、`app.json`、`app.wxss`。
- 自动补齐页面四件套。
- 自动补齐组件四件套。
- 自动补齐云函数 `index.js`。
- 忽略 `project.config.json` 和 `sitemap.json`，这两个文件由系统模板生成。
- 拒绝绝对路径、包含 `..` 的路径和缺少扩展名的路径。

校验结果会写入：

```text
.crew_state/latest_generation/file_plan_schema_report.json
```

## 一致性校验

页面四件套生成后，系统会在保存前执行轻量一致性校验：

- 事件一致：WXML 中绑定的事件必须在对应 JS 中存在。
- 路径一致：页面跳转必须指向文件清单中的页面。
- 组件一致：`usingComponents` 不应引用文件清单外的组件。
- 云函数一致：`wx.cloud.callFunction` 调用的云函数必须在文件清单中声明。
- 数据库集合一致：避免单页生成过多零散集合，促使模型复用核心集合和字段。

如果校验失败，系统不会保存该轮页面文件，而是将错误信息作为反馈传入下一轮同页面生成任务。校验和重试记录会写入：

```text
.crew_state/latest_generation/validation_report.json
```

## 需求描述建议

为提高生成质量，建议在需求中尽量说明以下内容：

- 项目目标：小程序服务的对象及要解决的问题。
- 用户角色：普通用户、管理员、商家、游客等。
- 核心页面：首页、列表、详情、发布、个人中心等。
- 关键功能：搜索、收藏、评论、支付、审核、统计、上传等。
- 数据来源：微信云开发、后端 API、本地缓存或 mock 数据。
- 技术限制：是否需要登录、权限控制、管理端、云函数、数据库集合等。

示例：

```text
我想做一个校园二手书交换微信小程序。学生可以发布书籍、浏览和搜索书籍、查看详情、收藏、留言联系；管理员可以查看举报并处理违规书籍。需要首页推荐、搜索列表、书籍详情、发布/编辑、消息或评论、个人中心。优先使用微信云开发。
```

## 常见问题

### UI 启动后生成失败

请优先检查以下项目：

- `DEEPSEEK_API_KEY` 是否已经设置。
- 当前网络是否可以访问 DeepSeek API。
- `uv sync` 是否成功安装依赖。
- 右侧运行日志中是否出现模型调用错误。

### Web UI 无法自动打开浏览器

可以手动访问：

```text
http://127.0.0.1:7860
```

如果端口被占用，请先关闭已有的 `ui.py` 进程，或修改 `ui.py` 中的 `PORT`。

### 日志出现乱码或控制字符

Web UI 会对日志进行清洗，包括移除常见 ANSI 控制符，并尝试修复常见 UTF-8 误解码。`start_ui.bat` 也会设置 UTF-8 相关环境变量。

如仍出现乱码，可在 PowerShell 中手动设置：

```powershell
$env:PYTHONUTF8="1"
$env:PYTHONIOENCODING="utf-8"
```

### 生成过程耗时较长

这是正常现象。项目需要依次完成需求分析、架构设计、文件规划、上下文整理、页面生成和一致性校验。页面数量、组件数量、质量档位和校验重试次数都会影响耗时。

### 生成结果不符合预期

建议从以下方向调整：

- 在 Web UI 中继续与 AI 澄清需求后再生成。
- 明确核心页面和主流程。
- 指定数据来源和是否使用微信云开发。
- 降低边缘功能数量，先生成主流程，再迭代扩展。
- 查看 `.crew_state/latest_generation/` 中的中间产物，定位偏差发生阶段。

### 已有文件被跳过

`main.py` 会跳过 `generated_mini_program/` 中已经完整存在的页面四件套和非页面文件。全局 `app.js`、`app.json`、`app.wxss` 会根据当前文件清单固定模板刷新。如需完整重新生成，请先清理输出目录。

## 后续改进方向

- 增加 `.env` 文件支持。
- 增加生成任务历史记录。
- 增加项目级一致性校验和自动修复。
- 支持对已有小程序项目进行增量生成。
- 在 Web UI 中支持选择输出目录和模型参数。

## 致谢
@lyc-cafard

