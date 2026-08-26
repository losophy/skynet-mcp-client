# skynet MCP 工具测试提示词

覆盖全部 32 个 `skynet_*` 工具的端到端测试提示词。**用法**：在 opencode 对话里直接粘贴
对应提示词（或让模型"按顺序测试"），模型会自动调用 `skynet_*` 工具并返回 skynet 的真实输出。
返回正常内容即该工具链路通。

**前置**：`/mcp` 里 skynet 显示已连接；skynet debug console 已启动（默认 8000）。

**测试顺序建议**：先跑「A. 只读·全局」→「B. 只读·单服务」→「C. 启动/操作类」→
「D. 危险命令」（危险命令会触发工具确认，请按提示操作）。

**地址写法**：`list` 输出里的 `:01000004`（八位 hex）、`1`（简写）、`.watchdog`（本地服务名）。
以下提示词用 `.watchdog` 示例，换成实际服务名或先用 list 拿地址即可。

---

## A. 只读 · 全局命令（无副作用，随便测）

| # | 工具 | 测试提示词（直接复制） | 预期结果 |
|---|---|---|---|
| 1 | `help` | `用 skynet 工具查看 debug console 支持的全部命令和用法` | 返回全部命令的帮助文本 |
| 2 | `list` | `用 skynet 工具列出当前所有服务及地址` | 每行 `地址\t启动方式 参数` |
| 3 | `service` | `用 skynet 工具列出所有唯一 lua 服务和挂起请求` | 唯一服务列表 |
| 4 | `stat` | `用 skynet 工具查看各服务的消息队列长度和挂起请求数` | 每服务一行统计 |
| 5 | `mem` | `用 skynet 工具查看各服务占用的 lua 内存` | 每服务内存占用 |
| 6 | `gc` | `用 skynet 工具触发一次全服 GC 并报告回收后内存` | GC 后各服务内存（会短暂影响性能） |
| 7 | `netstat` | `用 skynet 工具查看网络连接概况` | 连接读写字节/缓冲 |
| 8 | `cmem` | `用 skynet 工具查看 C 层内存信息` | C 模块内存统计 |
| 9 | `jmem` | `用 skynet 工具查看 jemalloc 内存统计` | jemalloc 统计（需 jemalloc 编译） |
| 10 | `dumpheap` | `用 skynet 工具导出当前堆 profile 数据` | heap 数据（需先 profactive on） |
| 11 | `profactive` | `用 skynet 工具查询 jemalloc 堆分析当前状态` | 返回 on/off 状态 |
| 12 | `clearcache` | `用 skynet 工具清空 lua 代码缓存` | 清缓存确认（配合 start 生效） |

## B. 只读 · 单服务命令（需要服务地址，先跑 #2 list 确认 `.watchdog` 存在）

| # | 工具 | 测试提示词（直接复制） | 预期结果 |
|---|---|---|---|
| 13 | `info` | `用 skynet 工具查看 .watchdog 服务的内部信息` | 消息队列/协程等运行时信息 |
| 14 | `ping` | `用 skynet 工具测量 .watchdog 服务的往返耗时` | 耗时 tick 数 |
| 15 | `task` | `用 skynet 工具查看 .watchdog 服务挂起请求的调用栈` | 挂起请求栈列表 |
| 16 | `uniqtask` | `用 skynet 工具查看 .watchdog 服务唯一任务的挂起调用栈` | 唯一任务栈 |
| 17 | `trace` | `用 skynet 工具开启 .watchdog 服务的协议跟踪` | 跟踪开启确认（测完用 `trace .watchdog off` 关闭） |
| 18 | `getenv` | `用 skynet 工具读取 standalone 环境变量` | `名字\t值` |

## C. 启动 / 操作类命令（⚠ 有副作用，确认后再执行）

| # | 工具 | 测试提示词（直接复制） | 预期结果 |
|---|---|---|---|
| 19 | `start` | `用 skynet 工具启动一个新的 watchdog 服务` | 返回 `地址\t服务名` |
| 20 | `log` | `用 skynet 工具启动一个带日志的 watchdog 服务` | 返回新服务地址 |
| 21 | `snax` | `用 skynet 工具启动一个 simpledb 的 snax 服务` | 返回 snax 服务地址 |
| 22 | `logon` | `用 skynet 工具开始记录 .watchdog 服务的输入消息` | 开始记录确认 |
| 23 | `logoff` | `用 skynet 工具停止记录 .watchdog 服务的输入消息` | 停止记录确认 |
| 24 | `setenv` | `用 skynet 工具把环境变量 testflag 设为 1` | 设置确认（改回：`setenv testflag 旧值`） |
| 25 | `dbgcmd` | `用 skynet 工具向 .watchdog 服务发送 INFO debug 命令` | debug 协议返回 |

## D. 危险命令（【危险】影响运行中的服务，每个都需用户确认；测试请选无害目标）

| # | 工具 | 测试提示词（直接复制） | 预期结果 / 注意事项 |
|---|---|---|---|
| 26 | `signal` | `用 skynet 工具给 .watchdog 服务发送信号（默认值）` | 打断正在执行的 lua 字节码并抛栈。**会打断服务当前代码** |
| 27 | `kill` | `用 skynet 工具强制中止 .watchdog 服务` | 强杀服务。**服务直接消失** |
| 28 | `exit` | `用 skynet 工具让 .watchdog 服务正常退出` | 走正常退出流程，优先于 kill |
| 29 | `killtask` | `用 skynet 工具终止 .watchdog 服务的指定线程` | 需先用 `task` 拿到 threadname |
| 30 | `inject` | `用 skynet 工具向 .watchdog 服务注入脚本 /home/losophy/patch.lua` | 路径是 **skynet 服务器视角**，脚本会在服务内执行 |
| 31 | `call` | `用 skynet 工具调用 .watchdog 服务的 lua 接口，表达式为 "ping"` | 接口在 skynet 进程内执行，可改服务状态 |
| 32 | `raw_command` | `用 skynet 工具原样执行命令 list` | 任意命令兜底，拼错命令名返回 `<CMD Error>` |

---

## 一键冒烟（覆盖最核心的只读链路）

把下面这段一次性发给 opencode，会依次走 help → list → service → stat → mem：

```
依次用 skynet 工具执行：查看命令帮助 → 列出所有服务 → 列出唯一服务 → 查看消息队列统计 → 查看 lua 内存。
每步都告诉我返回结果，如果某步失败，说明具体报错。
```

## 常见失败对照

- `Connection closed` → server 没起来，确认 `/mcp` 已连接、command 用 `-m skynet_mcp.main`
- 工具报"无法连接 skynet debug console" → skynet 没起或端口不一致（检查 `--port` 与
  `skynet.newservice("debug_console", ...)`）
- 单服务命令报 `<CMD Error>` → 地址不存在，先用 `list` 拿真实地址
- `raw_command` 传 `debug` → 被显式拒绝（HTTP 通道不支持交互式会话）
