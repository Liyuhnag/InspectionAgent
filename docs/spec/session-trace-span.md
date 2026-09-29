# 规格：会话、trace 与 span

计划见 `docs/plan/session-trace-span.md`。业务代码按其中四步分别提交，上一步审核通过后再做下一步。本规格一次写完，供每一步验收。

## 第 2 步：会话建模规格

本节定义本次实施与验收范围。只实现聊天会话表、会话接口和前端会话列表持久化，不实现后续 trace、span 或历史消息恢复。

### 行为与接口

- `GET /chat-sessions` 返回 HTTP 200 和 `{"sessions": [...]}`。列表只包含当前 `satoken` 对应用户的会话，按 `updated_at` 从新到旧排列。每项含 `id`、`title`、`updated_at`。
- `POST /chat-sessions` 不需要请求体。成功时返回 HTTP 201 和新建会话对象，字段为 `id`、`title`、`updated_at`。标题为「新会话」，创建时 `created_at` 与 `updated_at` 相同。
- `GET /chat-sessions/{id}` 返回 HTTP 200 和会话对象，字段为 `id`、`title`、`updated_at`。
- `PATCH /chat-sessions/{id}` 接收 `{"title":"新标题"}`，返回 HTTP 200 和更新后的会话对象。成功时保存标题并更新 `updated_at`。
- 改名请求会裁掉标题首尾空白。空标题或裁剪后超过 255 个字符时返回 HTTP 422。改名路径编号不存在或不属于当前用户时返回 HTTP 404 和 `{"detail":"会话不存在"}`。
- 所有会话接口均受现有鉴权中间件保护。未登录返回 HTTP 401，响应为 `{"detail":"未登录"}`。编号不存在或属于其他用户时，读取和改名接口均返回 HTTP 404，响应为 `{"detail":"会话不存在"}`，不泄露会话是否存在。
- 会话归属只取自鉴权中间件写入的 `request.state.username`。请求体、查询参数和路径均不能指定或覆盖归属用户。
- 会话 ID 为应用生成的 UUID 十六进制字符串，不含连字符，共 32 个字符。时间按 UTC 保存，并以 ISO 8601 格式返回。
- 手动改名会更新标题和 `updated_at`。后续 trace 阶段只在标题仍为「新会话」时按首条用户输入生成默认标题；自动生成不覆盖已手动修改的标题。

### 数据模型与模块边界

- 数据库表名为 `chat_sessions`。列为 `id VARCHAR(32)` 主键、`username VARCHAR(64)` 非空外键（指向 `users.username`）、`title VARCHAR(255)`、非空 `created_at` 和非空 `updated_at`。
- 增加以 `username`、`updated_at` 为顺序的组合索引，支持按用户倒序列出会话。
- `backend/app/chats/chat_session.py` 中的 `ChatSession` 继承 `CrudModel` 并复用其已实现的通用 CRUD 方法；会话专属查询由 `ChatSession` 自身的方法实现。本阶段不额外定义面向对象接口，也不建立 Service 或 Repository。
- 路由位于 `backend/app/api/routes/chat_sessions.py`，只校验改名请求、读取鉴权用户名、调用模型方法并组织 HTTP 响应。数据库连接沿用现有 `Engine` 和 `Session` 用法。
- `create_app` 启动时在 `User` 表之后创建 `chat_sessions` 表，并注册路由。聊天接口不加入公开路由名单。
- `backend/scripts/create_database.py` 必须要求显式传入 `--target development` 或 `--target test`。脚本从 `backend/config/dev.yaml` 读取配置，在服务器连接上用 `CREATE DATABASE IF NOT EXISTS` 创建所选库，然后在所选库中幂等创建 `users` 与 `chat_sessions` 表。脚本重复运行不得删除或重置数据，也不得输出凭据。
- 前端 API 位于 `frontend/src/api/chatSessions.ts`，请求沿用现有 `satoken`，并提供会话改名调用。聊天页初始化时拉取列表；若列表为空则创建一条空会话。新建和切换操作使用服务端返回的 ID。加载或创建失败时显示错误状态，不显示一个伪装成已保存的本地会话。本阶段不增加标题编辑控件。

### 验收标准

- 创建会话后，数据库记录的 ID、归属、默认标题和时间均符合定义；重启应用后仍可读取。
- 用户只能列出和读取自己的会话。用其他用户的 ID 与不存在的 ID 访问，响应状态和错误正文完全相同。
- 列表顺序按 `updated_at` 倒序。空列表响应为空数组，不报错。
- 未登录访问列表、创建和读取接口均返回 401；传入伪造用户名不能改变创建归属或读取范围。
- 前端进入页面后加载服务端列表；空列表时创建默认会话；侧栏新建和切换后，当前项与服务端会话一致。接口失败时显示错误状态。
- 现有登录、注册、SSE 回复与聊天气泡行为保持通过既有测试。

### 测试场景

- 模型正常创建、默认字段、合法 ID、UTC 时间、按用户查询、不同用户隔离、倒序排序和未知记录读取。
- 初始化脚本分别选择开发库和测试库；目标库不存在时创建，已存在时保持数据并补齐缺少的应用表；未指定目标时参数解析失败。
- 接口登录后创建、列表和读取；请求中伪造 username 不生效；跨用户编号与未知编号均返回相同 404；未登录的三个接口均返回 401；空列表返回空数组。
- 前端 API 为请求附加 `satoken`，正确解析列表、创建、单项读取和改名响应；改名请求使用 `PATCH` 并只提交 `title`。
- 前端页面初始化加载会话、空列表自动创建、新建、切换，以及列表或创建失败时的错误状态。
- 回归既有会话交互、登录、注册、SSE 与聊天气泡用例。

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
- 标题仍是「新会话」时，用这一轮用户输入的前 16 个字更新标题；超过 16 个字时末尾加「…」。之后的轮次不改标题。用户手动改过标题后，自动标题不覆盖它。
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
| `PATCH /chat-sessions/{id}` | 第 2 步 | 更新后的会话对象 | 401；404 会话不存在；422 标题无效 |
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
- 已登录用户改名后重新读取仍得到新标题；标题首尾空白会裁剪，空白标题和超过 255 个字符的标题返回 422。
- 甲携带自己的 token，访问乙的会话编号，得到 404。请求体中的用户名不影响列表。
- 甲修改乙的会话标题得到与未知编号相同的 404；未登录调用改名接口得到 401。
- 打开页面时列表为空会自动出现一条空会话。新建和切换改变当前会话。

第 3 步：

- 同一会话连续两次发送，trace 按创建时间排列，状态都是 `complete`，`user_text` 分别是两次输入。
- 第二条尚在推送时中断，该条为 `failed`，第一条仍为 `complete`。
- 第一条用户输入超过 16 个字时，标题是前 16 个字加「…」。第二条不改变标题。
- 用户手动改过标题后，后续 trace 不会用自动标题覆盖它。
- `POST /replies` 不再存在。
- 刷新后能读到用户输入和状态。此步的库里还没有助手正文。

第 4 步：

- 一条完成的 trace 只有一条 `sequence` 为 1、类型为 `text` 的 span，文本等于固定回复全文。
- 中断后 span 文本等于已经发出的 `chunk` 之和，trace 为 `failed`。
- `done` 带有这条 trace 和 span 的编号。`chunk` 仍然只有 `text`。
- 打开已有会话时，消息条数是 trace 数的两倍，顺序为用户、助手交替。`complete` 显示为完成，`failed` 和 `running` 显示为失败。

依赖 MySQL 或 Redis 的用例在没有本机 `dev.yaml`，或测试库不可用时跳过。前端来源测试用假响应，不要求后端已启动。
