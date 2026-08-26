# skynet-mcp-client

面向 skynet 游戏服务器的**对话式 MCP 图形化客户端**（非 coding agent）。

用户用自然语言直接控制 skynet debug console（无需"用 skynet 工具"提示词），
LLM 决策调用哪个 MCP 工具，危险命令弹审批卡人工确认，结果在对话里渲染成表格/图表，
所有调用落库可审计、会话可保存回放。

## 架构

```
浏览器 (React + Vite + Tailwind + ECharts)
   │  SSE (/api/chat, /api/human-feedback)
   ▼
FastAPI 后端 (Python)
   ├─ LangGraph Agent（LLM 决策 → 工具调用，危险命令 interrupt 审批）
   ├─ mcp SDK client（streamable-http）
   │        │  http://127.0.0.1:8765/mcp（WSL2 localhost 转发）
   │        ▼
   └─ skynet-mcp server（Linux 内，HTTP 模式）
               │  工具调用（每次一连接）
               ▼
      skynet debug console (127.0.0.1:8000)
```

- **后端**：Python 3.13 + FastAPI + LangChain/LangGraph + mcp SDK + SQLite（WAL）
- **前端**：React 19 + Vite + TS + Tailwind（照抄 NL2SQL-AI 的对话 UI 模式）+ ECharts
- **LLM**：OpenAI 兼容接口（.env 配置，如硅基流动/DeepSeek）

## 安装

```bash
# 1) Linux 内部署并启动 skynet-mcp server（HTTP 模式）
git clone https://github.com/losophy/skynet-mcp && cd skynet-mcp
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt   # 按项目实际依赖文件调整
.venv/bin/python -m skynet_mcp.main --http-port 8765

# 2) 客户端后端 venv
python.exe -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 3) 前端
cd frontend && npm install && npm run build && cd ..

# 4) 配置 LLM（复制 .env.example → .env，填 LLM_MODEL_NAME/LLM_API_KEY/LLM_BASE_URL）
```

## 启动

```powershell
# 一键：自动拉起 WSL server → 起后端 → 开浏览器
.\start.ps1

# 或手动
#   WSL 侧：起 HTTP server（见上）
#   后端：  .venv\Scripts\python.exe -m uvicorn backend.app:app --port 8100
#   前端：  cd frontend && npm run dev  （开发模式，代理 /api）
#   访问：  http://127.0.0.1:8100
```

## 配置（.env）

| 变量 | 说明 |
|---|---|
| `MCP_URL` | MCP server 端点，默认 `http://127.0.0.1:8765/mcp` |
| `CLIENT_HTTP_PORT` | 客户端 Web 端口，默认 `8100` |
| `LLM_MODEL_NAME` / `LLM_API_KEY` / `LLM_BASE_URL` | OpenAI 兼容 LLM（不配则对话不可用，但状态/工具接口可用） |

## API

| 接口 | 说明 |
|---|---|
| `POST /api/chat` | 对话（SSE：progress/result/human_approval/error/session_created） |
| `POST /api/human-feedback` | 危险命令审批（approve/reject）→ resume |
| `GET /api/status` `/api/tools` | 连接状态、工具列表（含危险等级） |
| `GET /api/sessions` `/api/sessions/{id}`（DELETE） | 会话管理 |
| `GET /api/calls` | 工具调用历史（全量） |
| `GET /api/audit` | 危险命令审计视图（只含 medium/high） |

## 测试

```bash
.venv\Scripts\python.exe -m pytest tests/ -q
.venv\Scripts\python.exe tests/test_api_e2e.py   # 端到端（mock MCP + fake LLM）
```

## 目录结构

```
backend/        FastAPI + LangGraph Agent + MCP client + parsers + db
frontend/       React 聊天 UI（SessionList / MessageBubble / HumanApprovalCard / ResultTable / ResultChart）
data/           SQLite（calls/messages/sessions，gitignore）
tests/          单元 + 集成测试
start.ps1       一键启动
```
