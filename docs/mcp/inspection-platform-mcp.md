# 巡检平台 MCP 对接要求

版本：v1  
日期：2026-10-01  
读者：巡检平台 MCP 服务的实现方

本文规定 MCP 需要提供的工具、参数、返回字段、错误码和连接方式。平台内部表结构可以不同，但对外必须呈现本文的资源和字段。做不到的条目请在回复里逐条说明，不要静默省略字段。调用方只通过这里列出的工具访问平台。

## 1. 要支持的能力

| 能力 | 对应工具 |
| --- | --- |
| 主机查询 | `list_businesses`、`list_clusters`、`get_cluster`、`list_modules`、`get_module`、`list_hosts`、`get_host` |
| 检查项目录 | `list_check_items` |
| 主机组增删改查 | `list_host_groups`、`get_host_group`、`create_host_group`、`update_host_group`、`delete_host_group` |
| 巡检方案增删改查 | `list_schemes`、`get_scheme`、`create_scheme`、`update_scheme`、`delete_scheme` |
| 巡检计划增删改查 | `list_plans`、`get_plan`、`create_plan`、`update_plan`、`delete_plan` |
| 巡检计划的执行 | `run_plan` |
| 执行历史及其结果 | `list_executions`、`get_execution`、`list_execution_host_results`、`summarize_execution_host_results` |

业务、集群、模块和检查项只提供查询，不提供创建、修改和删除。

不在本次范围：

- 向调用方推送回调。执行是异步的，调用方通过 `get_execution` 查询状态。
- 在主机上执行修复，例如重跑脚本、重启、清理磁盘。
- 生成新的巡检脚本。方案里的检查项只能引用已有目录。

## 2. 连接方式

使用 MCP Streamable HTTP，协议版本 `2025-06-18`。不用 stdio，也不用旧的 HTTP+SSE 独立传输。

| 项 | 要求 |
| --- | --- |
| 端点 | 测试环境 `https://21.91.71.22:8443/mcp`。生产环境地址另给。`tools/list` 已在测试环境返回 HTTP 200，并列出第 4 节的 28 个工具 |
| 方法 | `POST`，请求体是一条 JSON-RPC 2.0 消息 |
| 协议头 | `MCP-Protocol-Version: 2025-06-18` |
| 内容类型 | 请求 `Content-Type: application/json`；响应 `Content-Type: application/json` |
| 会话 | 无状态。不依赖 `Mcp-Session-Id`，每个 `POST` 独立完成 |
| TLS | 必须。测试环境可以用自签名证书，但要提前给出证书 |

调用顺序：

1. `initialize`，`params.protocolVersion` 为 `2025-06-18`。响应里的 `protocolVersion` 必须回 `2025-06-18`。
2. 通知 `notifications/initialized`。
3. `tools/list` 返回第 4 节的全部工具，每个工具带 `inputSchema` 和 `outputSchema`（JSON Schema draft 2020-12）。
4. `tools/call` 执行工具。未知工具名返回 JSON-RPC error，`code` 为 `-32602`。

`initialize` 和 `tools/list` 同样要带第 3 节的身份头。没有身份头时返回 HTTP 401，不要在未认证时把工具列表暴露出去。

一次 `tools/call` 的请求：

```json
{
  "jsonrpc": "2.0",
  "id": "1",
  "method": "tools/call",
  "params": {
    "name": "list_plans",
    "arguments": {
      "created_by": "zhangsan",
      "created_after": "2026-09-30T00:00:00+08:00",
      "created_before": "2026-10-01T00:00:00+08:00",
      "page_size": 20
    }
  }
}
```

成功时 HTTP 200，JSON-RPC `result` 同时带 `content` 和 `structuredContent`。`structuredContent` 是规范结果。`content[0].text` 必须是同一份 JSON 的字符串，不能改成自然语言。

```json
{
  "jsonrpc": "2.0",
  "id": "1",
  "result": {
    "content": [
      {
        "type": "text",
        "text": "{\"items\":[],\"next_cursor\":null}"
      }
    ],
    "structuredContent": {
      "items": [],
      "next_cursor": null
    },
    "isError": false
  }
}
```

`content[0].text` 是 `structuredContent` 的 JSON 字符串，UTF-8，不带 Markdown 围栏。

业务错误（参数不合法、没有权限、找不到、版本冲突）也返回 HTTP 200 的 `tools/call` 结果，`isError` 为 `true`，`structuredContent` 使用第 5.5 节的错误对象。不要用 HTTP 404 或 HTTP 409 表达业务错误。

只有协议层失败才使用 JSON-RPC error 或 HTTP 错误：

| 情况 | 返回 |
| --- | --- |
| JWT 缺失、过期、签名错误或声明不合法 | HTTP 401，正文可以是 JSON |
| 请求不是合法 JSON | HTTP 400 |
| 方法不存在 | JSON-RPC error `-32601` |
| 工具参数不是对象、工具不存在 | JSON-RPC error `-32602` |
| 平台内部异常 | `isError: true`，`code` 为 `INTERNAL`。`message` 不包含 SQL、堆栈、内网地址和密钥 |

单次调用的服务端处理时间不超过 10 秒。`run_plan` 只负责受理，必须在这个时间内返回 `execution_id`，不能等巡检跑完。

## 3. 身份与权限

每一次请求代表一名最终用户。调用方把该用户的 JWT 放在请求头：

```http
Authorization: Bearer <JWT>
```

MCP 验证这个 JWT。签名密钥由双方在仓库之外约定，不写进文档。下面任何一项不满足都返回 HTTP 401：

| 项 | 要求 |
| --- | --- |
| 算法 | `HS256`。`alg` 为 `none`、其他算法或签名错误都拒绝 |
| `iss` | `inspection-platform` |
| `aud` | `inspection-mcp` |
| `username` | 已授权用户的平台用户名，例如 `alice`、`bob`。调用方用它作为 `created_by` 的筛选值 |
| `exp` | 未过期的过期时间 |

权限：

- 按 `username` 对应用户在巡检平台上的权限过滤和授权。用户看不见、不能操作的业务，查询结果里不出现，写入返回 `PERMISSION_DENIED`。
- 不能因为 JWT 签名有效就返回全部业务的数据。
- 查询条件命中了存在但无权访问的对象时，按「没有这条数据」处理：列表里不返回它，按编号读取返回 `NOT_FOUND`。不要告诉调用方这个对象实际存在。
- JWT 无效返回 HTTP 401。JWT 有效但权限不足返回 `PERMISSION_DENIED`。两者不要混用。
- 写入和执行的审计记录使用 `username`，不要记成一个公共服务账号。

不允许只提供一个能查看全部数据的服务账号。

签名密钥不进入仓库。测试账号使用已授权用户，例如 `alice` 和 `bob`。还需要确认这两个账号各自能操作哪些业务，以及一条成功执行和一条失败执行的 `execution_id`。

## 4. 工具总表

读工具必须允许并发调用。写工具和 `run_plan` 必须按第 5.4 节在服务端保证并发安全，不能依赖调用方串行。

| 工具 | 读写 | 作用 |
| --- | --- | --- |
| `list_businesses` | 读 | 按名称或别名找业务 |
| `list_clusters` | 读 | 按业务查集群 |
| `get_cluster` | 读 | 按编号取一个集群 |
| `list_modules` | 读 | 按业务或集群查模块 |
| `get_module` | 读 | 按编号取一个模块 |
| `list_hosts` | 读 | 按条件查主机，可按集群、模块筛选，含「还没有某项巡检」的主机 |
| `get_host` | 读 | 按编号取一台主机 |
| `list_check_items` | 读 | 列出平台已有的检查项 |
| `list_host_groups` | 读 | 查主机组 |
| `get_host_group` | 读 | 取一个主机组 |
| `create_host_group` | 写 | 新建主机组 |
| `update_host_group` | 写 | 修改主机组 |
| `delete_host_group` | 写 | 删除主机组 |
| `list_schemes` | 读 | 查巡检方案 |
| `get_scheme` | 读 | 取一个巡检方案 |
| `create_scheme` | 写 | 新建巡检方案 |
| `update_scheme` | 写 | 修改巡检方案 |
| `delete_scheme` | 写 | 删除巡检方案 |
| `list_plans` | 读 | 查巡检计划 |
| `get_plan` | 读 | 取一个巡检计划 |
| `create_plan` | 写 | 新建巡检计划 |
| `update_plan` | 写 | 修改巡检计划，包括暂停和启用 |
| `delete_plan` | 写 | 删除巡检计划 |
| `run_plan` | 写 | 试跑或立即执行 |
| `list_executions` | 读 | 查执行历史 |
| `get_execution` | 读 | 取一次执行的摘要和当时的配置快照 |
| `list_execution_host_results` | 读 | 按主机分页取执行结果 |
| `summarize_execution_host_results` | 读 | 按主机、计划或检查项汇总 |

## 5. 通用约定

### 5.1 字段与时间

- 字段名使用 `snake_case`。布尔字段以 `is_` 或 `has_` 开头。枚举值使用 `UPPER_SNAKE`。
- 编号是字符串，由平台生成，创建后不变。不同资源的编号空间必须分开，不能把主机组编号当成计划编号使用。
- 时间使用 RFC3339，带时区偏移，精度至少到秒。例如 `2026-09-30T15:20:00+08:00`。不允许只返回 `2026-09-30 15:20:00` 这种不带时区的字符串。
- 平台统一按 `Asia/Shanghai` 解释「每天 8 点」这类周期，除非计划上另有 `timezone`。
- 未设置的可选字段返回 `null`，不要省略，也不要返回空字符串代替 `null`。
- 列表字段没有元素时返回 `[]`。

### 5.2 分页

所有 `list_*` 和 `summarize_execution_host_results` 都分页。

| 参数 | 类型 | 要求 |
| --- | --- | --- |
| `page_size` | 整数 | 可选。默认 50，最小 1，最大 200。超出范围返回 `VALIDATION_ERROR` |
| `cursor` | 字符串 | 可选。第一页不传。传入上次响应的 `next_cursor` |

响应：

| 字段 | 类型 | 要求 |
| --- | --- | --- |
| `items` | 数组 | 本页数据。汇总接口的字段名是 `buckets`，见该工具 |
| `next_cursor` | 字符串或 null | 没有下一页时为 `null` |

`cursor` 不透明。调用方不解析它。同一组筛选条件之下，游标必须能稳定向后翻页：不能漏行，也不能因为翻页过程中新增了一条数据就重复返回已经返回过的行。排序在每个列表工具里单独规定，未指定时按 `created_at` 降序，相同时按 `id` 降序。

不使用页码。页码在有新数据插入时会漏或重复。

### 5.3 筛选

字符串筛选：

| 参数 | 匹配 |
| --- | --- |
| `name_contains` | 名称子串，不区分大小写 |
| `business_name` | 先精确匹配业务名称；未命中再精确匹配该业务的别名；仍不区分大小写 |
| `created_by` | 精确匹配平台用户名 |

时间筛选是前闭后开区间：`created_after <= created_at < created_before`。只传一端时另一端不限制。`updated_after` 同理，作用在 `updated_at` 上。

多个筛选条件同时存在时是「并且」关系。

### 5.4 版本、重名与幂等

主机组、方案、计划必须带：

| 字段 | 类型 | 要求 |
| --- | --- | --- |
| `version` | 整数 | 从 1 开始。每次成功的更新加 1。删除不复用这个编号 |
| `created_at` | 时间 | 创建成功的时间 |
| `updated_at` | 时间 | 与 `version` 一起变化。只改了无关展示字段也要变化 |
| `created_by` | 字符串 | 创建者的平台用户名 |
| `updated_by` | 字符串 | 最后一次更新者的平台用户名 |

更新和删除必须带 `expected_version`。服务端比较该对象当前的 `version`：

- 一致：执行更新或删除，更新成功后 `version` 加 1。
- 不一致：不修改，返回 `VERSION_CONFLICT`。`details.current` 是当前完整对象，供调用方把差异展示给用户。
- 对象不存在或无权访问：`NOT_FOUND`，不要先透露版本号。

同一业务内，主机组名称、方案名称、计划名称各自唯一，比较时去掉首尾空格、不区分大小写。重复创建返回 `ALREADY_EXISTS`，`details.existing` 是已存在的对象。

每次创建和每次 `run_plan` 都要带 `idempotency_key`（调用方生成的 UUID）。平台至少保留 24 小时：

- 同一个用户、同一个工具、同一个 `idempotency_key`、同一份参数：返回第一次的成功结果，不新建第二条，也不再次执行。
- 同一个键但参数不同：返回 `IDEMPOTENCY_CONFLICT`，不写入。
- 第一次还在处理中时又收到同一个键：不要并行创建两份。等第一次结束后返回同一次结果。

删除已经不存在的对象，且 `idempotency_key` 能对应到同一次删除时，返回第一次的成功结果。没有对应键又确实不存在时返回 `NOT_FOUND`。

### 5.5 错误对象

`isError` 为 `true` 时，`structuredContent` 固定为：

```json
{
  "code": "VERSION_CONFLICT",
  "message": "主机组 hg_123 已被其他人修改",
  "details": {
    "current": {}
  }
}
```

| code | 含义 | details |
| --- | --- | --- |
| `VALIDATION_ERROR` | 缺字段、类型错误、枚举不在范围内、分页或时间范围不合法 | `fields`：字段路径到原因的数组 |
| `PERMISSION_DENIED` | JWT 有效，但不能操作这个业务或动作 | `business_id` 可选 |
| `NOT_FOUND` | 编号不存在，或存在但当前用户不能看 | 空对象 |
| `ALREADY_EXISTS` | 同一业务下名称已存在 | `existing`：已存在的对象 |
| `VERSION_CONFLICT` | `expected_version` 与当前不一致 | `current`：当前完整对象 |
| `IDEMPOTENCY_CONFLICT` | 同一个幂等键对应了不同参数 | `idempotency_key` |
| `PRECONDITION_FAILED` | 对象状态不允许这个动作，例如删除仍被计划引用的主机组，或执行已暂停的计划 | `reason` |
| `RATE_LIMITED` | 调用过快 | `retry_after_seconds` |
| `INTERNAL` | 平台内部错误 | 空对象。不返回内部异常文本 |

`message` 使用中文，给用户看。调用方的分支只看 `code`，不看 `message` 的措辞。

### 5.6 引用完整性

- 主机组的 `cluster_ids`、`module_ids`、`host_ids` 必须都属于该主机组的 `business_id`。夹带其他业务的集群、模块或主机返回 `VALIDATION_ERROR`。
- 方案的 `business_id` 与其中检查项没有跨业务限制，但 `check_item_id` 必须来自 `list_check_items`。
- 计划的 `scheme_id` 和 `host_group_id` 必须存在、当前用户可操作，且二者的 `business_id` 与计划的 `business_id` 相同。否则 `VALIDATION_ERROR`。
- 删除主机组前，若仍有未删除的计划引用它，返回 `PRECONDITION_FAILED`，不要级联删除计划。方案被计划引用时同样处理。
- 更新时未出现的字段保持原值。出现且值为 `null` 的字段，仅当该字段允许清空时才清空；必填字段传 `null` 返回 `VALIDATION_ERROR`。

## 6. 资源字段

### 6.1 业务 `Business`

只查询。`name` 和 `aliases` 都必须能被名称条件命中，使简称可以解析到业务。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | 字符串 | 业务编号 |
| `name` | 字符串 | 正式名称 |
| `aliases` | 字符串数组 | 口语或简称，例如 `["支付"]`。没有则 `[]` |
| `host_count` | 整数 | 当前用户在该业务下可见的主机数 |

层级是：业务包含集群，集群包含模块，模块包含主机。一台主机可以属于同一业务下的多个模块。主机不能属于其他业务的集群或模块。

### 6.2 集群 `Cluster`

只查询。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | 字符串 | 集群编号 |
| `name` | 字符串 | 集群名称 |
| `business_id` | 字符串 | 所属业务 |
| `business_name` | 字符串 | 所属业务名称，由服务端填好 |
| `module_count` | 整数 | 该集群下、当前用户可见的模块数 |
| `host_count` | 整数 | 这些模块中、当前用户可见的主机数。同一台主机出现在多个模块时只计一次 |

### 6.3 模块 `Module`

只查询。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | 字符串 | 模块编号 |
| `name` | 字符串 | 模块名称 |
| `business_id` | 字符串 | 所属业务 |
| `business_name` | 字符串 | 所属业务名称，由服务端填好 |
| `cluster_id` | 字符串 | 所属集群 |
| `cluster_name` | 字符串 | 所属集群名称，由服务端填好 |
| `host_count` | 整数 | 该模块下、当前用户可见的主机数 |

### 6.4 主机 `Host`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | 字符串 | 主机编号 |
| `name` | 字符串 | 主机名 |
| `ip` | 字符串 | 主 IP。没有则 `null` |
| `business_id` | 字符串 | 所属业务 |
| `business_name` | 字符串 | 所属业务名称，由服务端填好 |
| `modules` | 对象数组 | 主机所在的模块。每项含 `id`、`name`、`cluster_id`、`cluster_name`。没有模块时为 `[]` |
| `os` | 字符串或 null | 操作系统 |
| `status` | 枚举 | `ONLINE`、`OFFLINE`、`UNKNOWN` |
| `tags` | 字符串数组 | 例如 `["mysql", "prod"]` |

### 6.5 检查项 `CheckItem`

只查询平台已经存在的检查项。不提供新增检查项或上传脚本的工具。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | 字符串 | 检查项编号 |
| `name` | 字符串 | 名称，例如「磁盘使用率」 |
| `description` | 字符串 | 检查什么 |
| `default_threshold` | 字符串或 null | 默认阈值的展示值，例如 `"80%"` |
| `default_timeout_seconds` | 整数 | 默认超时，秒 |
| `value_unit` | 字符串或 null | 结果单位，例如 `"%"` |

### 6.6 方案中的一项检查 `SchemeCheck`

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `check_item_id` | 字符串 | 是 | 来自 `list_check_items` |
| `check_item_name` | 字符串 | 响应必有 | 创建请求里可以不传，响应里必须带回 |
| `threshold` | 字符串 | 是 | 例如 `"80%"`、`"90"`。平台要能在执行时解释 |
| `timeout_seconds` | 整数 | 是 | 大于 0，建议上限 3600。超出平台能力时返回 `VALIDATION_ERROR` 并在 `message` 里写明允许范围 |

### 6.7 主机组 `HostGroup`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | 字符串 | |
| `name` | 字符串 | 同一 `business_id` 下唯一 |
| `business_id` | 字符串 | 创建后不可改。更新时若传入不同的值，返回 `VALIDATION_ERROR` |
| `business_name` | 字符串 | 响应字段 |
| `description` | 字符串或 null | |
| `cluster_ids` | 字符串数组 | 创建或更新时传入的集群。没有则为 `[]` |
| `module_ids` | 字符串数组 | 创建或更新时传入的模块。没有则为 `[]` |
| `host_ids` | 字符串数组 | 创建或更新时直接传入的主机。没有则为 `[]`。这是显式指定的主机，不是展开后的全部成员 |
| `resolved_host_ids` | 字符串数组 | 实际成员。由 `cluster_ids` 下的主机、`module_ids` 下的主机和 `host_ids` 取并集并去重。服务端按编号排序 |
| `host_count` | 整数 | 等于 `resolved_host_ids` 的长度 |
| `version` | 整数 | 见第 5.4 节 |
| `created_at` / `updated_at` | 时间 | |
| `created_by` / `updated_by` | 字符串 | |

成员在创建和更新时展开一次并保存。之后集群或模块里增减主机，不会自动改变 `resolved_host_ids`。

`get_host_group` 和写入响应返回 `cluster_ids`、`module_ids`、`host_ids` 和完整的 `resolved_host_ids`。`list_host_groups` 不返回 `resolved_host_ids`，只返回 `host_count` 以及 `cluster_ids`、`module_ids`，避免一页里带出上万个主机编号。

### 6.8 巡检方案 `Scheme`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | 字符串 | |
| `name` | 字符串 | 同一业务下唯一 |
| `business_id` / `business_name` | 字符串 | `business_id` 创建后不可改 |
| `description` | 字符串或 null | |
| `checks` | `SchemeCheck` 数组 | 至少 1 项。同一个 `check_item_id` 不能出现两次 |
| `version` 及审计字段 | | 同主机组 |

### 6.9 巡检计划 `Plan`

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | 字符串 | |
| `name` | 字符串 | 同一业务下唯一 |
| `business_id` / `business_name` | 字符串 | 创建后不可改 |
| `scheme_id` | 字符串 | |
| `scheme_name` | 字符串 | 响应字段 |
| `host_group_id` | 字符串 | |
| `host_group_name` | 字符串 | 响应字段 |
| `schedule_type` | 枚举 | `CRON` 或 `MANUAL`。`MANUAL` 表示不自动跑，只能 `run_plan` |
| `cron` | 字符串或 null | `schedule_type` 为 `CRON` 时必填。五段 cron：分、时、日、月、周。例如每天 08:00 是 `0 8 * * *`。不接受六段（带秒）cron |
| `timezone` | 字符串 | IANA 时区，默认 `Asia/Shanghai` |
| `status` | 枚举 | `ENABLED` 或 `PAUSED`。暂停用更新，不单设工具 |
| `notify_users` | 字符串数组 | 这个计划的通知人，创建和修改计划时与其他字段一起提交。元素是平台上的通知人标识，服务端原样保存。没有通知人时为 `[]`。不单独提供通知人的查询或增删改工具 |
| `version` 及审计字段 | | 同主机组 |

### 6.10 执行 `Execution`

一次 `run_plan` 或一次到期调度产生一条执行。编号创建后不变。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | 字符串 | 执行编号，创建后不变 |
| `plan_id` / `plan_name` | 字符串 | |
| `business_id` / `business_name` | 字符串 | |
| `trigger` | 枚举 | `SCHEDULED`（到期）、`TEST_RUN`（试跑）、`RUN_NOW`（立即执行） |
| `status` | 枚举 | `PENDING`、`RUNNING`、`SUCCEEDED`、`PARTIAL_FAILED`、`FAILED`、`CANCELLED` |
| `started_at` | 时间或 null | 尚未开始为 `null` |
| `finished_at` | 时间或 null | 未结束为 `null` |
| `host_total` | 整数 | 这次应执行的主机数 |
| `host_succeeded` | 整数 | 主机执行成功且全部检查正常 |
| `host_failed` | 整数 | 主机没能完成执行：离线、超时、权限、脚本错误 |
| `host_abnormal` | 整数 | 主机执行成功，但至少一项检查不正常 |
| `scheme_snapshot` | 对象 | 开始执行时的方案副本，字段同 `Scheme`。之后方案被修改，这条快照不变 |
| `host_group_snapshot` | 对象 | 开始执行时的主机组副本，含当时的 `host_ids` |
| `created_by` | 字符串 | 调度触发时为 `system`；试跑和立即执行为发起人 |

`PENDING` 和 `RUNNING` 的计数字段随着主机完成而增加，允许总和暂时小于 `host_total`。结束后三者之和等于 `host_total`。

### 6.11 单台主机的结果 `HostResult`

一次执行里，参与执行的每台主机恰好一条，成功和失败的主机都要有。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `execution_id` | 字符串 | |
| `host_id` | 字符串 | |
| `host_name` | 字符串 | 执行当时的名称 |
| `host_ip` | 字符串或 null | |
| `status` | 枚举 | 见下表 |
| `started_at` / `finished_at` | 时间或 null | |
| `error_code` | 字符串或 null | 执行失败时必填 |
| `error_message` | 字符串或 null | 给人读的失败原因，可以是脚本输出的摘要，最长 4000 字符，超出则截断并在末尾加 `...(truncated)` |
| `checks` | 数组 | 执行成功时，方案里的每一项检查一条。执行失败且没有检查结果时为 `[]` |

`status`：

| 值 | 含义 |
| --- | --- |
| `PENDING` / `RUNNING` | 尚未结束 |
| `SUCCEEDED` | 执行完成，全部检查正常 |
| `ABNORMAL` | 执行完成，至少一项检查不正常 |
| `FAILED` | 脚本或采集报错，属于执行失败 |
| `TIMEOUT` | 超过该主机允许的时间，属于执行失败 |
| `UNREACHABLE` | 主机 agent 离线或连不上，属于执行失败 |
| `PERMISSION_DENIED` | 主机上权限不足，属于执行失败 |

`error_code` 在 `FAILED`、`TIMEOUT`、`UNREACHABLE`、`PERMISSION_DENIED` 时必填，建议与 `status` 相同或更细。`SUCCEEDED` 和 `ABNORMAL` 时为 `null`。

`checks` 的每一项：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `check_item_id` | 字符串 | |
| `check_item_name` | 字符串 | |
| `status` | 枚举 | `OK`、`ABNORMAL`、`ERROR` |
| `value` | 字符串或 null | 实际值，例如 `"92%"` |
| `threshold` | 字符串或 null | 当时使用的阈值 |
| `message` | 字符串或 null | 补充说明，最长 2000 字符 |

主机 `status` 为 `ABNORMAL` 时，`checks` 里至少一项是 `ABNORMAL`。主机 `status` 为 `SUCCEEDED` 时，每一项都是 `OK`。

## 7. 查询工具

### 7.1 `list_businesses`

按名称或别名查询当前用户有权查看的业务。

参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `name_contains` | 字符串 | 否 | 同时匹配 `name` 和 `aliases` |
| `page_size` / `cursor` | | 否 | |

响应：`items` 为 `Business` 数组，外加 `next_cursor`。只返回当前用户有权查看的业务。排序按 `name` 升序。

### 7.2 `list_clusters`、`get_cluster`

`list_clusters` 查询某个业务下的集群。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `business_id` | 字符串 | 与 `business_name` 至少填一个 | 两个都填时必须指向同一业务，否则 `VALIDATION_ERROR` |
| `business_name` | 字符串 | 同上 | 按第 5.3 节匹配名称或别名。匹配到 0 个返回空列表；匹配到多个返回 `VALIDATION_ERROR`，`details.candidates` 为这些业务的 `id` 和 `name` |
| `name_contains` | 字符串 | 否 | 匹配集群名称 |
| `page_size` / `cursor` | | 否 | |

响应：`items` 为 `Cluster` 数组，外加 `next_cursor`。只返回当前用户有权查看的集群。排序按 `name` 升序。

`get_cluster` 的参数是 `id`（必填）。响应是一个 `Cluster`。不存在或无权为 `NOT_FOUND`。

### 7.3 `list_modules`、`get_module`

`list_modules` 查询模块。模块必须属于指定业务；还可以再限定到一个集群。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `business_id` | 字符串 | 与 `business_name` 至少填一个 | 规则同 `list_clusters` |
| `business_name` | 字符串 | 同上 | 规则同 `list_clusters` |
| `cluster_id` | 字符串 | 否 | 只返回该集群下的模块。集群不属于本次业务时返回 `VALIDATION_ERROR` |
| `cluster_name` | 字符串 | 否 | 在本次业务内按名称精确匹配，不区分大小写。匹配到 0 个返回空列表；匹配到多个返回 `VALIDATION_ERROR`，`details.candidates` 为这些集群的 `id` 和 `name` |
| `name_contains` | 字符串 | 否 | 匹配模块名称 |
| `page_size` / `cursor` | | 否 | |

`cluster_id` 和 `cluster_name` 都填时必须指向同一集群，否则 `VALIDATION_ERROR`。

响应：`items` 为 `Module` 数组，外加 `next_cursor`。排序按 `name` 升序。

`get_module` 的参数是 `id`（必填）。响应是一个 `Module`。不存在或无权为 `NOT_FOUND`。

### 7.4 `list_hosts`

参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `business_id` | 字符串 | 与 `business_name` 至少填一个 | 两个都填时必须指向同一业务，否则 `VALIDATION_ERROR` |
| `business_name` | 字符串 | 同上 | 按第 5.3 节匹配名称或别名。匹配到 0 个返回空列表；匹配到多个返回 `VALIDATION_ERROR`，`details.candidates` 为这些业务的 `id` 和 `name` |
| `name_contains` | 字符串 | 否 | 匹配主机名 |
| `ip` | 字符串 | 否 | 精确匹配 |
| `tag` | 字符串 | 否 | `tags` 包含该值 |
| `status` | 枚举 | 否 | `ONLINE`、`OFFLINE`、`UNKNOWN` |
| `cluster_id` | 字符串 | 否 | 返回该集群下任一模块中的主机 |
| `cluster_name` | 字符串 | 否 | 在本次业务内按名称精确匹配，规则同 `list_modules` 的 `cluster_name` |
| `module_id` | 字符串 | 否 | 只返回该模块中的主机。模块不属于本次业务时返回 `VALIDATION_ERROR` |
| `module_name` | 字符串 | 否 | 在本次业务内按名称精确匹配，不区分大小写。未同时指定集群时，同名模块跨集群命中多个则返回 `VALIDATION_ERROR`，`details.candidates` 含 `id`、`name`、`cluster_id`、`cluster_name` |
| `host_group_id` | 字符串 | 否 | 只返回该主机组的成员 |
| `missing_check_item_id` | 字符串 | 否 | 见下方 |
| `page_size` / `cursor` | | 否 | |

`missing_check_item_id` 用于「找出还没有某项巡检的主机」。返回的主机必须同时满足：

- 属于这次查询的业务；
- 不存在这样的计划：计划 `status` 为 `ENABLED`，计划的主机组包含该主机，计划引用的方案包含这个 `check_item_id`。

已暂停的计划不算覆盖。检查项编号不存在时返回 `VALIDATION_ERROR`。

集群和模块同时传入时，模块必须属于该集群，否则 `VALIDATION_ERROR`。只传集群时，返回该集群下所有模块里的主机，同一台主机只出现一次。

响应：`items` 为 `Host` 数组，外加 `next_cursor`。每台主机的 `modules` 返回它在本次业务下的全部模块，不因筛选条件被裁掉。排序按 `id` 升序。

### 7.5 `get_host`

参数：`id`（必填）。响应：一个 `Host`。不存在或无权为 `NOT_FOUND`。

### 7.6 `list_check_items`

参数：`name_contains`（可选）、`page_size`、`cursor`。响应：`items` 为 `CheckItem` 数组。当前用户只要能配置巡检，就应能看到平台提供的检查项目录。排序按 `name` 升序。

### 7.7 列表共有的对象筛选

`list_host_groups`、`list_schemes`、`list_plans` 都接受：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `business_id` | 字符串 | 否 | |
| `business_name` | 字符串 | 否 | 规则同 `list_hosts` |
| `name_contains` | 字符串 | 否 | |
| `created_by` | 字符串 | 否 | 「我昨天创建的」会传当前用户名 |
| `created_after` / `created_before` | 时间 | 否 | 前闭后开 |
| `updated_after` | 时间 | 否 | |
| `page_size` / `cursor` | | 否 | |

另外：

| 工具 | 额外参数 | 说明 |
| --- | --- | --- |
| `list_schemes` | `check_item_id` | 方案包含该检查项 |
| `list_plans` | `status` | `ENABLED` 或 `PAUSED` |
| `list_plans` | `scheme_id` | |
| `list_plans` | `host_group_id` | |
| `list_plans` | `schedule_type` | `CRON` 或 `MANUAL` |

`created_by` 与 `created_after`、`created_before` 必须能同时生效。例如按某个用户名加上一天的时间范围筛选计划，0 条、1 条、多条都要稳定返回，不能漏掉边界上的记录。

响应里的 `items` 分别是 `HostGroup`、`Scheme`、`Plan`。主机组列表不含 `host_ids`。排序按 `created_at` 降序。

### 7.8 `get_host_group`、`get_scheme`、`get_plan`

参数都是 `id`（必填）。响应是对应的完整对象。`get_host_group` 包含完整 `host_ids`。

## 8. 写入工具

三个资源的创建、更新、删除规则相同，字段不同。服务端必须自行完成第 5 节的校验，不能假设调用方传入的数据已经合法。

### 8.1 创建

共同参数：

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `idempotency_key` | 字符串 | 是 | UUID |
| `business_id` | 字符串 | 是 | |
| `name` | 字符串 | 是 | 去掉首尾空格后长度 1 到 64 |
| `description` | 字符串或 null | 否 | 最长 500 |

`create_host_group` 另外接受下面三个数组，都可以传，至少要有一个非空：

| 参数 | 说明 |
| --- | --- |
| `cluster_ids` | 这些集群下的主机都纳入主机组 |
| `module_ids` | 这些模块下的主机都纳入主机组 |
| `host_ids` | 直接指定的主机 |

`business_id` 仍在共同参数里，必填。集群、模块、主机都必须属于这个业务。服务端取并集、去重后写入 `resolved_host_ids`。并集为空时返回 `VALIDATION_ERROR`，不创建。

`create_scheme` 另需 `checks`：`SchemeCheck` 数组，至少 1 项。请求里的 `check_item_name` 可以不传。

`create_plan` 另需：

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `scheme_id` | 是 | |
| `host_group_id` | 是 | |
| `schedule_type` | 是 | |
| `cron` | `CRON` 时必填 | 五段 |
| `timezone` | 否 | 默认 `Asia/Shanghai` |
| `status` | 否 | 默认 `ENABLED` |
| `notify_users` | 否 | 这个计划的通知人，默认 `[]`。没有单独的通知人接口 |

响应：创建后的完整对象，`version` 为 1。

名称重复返回 `ALREADY_EXISTS`，不创建。幂等重试返回第一次创建的对象，即使名称现在看起来冲突，只要键和参数相同。

### 8.2 更新

共同参数：`id`、`expected_version`、`idempotency_key` 必填。其余字段都可选，只改传入的字段。

| 工具 | 可改字段 | 不可改 |
| --- | --- | --- |
| `update_host_group` | `name`、`description`、`cluster_ids`、`module_ids`、`host_ids` | `business_id`。三个范围数组里，传入的那个整体替换，没传入的保持原值；传入 `[]` 表示清空这一项。替换后至少还要剩一个非空范围，且重新展开后的 `resolved_host_ids` 不能为空 |
| `update_scheme` | `name`、`description`、`checks` | `business_id`。`checks` 若传入，整体替换 |
| `update_plan` | `name`、`description`、`scheme_id`、`host_group_id`、`schedule_type`、`cron`、`timezone`、`status`、`notify_users` | `business_id` |

把计划改成 `PAUSED` 即暂停，改成 `ENABLED` 即恢复。`schedule_type` 改为 `MANUAL` 时，`cron` 应被清空；改为 `CRON` 时本次或对象上必须有 `cron`。

响应：更新后的完整对象。

### 8.3 删除

参数：`id`、`expected_version`、`idempotency_key`，都必填。

被未删除的计划引用时返回 `PRECONDITION_FAILED`，不删除。成功时 `structuredContent` 为：

```json
{
  "id": "hg_123",
  "deleted": true
}
```

## 9. 执行与执行历史

### 9.1 `run_plan`

受理一次执行，立即返回，不等待主机跑完。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `plan_id` | 字符串 | 是 | |
| `mode` | 枚举 | 是 | `TEST_RUN` 或 `RUN_NOW`。二者都要真正执行；区别记在执行的 `trigger` 上，便于和到期调度分开 |
| `idempotency_key` | 字符串 | 是 | 同一个键只能产生一条执行 |

计划不存在返回 `NOT_FOUND`。计划 `status` 为 `PAUSED` 时返回 `PRECONDITION_FAILED`，不执行，也不要自动改成 `ENABLED`。主机组为空时返回 `PRECONDITION_FAILED`。

执行开始后，`get_execution` 的 `status` 最迟 30 秒内必须从 `PENDING` 变为 `RUNNING` 或终态。终态包括 `SUCCEEDED`、`PARTIAL_FAILED`、`FAILED`、`CANCELLED`。

成功响应：

```json
{
  "execution_id": "exec_456",
  "status": "PENDING",
  "plan_id": "plan_123"
}
```

相同幂等键再次调用时，返回已经存在的那条执行的 `execution_id` 和当前 `status`，不新开一次。

### 9.2 `list_executions`

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `plan_id` | 字符串 | 否 | |
| `business_id` | 字符串 | 否 | |
| `status` | 枚举 | 否 | 第 6.10 节的执行状态 |
| `trigger` | 枚举 | 否 | |
| `started_after` / `started_before` | 时间 | 否 | 前闭后开，作用在 `started_at`。尚未开始的执行不用这两个条件过滤掉，它们只在不传时间条件时出现 |
| `page_size` / `cursor` | | 否 | |

响应的 `items` 是 `Execution`，但不包含 `scheme_snapshot` 和 `host_group_snapshot`。排序按 `started_at` 降序，未开始的排在最前。

### 9.3 `get_execution`

参数：`id`（必填）。响应是完整 `Execution`，含 `scheme_snapshot` 和 `host_group_snapshot`。两份快照固定为执行开始时的内容，之后方案或主机组被修改，这里也不变。

### 9.4 `list_execution_host_results`

参与该次执行的每台主机都能查到，包括成功的主机。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `execution_id` | 字符串 | 与下面的时间查询二选一 | 查这一次执行 |
| `plan_id` | 字符串 | 否 | 跨多次执行查某计划的主机结果时使用，此时 `started_after` 必填 |
| `started_after` / `started_before` | 时间 | 见左 | 跨执行查询时 `started_after` 必填，范围不超过 31 天 |
| `host_id` | 字符串 | 否 | |
| `status` | 枚举 | 否 | 第 6.11 节的主机状态。可传数组，表示「或」 |
| `page_size` / `cursor` | | 否 | |

`execution_id` 与 `plan_id` 不能同时空。响应的 `items` 是 `HostResult`，按 `host_id` 升序。

`status` 过滤必须生效。不传 `status` 时必须能翻页得到该次执行的全部主机，不能只保留失败主机。

### 9.5 `summarize_execution_host_results`

按主机、计划或检查项返回时间范围内的次数汇总。调用方不需要把全部主机结果拉回后再自行计数。

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `started_after` | 时间 | 是 | |
| `started_before` | 时间 | 是 | 前闭后开，跨度不超过 31 天 |
| `business_id` | 字符串 | 否 | |
| `plan_id` | 字符串 | 否 | |
| `group_by` | 枚举 | 是 | `HOST`、`PLAN`、`CHECK_ITEM` |
| `page_size` / `cursor` | | 否 | |

每个 bucket：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `key` | 字符串 | 分组编号：主机、计划或检查项 |
| `name` | 字符串 | 对应名称 |
| `execution_count` | 整数 | 范围内涉及的执行次数 |
| `failed_count` | 整数 | 主机状态属于执行失败（`FAILED`、`TIMEOUT`、`UNREACHABLE`、`PERMISSION_DENIED`）的次数。`group_by` 为 `CHECK_ITEM` 时改为检查状态 `ERROR` 的次数 |
| `abnormal_count` | 整数 | 主机状态 `ABNORMAL` 的次数。`group_by` 为 `CHECK_ITEM` 时改为检查状态 `ABNORMAL` 的次数 |
| `succeeded_count` | 整数 | 其余成功且正常的次数 |

排序按 `failed_count` 降序，其次 `abnormal_count` 降序，其次 `key` 升序。响应字段是 `buckets` 和 `next_cursor`。

## 10. 验收

下面每一条都要通过，MCP 才算按本文交付。

1. `initialize` 协商到 `2025-06-18`，`tools/list` 含第 4 节全部工具，且每个工具有 `inputSchema` 和 `outputSchema`。
2. 未带 `Authorization`、签名错误、`exp` 已过期、`alg` 不是 `HS256`、`iss` 或 `aud` 不匹配、`username` 不是已授权用户时，得到 HTTP 401。只有业务 A 权限的用户调用 `list_hosts`，结果里没有业务 B 的主机；用业务 B 的编号调用 `get_host` 得到 `NOT_FOUND`。
3. `list_plans` 能按 `created_by` 加一天的时间范围筛选，边界时刻的归属符合前闭后开。
4. `list_businesses` 用别名能找到业务。`list_hosts` 的 `missing_check_item_id` 不把仅被暂停计划覆盖的主机算成已覆盖。
5. 指定业务能列出集群，指定集群能列出模块。`list_hosts` 传入某个 `module_id` 时，只返回该模块中的主机，且每台主机的 `modules` 含该模块。其他业务的 `get_cluster`、`get_module` 返回 `NOT_FOUND`。
6. 连续两次相同的 `create_host_group`（同一幂等键、同一参数）只产生一个主机组，两次响应的 `id` 相同。
7. 同一业务、同一名称再创建，返回 `ALREADY_EXISTS`，且 `details.existing.id` 是已有对象。
8. 用过期的 `expected_version` 更新，对象不变，返回 `VERSION_CONFLICT` 和当前对象。用当前版本更新，`version` 加 1，`updated_at` 变化。
9. 删除仍被计划引用的主机组，返回 `PRECONDITION_FAILED`，主机组还在。
10. `run_plan` 在 10 秒内返回 `execution_id`。同一幂等键不产生第二次执行。
11. 执行结束后，`host_succeeded + host_failed + host_abnormal = host_total`。不带 `status` 过滤时，`list_execution_host_results` 能翻页得到每一台主机。
12. 至少准备一条「主机离线」和一条「磁盘超过阈值」的样例执行。前者主机 `status` 为 `UNREACHABLE`；后者主机 `status` 为 `ABNORMAL`，且 `checks` 里有 `value` 和 `threshold`。
13. 执行开始之后修改方案，`get_execution` 的 `scheme_snapshot` 仍是执行开始时的内容。
14. `summarize_execution_host_results` 在给定一周范围内返回按失败次数排序的主机。
15. 任意业务错误都是 `isError: true` 加第 5.5 节的对象，而不是一段无法解析的文本。
16. `create_host_group` 同时传入一个集群、一个模块和若干 `host_ids` 时，`resolved_host_ids` 是这三部分主机的并集，且每台主机只出现一次。三部分都不传时返回 `VALIDATION_ERROR`。

请实现方回复时给：测试环境 URL、两个测试账号的获取方式、一条成功执行和一条失败执行的 `execution_id`，以及与本文不一致的字段对照表。没有对照表则视为完全按本文实现。
