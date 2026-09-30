# 总结：会话、Trace 与 Span

## 最终实现

- 使用 `chat_sessions`、`traces`、`spans` 三张表保存会话、每轮用户输入和执行步骤，不另建消息表。
- 会话 API 支持列表、创建、读取和手动改名；标题仍为「新会话」时，首轮输入生成默认标题。
- 回复 API 按会话创建 Trace 和一条 `running` 的 `text` Span，通过 SSE 发送模拟回复。推送期间正文只在内存累积；结束、出错或断开时在线程池里一次写入正文和 Span、Trace 的最终状态。
- Span 表按多 agent 和上下文压缩的需要扩展了字段：`status`、`parent_span_id`、`agent_name`、`node`、`visible`、`model`、`truncated`、`summary`、`summarized_at`、`tokens`、`summary_tokens`、`started_at`、`ended_at`。模拟阶段归属和摘要字段为空。
- 写库正文上限 64 KiB（UTF-8 字节），按字符边界截断并标记 `truncated`；推送给客户端的片段不截断。
- 应用启动时把超过 10 分钟仍为 `running` 的 Trace 和 Span 标为 `failed`。
- 重新打开会话时，后端只拼接 `visible` 为真的 `text` Span，按 `sequence` 排序作为助手回复返回。
- `backend/scripts/create_database.py` 按显式目标创建开发库或测试库；`--rebuild-spans` 显式删除并重建 `spans` 表。

## 第二阶段：分支、历史接口和模型上下文

- Trace 增加 `parent_trace_id`，会话增加 `active_trace_id`，一个会话的对话成为一棵树，界面只显示从根到 `active_trace_id` 的一条路径。
- 编辑和重新生成都以 `sibling_of` 发送：新 Trace 与原 Trace 同父，成为同一位置的新版本。编辑在用户气泡原位弹出输入框，这不是 human-in-the-loop，而是用户主动发起的新分支；HITL 仍留给 `human_input` Span。
- `PUT /chat-sessions/{id}/active-trace` 切换版本：跳到该版本所在分支的末端，每一步都取最新的子节点。因此切回旧版本后看到的是这个版本下最新的一条续写，不是上次停留的那条。
- `GET /chat-sessions/{id}/history` 取代前端逐轮读取 Span 的 N+1 请求：除会话校验外只查两次（全部 Trace 元数据一次、本页可见 text Span 一次），支持 `limit`、`before` 翻页，并返回每轮的版本信息。
- `backend/app/agents/context_strategies.py` 用策略模式组装模型上下文：默认策略为最近 2 轮原文加更早轮次的目录，只用已完成的轮次，历史部分受 token 上限约束；每个 agent 的策略也写在这个文件并登记到 `_STRATEGIES`。
- `backend/app/tools/history_tools.py` 提供按需取历史的 `list_turns`、`read_turn`、`read_step`，只读当前路径上已完成的祖先轮次，有单次和累计字数上限。
- Span 增加 `prompt_version`、`context_rule_version`、`input_digest` 三列，供 llm Span 记录当时用的提示词版本、上下文规则版本和输入指纹，事后可核对重建的上下文是否一致。
- 前端：打开会话只请求一次历史；顶部「加载更早的对话」；用户气泡有「编辑」和「< i / n >」版本切换，助手气泡有「重新生成」；流式回复和加载期间这些操作都不可用；一轮结束后重新读取历史，拿到新 Trace 的编号。
- 旧库迁移：`create_database.py --migrate-branches` 补列、外键和索引，并把已有 Trace 按创建时间串成一条链；可重复执行。

## 方案取舍

- session、Trace、Span 分别代表会话、单轮对话和单轮中的执行步骤，助手正文只保存在 Span。
- 进程被直接杀掉时丢失正在生成的一轮可以接受，因此没有采用 Redis Stream 或 MySQL 增量事件表，换来简单的一次写入。
- `summary` 只供模型上下文使用，不改写 `text`；跨轮总结以后单独建 `context_summaries` 表，不放进 Span。
- 普通单表查询留在模型中；跨模型事务和 SSE 生命周期由 `ChatReplyService` 协调。

## 遇到的问题

- 沙箱默认网络策略阻断了 MySQL 连接，测试辅助代码现会报告驱动错误类型和错误码，且不输出连接凭据。
- MySQL 集成测试发现 Span 可能先于 Trace 插入，触发外键错误。创建 Trace 后在同一事务内显式 `flush` 再插入 Span。
- Starlette 的 `StreamingResponse` 不会关闭内容生成器，客户端断开后最终写入要等垃圾回收；它的取消还会反复打断后续等待。回复改用 `ClosingStreamingResponse` 显式关闭生成器，最终写入放在屏蔽取消的范围内。
- 前端构建在 Node.js 21.7.3 下有版本提示，且 bundle 超过 500 kB；构建仍成功。
- MySQL 上 Trace 自引用外键会让测试清理时批量删除失败，清理前先把 `parent_trace_id` 置空。
- 上下文预算最初在降级原文时连目录一起计算，导致最后一轮原文也被降为目录；改为先让原文部分放得下，再丢最早的目录行。

## 可沿用做法

- 新增模型表时同步更新数据库初始化脚本，并按外键依赖顺序创建表；改表结构时用显式选项重建，不让启动过程自动删表。
- 嵌套数据接口先按 `satoken` 用户验证父级会话，再读取子级 Trace 或 Span；越权与不存在统一返回 404。
- 测试取消处理时，要在事件循环关闭前检查状态，否则 `asyncio` 关闭时会自动关闭残留生成器，掩盖问题。
