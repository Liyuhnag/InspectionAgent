# 规格：会话、trace 与 span

计划见 `docs/plan/session-trace-span.md`。业务代码按其中四步分别提交，上一步审核通过后再做下一步。本规格一次写完，供每一步验收。

## 行为说明

助手回复由后端用 SSE 推送。模拟阶段不调用模型。固定回复是一段较长的巡检说明，全文由 `mock_reply` 生成，包含用户输入、1 号线压力异常、3 号泵房阀门核对，以及备用泵、照明、消防和配电间的补记。长度要够一次回复被切成很多段。

`{用户输入}` 是去掉首尾空白后的原文。回复按每段最多 4 个字符切开，每段一个 `chunk` 事件，最后一段可以短于 4 个字符。段之间的顺序与原文一致。

助手气泡按 Markdown 渲染。原文里的 HTML 标签按文本显示，不执行。只允许 `http` 和 `https` 链接。用户气泡仍是纯文本。

SSE 响应的 `Content-Type` 为 `text/event-stream`。事件格式：

```text
event: chunk
data: {"text":"已收"}

event: done
data: {}

event: error
data: {"detail":"回复失败"}
```

`chunk` 的 `data` 只有 `text`。模拟回复的正常结束发 `done`，不发 `error`。推送过程中失败时发 `error`，然后结束响应。空文本或缺少 `text` 时不建立流，直接返回 400，`detail` 为「不能为空」。

未登录访问任一聊天接口返回 401，`detail` 为「未登录」。当前用户只来自 `satoken`。请求体里的用户名不改变归属。

前端用新的 `TextChunkSource` 读这些事件。`chunk` 追加到同一条助手消息，`done` 把该消息标为完成，`error` 或连接中断标为失败。失败时保留已经输出的文字，并允许再次发送。气泡、输入框和侧栏收起展开的行为不变。

聊天会话、trace、span 分三张表，都继承 `CrudModel`。不另建消息表，不为每个 `chunk` 插入一行。

会话：

- 主键由服务端生成，是 32 位十六进制字符串。
- 列包括用户名、标题、创建时间、更新时间。用户名对应 `users.username`。
- 新建时标题为「新会话」。
- 列表只含当前用户的会话，按更新时间从新到旧。
- 编号不存在，或不属于当前用户，都返回 404，`detail` 为「会话不存在」。两种情况的响应相同。
- 打开聊天页时读取列表。一条都没有时自动新建一条空会话。侧栏的新建和切换调用这些接口。

trace：

- 一条会话有多条 trace。一条 trace 是一轮完整对话。
- 列包括所属会话、这一轮的用户输入、状态、创建时间。主键同样是 32 位十六进制字符串。
- 状态取值为 `running`、`complete`、`failed`。
- 发送时先写入 `running`，再推送 SSE。正常结束改为 `complete`。客户端中断或推送失败改为 `failed`。
- 列表按创建时间从早到晚。
- 标题仍是「新会话」时，用这一轮用户输入的前 16 个字更新标题；超过 16 个字时末尾加「…」。之后的轮次不改标题。
- 每新建一条 trace，会话的更新时间改为这条 trace 的创建时间。
- 从本步起，发送地址改为带会话编号的接口，并删除 `POST /replies`。刷新后能看到每一轮的用户输入和状态。助手正文要到 span 写入后才存在于库里。

span：

- 一条 trace 在模拟阶段只有一条 span。列包括所属 trace、顺序、类型、文本。主键是 32 位十六进制字符串。顺序从 1 开始。
- 类型允许 `text`、`thinking`、`tool_call`、`mcp_call`、`human_input`、`context`。模拟阶段只写 `text`。
- 开始推送前插入这条 span，文本为空。每发出一个 `chunk`，把已累计的助手正文写回同一行。
- 流正常结束时 trace 为 `complete`。失败或中断时 trace 为 `failed`，span 保留已写回的文本。
- 列表按顺序从小到大。
- 本步的 `done` 事件改为 `{"trace_id":"...","span_id":"..."}`。`chunk` 仍然只有 `text`。
- 打开已有会话时，按 trace 的顺序恢复消息。每条 trace 先放用户消息，正文是该轮用户输入，状态为完成。再放助手消息，正文只拼接类型为 `text` 的 span。trace 为 `complete` 时助手消息为完成；`failed` 或仍为 `running` 时助手消息为失败。没有 trace 的会话仍显示空会话首页。

## 接口、状态和模块边界

登录用的 `POST/GET/DELETE /session` 不变，仍在鉴权排除名单里。下面的聊天接口都要登录。

模型放在 `backend/app/chats/`。聊天会话模型名为 `ChatSession`，与前端内存中的 `ChatSession` 不是同一个类。trace 模型名为 `Trace`，span 模型名为 `Span`。列表和按所属记录过滤写在对应模型上，不另做仓库。路由放在 `backend/app/api/routes/`，只校验入参并调用这些模型。数据库会话沿用 SQLAlchemy 的 `Session`，不拿它表示聊天会话。

应用启动时创建三张表。第 1 步还没有这些表。

| 动作 | 何时提供 | 成功 | 失败 |
| --- | --- | --- | --- |
| `POST /replies` | 第 1 步，第 3 步删除 | SSE：若干 `chunk`，然后 `done` | 401 未登录；400 不能为空 |
| `GET /chat-sessions` | 第 2 步 | `{"sessions":[...]}` | 401 |
| `POST /chat-sessions` | 第 2 步 | 新建的会话，标题为「新会话」 | 401 |
| `GET /chat-sessions/{id}` | 第 2 步 | 该会话 | 401；404 会话不存在 |
| `GET /chat-sessions/{id}/traces` | 第 3 步 | `{"traces":[...]}` | 401；404 会话不存在 |
| `POST /chat-sessions/{id}/replies` | 第 3 步 | 先有一条 `running` trace，再 SSE | 401；404 会话不存在；400 不能为空 |
| `GET /chat-sessions/{id}/traces/{trace_id}/spans` | 第 4 步 | `{"spans":[...]}` | 401；404 会话不存在或 trace 不属于该会话 |

会话对象含 `id`、`title`、`updated_at`。trace 对象含 `id`、`user_text`、`status`、`created_at`。span 对象含 `id`、`sequence`、`type`、`text`。时间用 ISO 8601 字符串。响应里不返回别的用户的用户名以外的登录信息；会话对象可以带 `username`，其值必须是当前用户。

前端请求继续使用 `frontend/src/api/session.ts` 里的 `satoken`。SSE 来源放在 `frontend/src/domain/chat/`，由 `ChatView` 在未传入测试来源时使用。第 1 步它请求 `POST /replies`。第 3 步改为请求当前会话的 `POST /chat-sessions/{id}/replies`。

## 验收标准

- 登录后发送一句，助手气泡里的全文等于上面的固定回复，并且是逐段出现在同一条消息里。
- 未登录不能收到 SSE。空白不能发送。
- 甲只能看到甲的会话。甲使用乙的会话编号得到 404。
- 一条会话两次发送得到两条 trace，都能完成后状态为 `complete`。中断第二条时，它为 `failed`，第一条仍为 `complete`。
- 完成后的助手正文在一条 `text` span 里，等于 SSE 全文。失败时 span 里是已推送的部分。
- 刷新后，侧栏会话还在；点开后，用户输入和助手正文的顺序与 trace、span 一致。
- 登录、注册、气泡追加和侧栏收起展开的已有测试仍然通过。

## 测试场景

第 1 步：

- 未登录 `POST /replies` 得到 401。
- 登录后，`chunk` 按顺序拼回固定回复，并以 `done` 结束。`data` 里没有 `trace_id`。
- 空 `text` 得到 400，响应不是 SSE。
- 前端来源把片段写入同一条助手消息。中断或 `error` 后消息为失败，已有文字还在，可以再次发送。

第 2 步：

- 新建会话的标题是「新会话」。列表按更新时间从新到旧，且只有当前用户。
- 甲携带自己的 token，访问乙的会话编号，得到 404。请求体中的用户名不影响列表。
- 打开页面时列表为空会自动出现一条空会话。新建和切换改变当前会话。

第 3 步：

- 同一会话连续两次发送，trace 按创建时间排列，状态都是 `complete`，`user_text` 分别是两次输入。
- 第二条尚在推送时中断，该条为 `failed`，第一条仍为 `complete`。
- 第一条用户输入超过 16 个字时，标题是前 16 个字加「…」。第二条不改变标题。
- `POST /replies` 不再存在。
- 刷新后能读到用户输入和状态。此步的库里还没有助手正文。

第 4 步：

- 一条完成的 trace 只有一条 `sequence` 为 1、类型为 `text` 的 span，文本等于固定回复全文。
- 中断后 span 文本等于已经发出的 `chunk` 之和，trace 为 `failed`。
- `done` 带有这条 trace 和 span 的编号。`chunk` 仍然只有 `text`。
- 打开已有会话时，消息条数是 trace 数的两倍，顺序为用户、助手交替。`complete` 显示为完成，`failed` 和 `running` 显示为失败。

依赖 MySQL 或 Redis 的用例在没有本机 `dev.yaml`，或测试库不可用时跳过。前端来源测试用假响应，不要求后端已启动。
