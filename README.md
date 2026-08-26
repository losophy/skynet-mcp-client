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

- **后端**：Python 3.12（uv 托管）+ FastAPI + LangChain/LangGraph + mcp SDK + SQLite（WAL）
- **前端**：React 19 + Vite + TS + Tailwind（照抄 NL2SQL-AI 的对话 UI 模式）+ ECharts
- **LLM**：OpenAI 兼容接口（.env 配置，如硅基流动/DeepSeek）

## 一次完整请求的链路

以「列出所有服务」为例，从输入到回显的完整流转：

```
你在浏览器输入 "列出所有服务"
        ↓
前端 React 把这个文本打包成 POST /api/chat 请求
        ↓
FastAPI 后端收到，交给 LangGraph Agent（LLM 大脑）
        ↓
Agent 决定调用 MCP 的 "list" 工具
        ↓
通过 MCP 协议（streamable-http）发给 skynet-mcp 服务端
        ↓
skynet-mcp 把 MCP 请求翻译成裸 socket POST 命令 "list"
        ↓
发给 skynet debug console（127.0.0.1:8000）
        ↓
skynet 执行 list，返回裸文本 + <CMD OK>
        ↓
skynet-mcp 解析裸文本，包装成 MCP 响应
        ↓
skynet-mcp-client 收到工具执行结果，回填给 Agent
        ↓
LLM 把原始数据翻译成中文："当前有 2 个服务：launcher 和 debug_console"
        ↓
通过 SSE 流式推送给前端
        ↓
浏览器把文字渲染成你看到的对话气泡
```

危险命令（如 kill / start）会在这条链路上多一步：Agent 发起调用前先弹出审批卡，等你点「批准执行」才继续往下执行。

## 安装

```bash
# 1) 手动拉起 skynet-mcp server（HTTP 模式 :8765）
#    部署与启动方式见 skynet-mcp 仓库 README：https://github.com/losophy/skynet-mcp
#    启动后确认 http://127.0.0.1:8765/mcp 可访问，再继续下面步骤

# 2) 客户端后端 venv（用 uv 托管的 Python 3.12；uv venv 不内置 pip，装包用 uv pip）
uv venv --python 3.12 .venv
uv pip install -r requirements.txt

# 3) 前端
cd frontend; npm install; npm run build; cd ..

# 4) 配置 LLM（复制 .env.example → .env，填 LLM_MODEL_NAME/LLM_API_KEY/LLM_BASE_URL）
```

## 启动

```powershell
# 1) MCP server（先手动拉起，见安装部分 / skynet-mcp 仓库 README）

# 2) 客户端后端（托管前端 dist）
.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8100

# 3) 前端开发模式（代理 /api，另开一个终端）
cd frontend; npm run dev

# 访问：http://127.0.0.1:8100
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
```
