# 计划：会话、trace 与 span

## 第 2 步：会话建模实施计划

### 采用的方案

采用 `docs/solution/session-trace-span.md` 中已批准的做法 A：建立 MySQL `chat_sessions` 表，`ChatSession` 继承 `CrudModel`。模型负责通用 CRUD 和简单、只涉及会话表的查询；鉴权用户名由路由传给模型。本阶段不增加 Service。后续跨模型流程或复杂业务规则出现时再引入 Service。

### 改动目录和模块

- `backend/app/chats/`：新增 `ChatSession` 模型，声明会话字段，并实现按用户名列出会话、按会话编号和用户名读取会话的方法。
- `backend/app/api/routes/`：新增会话路由，提供列表、创建、读取和改名接口；用户名只从鉴权状态取得。
- `backend/app/main.py`：启动时创建会话表并挂载会话路由。会话接口保持在鉴权中间件保护范围内。
- `backend/scripts/create_database.py`：按显式目标幂等创建开发库或测试库，并初始化用户表与会话表；新增模型表时同步维护初始化列表。
- `backend/tests/`：新增会话模型和接口测试，覆盖标题、列表排序、用户隔离、未登录和不存在会话。
- `frontend/src/api/`：新增会话 API，沿用现有 `satoken` 请求头，并提供改名调用。
- `frontend/src/domain/chat/`、`frontend/src/views/`：将本地会话初始化、新建、切换改为异步读取和写入后端会话；服务端列表为空时自动创建一条默认会话。

### 实施步骤

1. 新增 `ChatSession` 模型和应用启动建表接入。主键由应用生成 32 位十六进制字符串；字段为 `username`、`title`、`created_at`、`updated_at`。用户名外键指向 `users.username`，新建标题为「新会话」，时间使用 UTC。
2. 新增 `backend/scripts/create_database.py`，需要调用方明确选择 `development` 或 `test`。脚本从本机配置取凭据，幂等创建所选数据库，并调用该库的模型初始化用户表和会话表。
3. 新增 `GET /chat-sessions`、`POST /chat-sessions`、`GET /chat-sessions/{id}` 和 `PATCH /chat-sessions/{id}`。列表只查当前用户并按 `updated_at` 从新到旧排列；读取和改名都按会话编号及用户名过滤。不存在或不属于当前用户时返回相同的 404「会话不存在」。
4. 改名接口只接收标题，去掉首尾空白后保存；空标题或超过 255 个字符时拒绝。更新标题时同步更新 `updated_at`。
5. 新增前端会话 API，并让聊天页加载后端会话。列表为空时创建默认会话；新建会话和切换会话使用服务端编号；API 模块提供改名调用。会话加载或创建失败时显示可理解的错误状态，不伪造一个看似已持久化的本地会话。
6. 更新相关测试并检查现有聊天、登录和注册行为的回归。按照项目流程，一步实现完成后停下来供审查，不提交；收到审查通过和提交指示后再提交本步骤。

### 测试范围

- 模型：创建会话时生成合法编号，默认标题和时间正确；按用户列出的会话互不混淆，并按更新时间倒序；读取时同时按编号和用户名过滤。
- 初始化脚本：缺少目标库时可创建；目标库和表已存在时重复运行不破坏已有数据；脚本要求显式选择目标。
- 接口：已登录用户能创建、列出、读取和改名自己的会话；请求体不能改变会话归属；访问不存在或他人会话均返回相同的 404；未登录访问所有会话接口均返回 401。
- 改名：已登录用户可以持久化修改自己的标题；前后空白会裁掉；空标题或超过 255 字符被拒绝；他人或不存在的会话返回相同 404；成功修改会更新 `updated_at`。
- 前端 API：请求携带 `satoken`，解析会话列表、创建、读取和改名响应。
- 前端交互：初次进入时加载会话；空列表时创建默认会话；点击新建和切换后当前会话与侧栏一致；加载失败时呈现错误状态。
- 回归：已有聊天气泡、登录和注册相关用例。

### 不做的内容

- 不实现 trace、span、trace 列表、历史消息恢复或会话标题自动更新。
- 不改 SSE 回复来源和 `POST /replies`。
- 不新增独立 Service、Repository 或消息表。
- 不增加标题编辑 UI；本阶段提供后端接口和前端 API 调用能力。
- 不改变登录用的 `/session`、鉴权排除名单、聊天气泡样式和侧栏收起展开行为。

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
2. session 建模与接口。表的主键由服务端生成。列包括用户名、标题、创建时间和更新时间。用户名对应 `users.username`。接口为 `GET /chat-sessions`、`POST /chat-sessions`、`GET /chat-sessions/{id}` 和 `PATCH /chat-sessions/{id}`。列表只返回当前用户的会话，按更新时间从新到旧。新建的标题是「新会话」。改名只接受标题，校验后更新标题和更新时间。编号不存在或不属于当前用户时返回 404。打开聊天页时读取列表；一条都没有时自动新建一条，和现在进入页面就有一条空会话一致。侧栏的新建和切换改调这些接口。
3. trace 建模与接口。一条 trace 属于一条 session，列包括这一轮的用户输入、状态和创建时间。状态为进行中、完成、失败。`GET /chat-sessions/{id}/traces` 按创建时间返回该会话的各轮。发送改为 `POST /chat-sessions/{id}/replies`：先把 trace 标为进行中，再按第 1 步的事件推送；正常结束标为完成，连接中断或推送失败标为失败。标题仍是「新会话」时，用首轮用户输入的前 16 个字生成标题，超长时加省略号，规则与现在的 `Dialogue.nameFrom` 相同；用户手动修改后的标题不被自动覆盖。会话的更新时间跟着 trace 更新。这一步删除 `POST /replies`。刷新后能看到每一轮的用户输入和状态。助手正文仍只在当次 SSE 里出现。
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
