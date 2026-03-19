# 贡献指南

感谢你对 open-skills-host 的关注！我们欢迎任何形式的贡献，无论是报告 Bug、提出新功能建议，还是提交代码。

## 目录

- [开发环境设置](#开发环境设置)
- [项目结构](#项目结构)
- [开发工作流](#开发工作流)
- [代码规范](#代码规范)
- [提交 Pull Request](#提交-pull-request)
- [问题反馈](#问题反馈)

---

## 开发环境设置

### 前置要求

- **Python 3.12+**：本项目要求 Python 3.12 或更高版本
- **uv**：我们使用 [uv](https://docs.astral.sh/uv/) 作为包管理器（比 pip/poetry 更快）

#### 安装 uv

如果你还没有安装 uv，可以通过以下方式安装：

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# 或使用 pipx
pipx install uv
```

### 克隆仓库

```bash
git clone https://github.com/your-username/open-skills-host.git
cd open-skills-host
```

### 安装依赖

使用 uv 安装所有依赖（包括开发依赖）：

```bash
# 安装项目依赖
uv sync

# 如果需要开发依赖（如 pytest）
uv sync --group dev
```

> **注意**：`uv sync` 会自动创建虚拟环境并安装所有依赖，无需手动创建 venv。

### 配置环境变量

1. 复制环境变量模板：

```bash
cp .env.example .env
```

2. 编辑 `.env` 文件，配置以下必要参数：

```ini
# LLM API 配置（必填）
OPENAI_API_KEY=sk-your-api-key-here
OPENAI_API_BASE=https://api.openai.com/v1  # 或其他兼容 API

# 模型配置
LLM_MODEL=gpt-4o                           # 或 kimi-k2-0711-preview 等
LLM_TEMPERATURE=0.1

# 技能目录（必填）
SKILLS_DIR=./skills                        # 本地开发可使用相对路径

# 产出物目录
SKILLS_OUTPUT_DIR=./outputs
```

支持的 LLM 提供商：
- **OpenAI**: `https://api.openai.com/v1`
- **Moonshot (Kimi)**: `https://api.moonshot.cn/v1`
- **DeepSeek**: `https://api.deepseek.com/v1`
- **本地模型**: 通过 Ollama/vLLM 等部署

### 验证安装

```bash
# 列出可用技能（验证环境配置正确）
uv run main.py --list

# 运行测试
uv run pytest

# 启动开发服务器
uv run server.py --port 8000
```

---

## 项目结构

```
open-skills-host/
├── main.py               # CLI 入口
├── server.py             # HTTP 服务入口
├── core/                 # 核心模块
│   ├── config.py         # 配置管理
│   ├── models.py         # 数据模型
│   ├── discovery.py      # 技能发现
│   ├── parser.py         # SKILL.md 解析
│   └── errors.py         # 异常定义
├── agent/                # Agent 模块
│   ├── runner.py         # 技能执行器
│   ├── llm.py            # LLM 客户端
│   ├── tool_registry.py  # 工具注册
│   └── callbacks.py      # 回调处理
├── api/                  # HTTP API 模块
│   ├── main.py           # FastAPI 应用
│   ├── schemas.py        # API 模型
│   ├── cdn.py            # 文件上传
│   └── routes/           # 路由定义
└── tests/                # 测试目录（如有）
```

---

## 开发工作流

### 1. 创建分支

```bash
# 从 main 分支创建功能分支
git checkout main
git pull origin main
git checkout -b feature/your-feature-name
```

分支命名规范：
- `feature/xxx` - 新功能
- `fix/xxx` - Bug 修复
- `docs/xxx` - 文档更新
- `refactor/xxx` - 重构

### 2. 开发与测试

```bash
# 运行所有测试
uv run pytest

# 运行特定测试文件
uv run pytest tests/test_parser.py

# 运行带覆盖率的测试
uv run pytest --cov=core --cov=agent
```

### 3. 本地调试

```bash
# CLI 模式调试
uv run main.py --skill your-skill --request "测试请求" -v

# HTTP 模式调试
uv run server.py --port 8000
# 然后访问 http://localhost:8000/docs 查看 API 文档
```

---

## 代码规范

### Python 风格

- 遵循 [PEP 8](https://pep8.org/) 规范
- 使用类型注解（Type Hints）
- 函数和类需要写 docstring

### 提交信息格式

使用清晰的提交信息：

```
<type>: <description>

[optional body]
```

类型包括：
- `feat`: 新功能
- `fix`: Bug 修复
- `docs`: 文档更新
- `refactor`: 重构
- `test`: 测试相关
- `chore`: 构建/工具相关

示例：
```
feat: 支持技能执行超时配置

- 添加 SKILL_TIMEOUT 环境变量
- Agent 执行超时后自动终止
- 返回超时错误信息
```

---

## 提交 Pull Request

### 提交前检查清单

- [ ] 代码通过所有测试：`uv run pytest`
- [ ] 新功能包含测试用例
- [ ] 更新了相关文档
- [ ] 提交信息清晰明确

### PR 流程

1. 推送分支到远程仓库
2. 在 GitHub 上创建 Pull Request
3. 填写 PR 描述，说明改动内容
4. 等待 Code Review
5. 根据反馈修改后合并

---

## 问题反馈

### 报告 Bug

请在 [Issues](https://github.com/your-username/open-skills-host/issues) 中提交，包含：

- 问题描述
- 复现步骤
- 期望行为 vs 实际行为
- 环境信息（OS、Python 版本等）
- 相关日志或截图

### 功能建议

欢迎提出新功能想法！请描述：

- 使用场景
- 期望的行为
- 可能的实现方案（可选）

---

## 获取帮助

如果在贡献过程中遇到问题，可以：

1. 查看 [README.md](README.md) 中的常见问题
2. 在 Issues 中搜索是否有类似问题
3. 创建新 Issue 描述你的问题

再次感谢你的贡献！🎉
