# skynet-mcp-client 一键启动（Windows 侧 PowerShell）
# 1. 确保 WSL 内 MCP server（HTTP 模式）在跑
# 2. 起客户端后端（uvicorn 8100，托管前端 dist）
# 3. 打开浏览器
$ErrorActionPreference = "Stop"
$MCP_PORT = 8765
$CLIENT_PORT = 8100
$UBUNTU = "Ubuntu"

function Test-Mcp {
    try {
        Invoke-WebRequest -Uri "http://127.0.0.1:$MCP_PORT/mcp" -Method Post `
            -Body '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{}}}' `
            -ContentType "application/json" -TimeoutSec 2 -UseBasicParsing | Out-Null
        return $true
    } catch {
        return $false
    }
}

# ---- 1. WSL MCP server ----
if (-not (Test-Mcp)) {
    Write-Host "[1/3] 启动 WSL 内 MCP server（HTTP 模式 :$MCP_PORT）..."
    wsl -d $UBUNTU -- bash -lc "cd /home/losophy/skynet-mcp && nohup .venv/bin/python -m skynet_mcp.main --transport http --http-port $MCP_PORT >/tmp/skynet-mcp-http.log 2>&1 &"
    Start-Sleep -Seconds 2
    for ($i = 0; $i -lt 30; $i++) {
        if (Test-Mcp) { break }
        Start-Sleep -Milliseconds 500
    }
}
if (Test-Mcp) {
    Write-Host "  MCP server 就绪：http://127.0.0.1:$MCP_PORT/mcp"
} else {
    Write-Warning "  MCP server 未就绪！查看日志：wsl -d $UBUNTU -- cat /tmp/skynet-mcp-http.log"
}

# ---- 2. 客户端后端 ----
$venvPy = "D:\AgentProjects\skynet-mcp-client\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Error "未找到客户端 venv：$venvPy（先运行 .\scripts\setup.ps1 或手动创建）"
}
if (-not (Test-Path "D:\AgentProjects\skynet-mcp-client\frontend\dist")) {
    Write-Warning "前端未构建，先执行：cd frontend && npm run build"
}
Write-Host "[2/3] 启动客户端后端（:$CLIENT_PORT）..."
Start-Process -WindowStyle Hidden -FilePath $venvPy `
    -ArgumentList "-m", "uvicorn", "backend.app:app", "--host", "127.0.0.1", "--port", "$CLIENT_PORT" `
    -WorkingDirectory "D:\AgentProjects\skynet-mcp-client"

$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        Invoke-WebRequest -Uri "http://127.0.0.1:$CLIENT_PORT/api/status" -TimeoutSec 2 -UseBasicParsing | Out-Null
        $ready = $true
        break
    } catch {
        Start-Sleep -Milliseconds 500
    }
}
if (-not $ready) {
    Write-Warning "客户端后端未就绪，请检查端口占用或 venv 依赖。"
}

# ---- 3. 打开浏览器 ----
Write-Host "[3/3] 打开浏览器：http://127.0.0.1:$CLIENT_PORT"
Start-Process "http://127.0.0.1:$CLIENT_PORT"
Write-Host "完成。若需 LLM 对话能力，确认 .env 已配置 LLM_MODEL_NAME/LLM_API_KEY/LLM_BASE_URL。"
