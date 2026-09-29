# 计划：会话、trace 与 span

## 采用的方案

方案 A。见 `docs/solution/session-trace-span.md`。

后端用 SSE 推送助手回复。模拟阶段返回固定文案。聊天数据是三张表：session、trace、span。一条 session 有多条 trace，一条 trace 是一轮完整对话，span 是这一轮里的步骤。不另建消息表。登录用的 `/session` 保持不变。

## 改动的目录和模块

- `backend/app/`：新增聊天会话、trace、span 的模型和路由。模型继承 `CrudModel`。列表和按会话过滤写在模型上，不另做仓库
- `backend/app/main.py`：启动时建这三张表，挂上路由。聊天路由不加入鉴权排除名单
- `backend/tests/`：SSE、三张表和「甲的 token 读不到乙」
- `frontend/src/domain/chat/`：新增 SSE 来源，实现现有的 `TextChunkSource`
- `frontend/src/views/ChatView.vue`：默认改用 SSE 来源。侧栏在 session 接口完成后改为读写后端
- `frontend/src/api/`：聊天请求继续带 `satoken`

不改 `agents/`、`graphs/`、`prompts/`、`tools/`。不改气泡组件、输入框和侧栏收起展开的行为。`ChatSession` 仍然把片段追加到同一条助手消息。

## 实施步骤

每一步一次提交。上一步审核通过后再做下一步。

1. 前后端通路。新增 `POST /replies`，请求体是 `{ "text": "..." }`，响应 `Content-Type` 为 `text/event-stream`。事件为 `chunk`（`{"text":"..."}`）、`done`（`{}`）和 `error`（`{"detail":"..."}`）。正文由后端按段推送固定文案。未登录返回 401。前端用新的 `TextChunkSource` 读取这些事件，`ChatView` 改用它。中断时关闭流，已输出的文字保留，助手消息标为失败。这一步不建表。
2. session 建模与接口。表的主键由服务端生成。列包括用户名、标题、创建时间和更新时间。用户名对应 `users.username`。接口为 `GET /chat-sessions`、`POST /chat-sessions`、`GET /chat-sessions/{id}`。列表只返回当前用户的会话，按更新时间从新到旧。新建的标题是「新会话」。编号不存在或不属于当前用户时返回 404。打开聊天页时读取列表；一条都没有时自动新建一条，和现在进入页面就有一条空会话一致。侧栏的新建和切换改调这些接口。
3. trace 建模与接口。一条 trace 属于一条 session，列包括这一轮的用户输入、状态和创建时间。状态为进行中、完成、失败。`GET /chat-sessions/{id}/traces` 按创建时间返回该会话的各轮。发送改为 `POST /chat-sessions/{id}/replies`：先把 trace 标为进行中，再按第 1 步的事件推送；正常结束标为完成，连接中断或推送失败标为失败。第一条 trace 出现时，用用户输入的前 16 个字更新会话标题，超长时加省略号，规则与现在的 `Dialogue.nameFrom` 相同。会话的更新时间跟着 trace 更新。这一步删除 `POST /replies`。刷新后能看到每一轮的用户输入和状态。助手正文仍只在当次 SSE 里出现。
4. span 建模与接口。一条 span 属于一条 trace，列包括顺序、类型和文本。类型沿用前端的片段类型。模拟阶段只写一条 `text`。流式过程中累计到这一条上，不为每个 `chunk` 插一行；结束时标 trace 完成，失败时标 trace 失败并保留已经写入的文本。`GET /chat-sessions/{id}/traces/{trace_id}/spans` 按顺序返回。`done` 事件带上 `trace_id` 和 `span_id`。`chunk` 仍只含 `text`，气泡追加方式不变。打开一条已有会话时，用 trace 的用户输入和 span 的文本恢复消息列表。

## 测试范围

- 未登录调用 `POST /replies` 得到 401。登录后收到按序的 `chunk`，并以 `done` 结束。
- 新的文本来源把片段追加到同一条助手消息。流失败或中断后状态为 `error`，已输出文字还在，之后可以再发送。
- 两个用户：甲只能列出和读取甲的会话。甲使用乙的会话编号得到 404。请求体里的用户名不影响结果。
- 新建会话的标题是「新会话」。第一条用户输入写入后，标题变为输入的前 16 个字。
- 同一条会话连续发送两次，得到两条 trace，状态分别为完成。第二条进行中时中断，该条为失败，前一条仍为完成。
- 一条完成的 trace 有一条 `text` span，文本等于 SSE 推送的全文。失败时 span 保留已写入的部分。
- 打开已有会话时，消息顺序与 trace、span 的顺序一致。
- 已有的登录、注册和聊天气泡测试仍然通过。

## 不做的内容

不接真实模型，不调用 `agents/`、`graphs/`、`prompts/`、`tools/`。不渲染思考、工具调用、MCP、人工介入和上下文压缩；这些类型只留在 span 的类型里。不做给模型喂上下文的对话记忆，也不为记忆另建表。不修改登录用的 `/session`。不把 token 放进 URL。不另建消息表，不为每个 SSE 片段写一行。
