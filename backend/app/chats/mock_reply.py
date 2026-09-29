# -*- coding: utf-8 -*-
"""模拟回复。变化点是以后换成模型输出，切段长度保持不变。"""

import json
from collections.abc import Iterator

CHUNK_SIZE = 4


def mock_reply(text: str) -> str:
    """按用户输入生成一段较长的巡检回复。"""
    paragraphs = (
        f"关于「{text}」：东区今日巡检已完成现场核对，共发现 2 项异常，其余点位正常。",
        "",
        "## 1 号线压力",
        "",
        "- 读数 0.31 MPa，低于运行区间 0.40–0.55 MPa，偏差持续约 20 分钟。",
        "- 现场阀门开度正常，管线无可见泄漏。",
        (
            "- 建议先复核压力变送器零点，并对照上游泵出口压力，"
            "确认是表计漂移还是实际供压不足。"
        ),
        "- 复核完成前，该点标记为待处理，不纳入本班关闭项。",
        "",
        "## 3 号泵房阀门",
        "",
        "- 入口阀、出口阀和旁路阀位置与操作票一致。",
        "- 出口压力 0.42 MPa，振动和温度未见异常，盘车无卡涩。",
        "- 润滑油位在标线中部，地面无积油。此项可以关闭。",
        "",
        "## 其他点位",
        "",
        "- 2 号冷却水泵备用状态已确认，控制柜指示灯正常。",
        "- 东区通道照明有 1 盏不亮，已另行报修。",
        f"- 不影响本次「{text}」的结论。巡检人应写明到达时间和表计照片编号。",
        "- 若下一班压力仍低于 0.40 MPa，升级为异常工单并通知值班长。",
        "- 消防栓铅封完好，应急照明试灯正常，通道无占压。",
        (
            "- 配电间温度 27 摄氏度，湿度在允许范围内，无焦糊味。"
            "接地线连接牢固，柜门关闭并上锁。"
        ),
        "",
        (
            "以上结果仅覆盖本班已到达的点位。"
            "未到达的西区管廊不在本次结论内，留待下一班补检。"
        ),
    )
    return "\n".join(paragraphs)


def iter_chunks(reply: str, size: int = CHUNK_SIZE) -> list[str]:
    """按固定长度切开回复。最后一段可以更短。"""
    return [reply[index:index + size] for index in range(0, len(reply), size)]


def sse_reply(text: str) -> Iterator[str]:
    """把模拟回复写成 chunk 事件，并以 done 结束。"""
    for chunk in iter_chunks(mock_reply(text)):
        payload = json.dumps({"text": chunk}, ensure_ascii=False)
        yield f"event: chunk\ndata: {payload}\n\n"
    yield "event: done\ndata: {}\n\n"
