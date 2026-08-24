# config_car_m.py - CAR-M嵌合抗原受体巨噬细胞研究速递配置

from config_base import (  # noqa: F401 - 这些名称作为动态配置模块的公开属性使用
    EASYSCHOLAR_KEY,
    JOURNALS_CAS1,
    MAX_BACKFILL_DAYS,
    RECEIVER_EMAILS,
    RECENT_DAYS,
    SENDER_EMAIL,
    SMTP_AUTH_CODE,
    SMTP_PORT,
    SMTP_SERVER,
)

TOPICS = [
    {
        "name": "CAR-M",
        "name_zh": "CAR-M嵌合抗原受体巨噬细胞研究速递",
        "query": (
            '("chimeric antigen receptor macrophage*"[Title/Abstract] OR '
            '"CAR macrophage*"[Title/Abstract] OR '
            '"CAR-M"[Title/Abstract] OR '
            '"CAR-Mac"[Title/Abstract] OR '
            '"chimeric antigen receptor"[Title] AND "macrophage*"[Title]) AND '
            f"({JOURNALS_CAS1})"
        ),
        "fallback_query": (
            '"chimeric antigen receptor macrophage*"[Title/Abstract] OR '
            '"CAR macrophage*"[Title/Abstract] OR '
            '"CAR-M"[Title/Abstract] OR '
            '"CAR-Mac"[Title/Abstract] OR '
            '("chimeric antigen receptor"[Title] AND "macrophage*"[Title])'
        ),
        "max_results": 30,
        "min_relevance_score": 6,
    },
]
