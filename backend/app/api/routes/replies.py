# -*- coding: utf-8 -*-
"""模拟回复接口。只校验入参并推送事件流。"""

from fastapi import APIRouter
from fastapi import HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.chats.mock_reply import sse_reply


class ReplyBody(BaseModel):
    """发送一句用户输入。缺少 text 时按空字符串处理。"""

    text: str = ""


def replies_router() -> APIRouter:
    """挂上模拟回复。调用方必须已经登录。"""
    router = APIRouter()

    @router.post("/replies")
    def create_reply(body: ReplyBody) -> StreamingResponse:
        """按段推送固定回复。空文本不建立事件流。"""
        text = body.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="不能为空")
        return StreamingResponse(sse_reply(text), media_type="text/event-stream")

    return router
