# Agent MCP Skill Demo

这是一个基于 `doc.md` 整理出的 Python GitHub 项目示例。项目用 MCP Server 暴露工具，用 Markdown Skill 描述执行流程，模型侧通过 OpenAI Python SDK 访问任意兼容 Chat Completions 的服务。

也就是说，运行时不绑定 Ollama。你可以使用 OpenAI 官方 API，也可以使用任何 OpenAI SDK 兼容的 `/v1` 接口，例如本地模型服务、私有网关或第三方兼容服务。

![](demo.png)

## 项目结构

```text
.
├── config.json                  # 默认配置
├── .env.example                 # 环境变量模板
├── requirements.txt             # 直接安装依赖
├── pyproject.toml               # 包元数据和 CLI 入口
├── orchestrator.py              # 根目录运行入口
├── mcp_servers/
│   ├── holidays_server.py       # 公共假日 API MCP Server
│   └── ops_server.py            # 本地 SQLite 运维数据 MCP Server
├── scripts/
│   ├── seed_db.py               # 生成示例 ops.db
│   └── server_test.py           # 直接调用 MCP 工具的调试脚本
├── skills/
│   └── oncall_holiday_check.md  # 值班假日检查 Skill
└── src/
    └── agentic_stack/
        ├── config.py            # 配置和 .env 加载
        └── orchestrator.py      # Agent 编排器
```

## 环境变量

复制 `.env.example` 为 `.env` 后按需修改。`.env` 已被 `.gitignore` 忽略，适合放 API Key、本地路径和运行时配置。

```env
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4.1-mini
MAX_STEPS=10

PYTHON_EXECUTABLE=

SKILL_PATH=skills/oncall_holiday_check.md
DEFAULT_QUESTION=当前值班工程师所在国家今天是否有公共假日？如果有，列出他们名下的 P1 问题。

HOLIDAY_API_BASE=https://date.nager.at/api/v3
OPS_DB={root}/ops.db
```

使用 OpenAI 官方 API 时，填入 `OPENAI_API_KEY`，`OPENAI_BASE_URL` 可以保持默认值。使用兼容端点时，把 `OPENAI_BASE_URL` 改成对应 `/v1` 地址，并把 `OPENAI_MODEL` 改成该服务暴露的模型名。

例如 OpenAI SDK 兼容的本地端点：

```env
OPENAI_API_KEY=not-needed
OPENAI_BASE_URL=http://localhost:11434/v1
OPENAI_MODEL=qwen3.5:9b
```

`{root}` 会在代码中展开为项目根目录。未设置 `PYTHON_EXECUTABLE` 时，编排器会使用当前虚拟环境的 Python 解释器启动 MCP 子进程。

## 使用方式

安装依赖：

```bash
pip install -r requirements.txt
```

准备本地示例数据库：

```bash
python scripts/seed_db.py
```

示例数据库会写入中文工程师、国内运维问题和中国时区数据，便于直接演示本土化场景。

运行默认问题：

```bash
python orchestrator.py
```

传入自定义问题：

```bash
python orchestrator.py "当前值班工程师是否有 P1 问题需要处理？"
```

如果使用可编辑安装，也可以通过 CLI 入口运行：

```bash
pip install -e .
agentic-stack
```

## 实现说明

编排器只负责通用流程：读取配置、启动 MCP Server、收集工具 schema、把 Markdown Skill 注入 system prompt，并处理模型发起的工具调用。它不写死任何业务逻辑，也不绑定具体模型供应商。

模型调用位于 `src/agentic_stack/orchestrator.py`，使用 `openai.AsyncOpenAI.chat.completions.create(...)`。MCP 工具会被转换成 OpenAI Chat Completions 的 `tools` schema，模型返回 `tool_calls` 后，编排器调用对应 MCP Server，并用 `tool_call_id` 把结果写回对话。

两个 MCP Server 各自承担清晰职责：

- `holidays_server.py` 把 `date.nager.at` 公共假日 API 包装成 `is_public_holiday` 和 `list_country_holidays`，并内置 2026 年中国法定节假日演示数据。
- `ops_server.py` 查询本地 SQLite，暴露 `get_current_oncall`、`list_open_issues`、`get_engineer` 和 `list_engineers`。

业务流程写在 `skills/oncall_holiday_check.md` 中。要替换任务，可以新增 Skill 和 MCP Server，再在 `config.json` 或 `.env` 中切换路径与环境变量。

## 调试 MCP Server

可以用调试脚本直接调用单个 MCP 工具：

```bash
python scripts/server_test.py holidays
python scripts/server_test.py ops
```

也可以传入工具名和 JSON 参数：

```bash
python scripts/server_test.py holidays is_public_holiday "{\"country_code\":\"CN\",\"on_date\":\"2026-10-01\"}"
```

MCP Server 使用 stdio 通信，Server 代码里不要向 stdout 打印调试信息，否则会污染 JSON-RPC 协议通道。
