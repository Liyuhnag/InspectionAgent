# InspectionAgent

多 agent 项目骨架。前端用 Vue，后端用 FastAPI。LangChain 用来实现具体 agent，LangGraph 用来编排多 agent 流程。

当前只有目录，业务代码尚未实现。

## 目录

```text
backend/app/
├── api/routes/     # FastAPI 路由
├── agents/         # LangChain agent
├── graphs/         # LangGraph workflow
├── tools/          # agent 可调用的工具
└── prompts/        # 系统提示词
backend/tests/      # 后端测试
frontend/
├── public/         # 静态资源
└── src/
    ├── api/        # 调用后端的请求
    ├── assets/     # 图片、样式等资源
    ├── components/ # 可复用组件
    ├── router/     # 路由
    └── views/      # 页面
```

## 职责

- 新增专家 agent：在 `backend/app/agents/` 中用 LangChain 实现，提示词放在 `backend/app/prompts/`，工具放在 `backend/app/tools/`。
- 新增流程：在 `backend/app/graphs/` 中用 LangGraph 的 `StateGraph` 编排，只引用已有 agent。
- 对外接口：在 `backend/app/api/routes/` 中暴露 FastAPI 路由，由 `frontend/src/api/` 调用。
