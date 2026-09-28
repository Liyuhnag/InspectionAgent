# ADR-001: 登录用单 token 会话，存在 Redis

## Status

Accepted

## Date

2026-09-28

## Context

巡检应用只有一个后端。登录要能立刻作废，并且和现有 Sa-Token 项目的用法一致：前端保存 token，每个请求自己带上。页面脚本能读到 `localStorage`，所以 token 被拷走之后必须能失效。

原先规格把 JWT 放进 HttpOnly Cookie。那样页面脚本读不到 token，但登出只能清 Cookie，复制走的 JWT 在过期前仍然有效。也讨论过双 token：短寿命的访问 token 加长寿命的刷新 token。本项目每次请求都能查 Redis，不需要把凭证拆成两份。

## Decision

登录成功后生成一个随机 token，只在响应正文里返回一次。Redis 的键是这个 token 的 SHA-256，值是用户名，过期时间用 `jwt.expires_minutes`。不保存 token 原文，也不写进日志或网址。

之后的请求在 `satoken` 头里带上 token。当前用户只查 Redis，请求体里的用户名无效。每次成功读取当前用户时，把这条记录的过期时间重新设为 `jwt.expires_minutes`，空闲超过这个时间就失效。

退出时删掉 Redis 里的这条记录。复制走的 token 立刻不能用。不使用刷新 token，也不把登录态放进 Cookie。

已经做好的 JWT 工具留在 `backend/app/users/`，浏览器登录不调用它。前端在登录页把 token 放进 `localStorage`，并在请求头里带上。聊天内容继续按文本显示。正式环境用 HTTPS。

## Alternatives Considered

### JWT 放在 HttpOnly Cookie

页面脚本读不到 token。复制走的令牌在过期前仍然能用，因为服务端没有一份可以删掉的会话。和现有前端「自己带 token」的习惯也不一样。

### HttpOnly Cookie 里只放会话编号，用户名仍在 Redis

能同时做到脚本读不到编号，以及登出立刻失效。前端不能自己保存或附带登录态，和 Sa-Token 那套请求头用法不同。这次不选。

### 访问 token 加刷新 token

适合好几个服务各自验签、又不能每次查 Redis 的情况。这里多一个长期凭证，泄漏时更难收。一个会过期、能删除的 token 就够。

## Consequences

- 登出和过期都由 Redis 决定，复制走的 token 会失效。
- Redis 里没有 token 原文。
- 页面脚本仍能读到 `localStorage` 里的 token。聊天页不把内容写成 HTML，用来收窄这条口子。
- 前端登录页负责保存 token 和请求头，不在本决策的后端接口里实现。
