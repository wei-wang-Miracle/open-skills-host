# open-skills-host

**一个即插即用的 Agent Skill 执行宿主** — 让企业级 AI 智能引擎能够调用运行在远程服务器上的结构化技能。

[English](#english) | 简体中文

---

## 为什么需要它？

企业级 AI 智能引擎需要执行各类结构化 Skill（技能）来完成复杂任务。但这些技能**通常只能在本地运行**，难以满足企业级部署需求。

当你需要：

- 在 **无 GUI 的远程服务器** 上运行技能（生产环境部署）
- 把技能执行权交给**企业自研 AI 系统**（如智能客服、工作流引擎、RPA 平台）
- 通过 **HTTP API** 触发技能，集成到现有业务流程
- 让技能在**隔离环境**中运行，不受本地上下文干扰

open-skills-host 解决了这些问题。

---

## 它是什么？

> open-skills-host 是一个**外挂式 Skill 执行器**。

它不替代你的 AI 助手，而是作为一个独立的执行宿主：

1. **接收** 来自任意调用方的技能执行请求
2. **加载** 对应的 SKILL.md 指令文件
3. **驱动** 本地 LLM 执行技能（LangChain ReAct Agent）
4. **返回** 结构化结果（文本 或 文件产出物）

```
企业 AI 智能引擎 / 工作流平台 / 业务系统
         │
         │  POST /skills/invoke
         ▼
  open-skills-host (HTTP Server)
         │
         │  SKILL.md + ReAct Agent
         ▼
    LLM + 工具集（Shell、文件读写等）
         │
         ▼
    结构化执行结果 / 产出文件
```

---

## 核心特性

- **即插即用**：技能以 SKILL.md 文件定义，放入目录即可识别，无需注册
- **渐进式加载**：发现阶段只加载轻量元数据（~100 token），激活时才加载完整指令，节省 token
- **双模使用**：支持 CLI 本地调试 和 HTTP API 远程调用
- **结构化输出**：Agent 直接输出 `SkillExecutionResult` 模型，便于系统集成
- **OpenAI 兼容**：底层 LLM 使用 OpenAI 协议，兼容 Moonshot、DeepSeek、本地模型等
- **双层安全防护**：ReAct 推理层主动风险评估 + Shell 工具静态兜底拦截

---

## 快速开始

### 环境要求

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/)（推荐）或 pip

### 安装

```bash
git clone https://github.com/your-username/open-skills-host.git
cd open-skills-host
uv sync
```

### 配置

复制 `.env.example` 并填写你的配置：

```bash
cp .env.example .env
```

```ini
# LLM 配置（兼容 OpenAI 协议）
OPENAI_API_KEY=sk-your-key
OPENAI_API_BASE=https://api.moonshot.cn/v1
LLM_MODEL=kimi-k2-0711-preview
LLM_TEMPERATURE=0.1

# 技能目录（支持绝对路径、相对路径、~ 展开）
SKILLS_DIR=~/my-skills

# 产出文件保存目录
SKILLS_OUTPUT_DIR=~/outputs
```

### 准备技能

技能是一个包含 `SKILL.md` 的目录：

```
my-skills/
└── pdf-to-markdown/
    ├── SKILL.md          # 技能描述和执行指令
    └── scripts/
        └── convert.py   # 可选：辅助脚本
```

`SKILL.md` 格式：

```markdown
---
name: pdf-to-markdown
description: 将 PDF 文件转换为 Markdown 格式
---

## 指令

接收用户提供的 PDF 文件路径，调用 scripts/convert.py 完成转换，
将结果保存至 output_dir，返回 Markdown 文件路径。
```

### 运行

**CLI 模式**（本地调试）

```bash
# 列出所有可用技能
uv run main.py --list

# 执行技能
uv run main.py --skill pdf-to-markdown --request "把 ~/docs/report.pdf 转成 Markdown"
```

**HTTP 服务模式**

```bash
uv run server.py --host 0.0.0.0 --port 8000
```

调用示例：

```bash
curl -X POST http://localhost:8000/skills/invoke \
  -H "Content-Type: application/json" \
  -d '{
    "skill_name": "pdf-to-markdown",
    "request": "把这个 PDF 转成 Markdown",
    "input_files": ["https://example.com/report.pdf"]
  }'
```

响应：

```json
{
  "execution_id": "a1b2c3d4",
  "success": true,
  "artifact_type": "file",
  "download_url": "https://cdn.example.com/output/report.md",
  "summary": "已成功将 report.pdf 转换为 Markdown 格式"
}
```

---

## API 文档

服务启动后访问 `http://localhost:8000/docs` 查看交互式 API 文档。

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/skills` | 列出所有可用技能 |
| `GET` | `/skills/{name}` | 查看技能详情和指令 |
| `POST` | `/skills/invoke` | 执行技能 |

---

## 项目结构

```
open-skills-host/
├── main.py               # CLI 入口
├── server.py             # HTTP 服务入口
├── core/
│   ├── config.py         # 路径与环境变量
│   ├── models.py         # 数据模型
│   ├── discovery.py      # 技能扫描与发现
│   └── parser.py         # SKILL.md 解析（渐进式披露）
├── agent/
│   ├── runner.py         # 技能执行核心
│   ├── llm.py            # LLM 客户端
│   ├── tool_registry.py  # 通用工具集（Shell、文件读写等）
│   └── callbacks.py      # 执行事件日志
└── api/
    ├── main.py           # FastAPI 应用工厂
    ├── schemas.py        # 请求/响应模型
    ├── cdn.py            # 文件上传/下载
    └── routes/
        └── skills.py     # REST 端点
```

---

## 设计理念

### 分离决策与执行

open-skills-host 只负责**执行**，不负责**决策**。

决定"现在该调用哪个技能、用什么参数"是一个需要完整上下文的高阶推理任务，应该交给拥有完整对话上下文的智能引擎（企业 AI 智能引擎）来完成。open-skills-host 专注于接收明确的执行指令并可靠地完成它。

### 分离业务与工具

open-skills-host 只作为**工具**，不参与**业务编排**。

业务流程的设计、编排和状态管理是企业级 AI 智能引擎的核心职责。open-skills-host 定位为一个纯粹的工具执行层，提供标准化的技能执行能力，被上层业务系统按需调用。它不感知业务上下文，不维护业务流程状态，只确保每个技能被正确、安全、高效地执行。

这种分离使得：
- **业务层**可以灵活编排流程，根据业务需求自由组合技能
- **工具层**可以专注执行优化，提升技能运行的稳定性和性能
- 双方独立演进，业务逻辑变更不影响技能实现，技能升级不影响业务流程

### 技能格式

SKILL.md 采用标准化的技能定义格式，兼容主流 AI 编程助手的技能规范。这意味着：

- 在本地开发环境调试的技能，可以直接部署到 open-skills-host
- 开发环境与生产环境共享同一套技能库，无需维护两份定义

---

## 常见问题

**Q: 为什么不用 Agent Tool 来加载 SKILL.md 脚本？**

A: Agent Tool 的工作方式是将脚本内容注入到 LLM 上下文中，这会消耗大量 token，在批量加载或脚本较长时成本很高。open-skills-host 通过渐进式披露机制，发现阶段只读取轻量的 YAML 元数据（~100 token），激活时才加载完整指令，执行时才按需读取脚本文件，将 token 消耗降至最低。

**Q: 为什么不把所有技能都预加载给 Agent，让它综合使用？**

A: 这涉及架构设计的核心取舍：**决策与执行应该分离**。把所有技能都塞给一个 Agent，它既要理解完整的对话上下文，又要从大量技能中选择合适的，还要执行具体操作，职责过重，且上下文窗口会被大量技能描述占满，影响推理质量。更好的做法是：由拥有完整用户上下文的智能引擎（AI 助手）决定调用哪个技能，open-skills-host 专注执行，保持 Agent 上下文干净、推理精准。

**Q: 支持哪些 LLM？**

A: 任何兼容 OpenAI 协议的 LLM 都支持，包括 OpenAI、Moonshot (Kimi)、DeepSeek、Qwen、以及通过 vLLM/Ollama 部署的本地模型。在 `.env` 中配置 `OPENAI_API_BASE` 即可切换。

**Q: 技能执行是否有安全防护？**

A: 有双层防护。第一层是 ReAct 推理层：Agent 在执行有副作用的命令前会主动调用 `assess_command` 工具，获取风险评级（BLOCK/DANGER/CAUTION/SAFE）后再决策。第二层是静态兜底：Shell 工具对极端破坏性命令（如 `rm -rf /`）进行硬拦截，无论 Agent 如何推理都无法执行。

**Q: 技能产出文件如何传递给调用方？**

A: HTTP API 模式下，执行完成后会将产出文件上传至 CDN，在响应中返回 `download_url`。CLI 模式下，产出文件保存在 `SKILLS_OUTPUT_DIR` 指定的目录中，直接访问即可。

---

## 路线图

- [ ] **交互式技能执行**：支持技能执行过程中与用户多轮交互（当前版本为一次性执行）
- [ ] **沙箱隔离**：在 Docker 容器或独立虚拟环境中执行技能，进一步隔离执行环境与宿主系统
- [ ] **技能市场**：支持通过 URL 直接安装技能，构建技能共享生态
- [ ] **执行历史**：记录技能执行日志，支持查询和回放
- [ ] **并发控制**：细粒度的技能执行并发限制与队列管理
- [ ] **流式响应**：通过 SSE 实时推送执行进度，而不是等待最终结果

---

## 贡献

欢迎提交 Issue 和 Pull Request。

在提交 PR 之前，请确保：

1. 代码通过现有测试：`uv run pytest`
2. 新功能附带测试用例
3. 遵循现有代码风格

---

## License

MIT License

---

<a name="english"></a>

## English

**An out-of-process Skill executor for enterprise AI engines** — enables enterprise AI systems to invoke structured skills running on a remote server.

### The Problem

Enterprise AI engines need to execute various structured skills to complete complex tasks, but these skills often only run locally. If you need to run skills on production servers, integrate skill execution into existing business systems, workflow engines, or call skills via HTTP API, you need open-skills-host.

### What It Does

open-skills-host is a standalone execution host that:

1. **Receives** skill execution requests from any caller
2. **Loads** the corresponding SKILL.md instruction file
3. **Drives** a local LLM to execute the skill (LangChain ReAct Agent)
4. **Returns** structured results (text or file artifacts)

### Key Design Decision: Separate Decision from Execution

open-skills-host only handles **execution**, not **decision-making**.

Deciding which skill to call and with what parameters requires full conversation context — that's best left to your enterprise AI engine with its complete context. open-skills-host focuses on receiving clear execution instructions and completing them reliably.

This also answers why we don't preload all skills into a single Agent: loading all skills fills the context window with descriptions, degrades reasoning quality, and conflates decision-making with execution. A cleaner architecture is: your enterprise AI engine (with full context) decides what to call, open-skills-host executes it precisely.

### Roadmap

- Interactive skill execution (multi-turn during execution)
- Sandbox isolation (Docker containers)
- Skill marketplace (install via URL)
- Execution history and replay
- Streaming responses via SSE
