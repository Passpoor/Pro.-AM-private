# config_car_m.py - CAR-M嵌合抗原受体巨噬细胞研究速递配置

from config_base import JOURNALS_CAS1, RECENT_DAYS, MAX_BACKFILL_DAYS, SMTP_SERVER, SMTP_PORT, SENDER_EMAIL, SMTP_AUTH_CODE, RECEIVER_EMAILS

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
            f'({JOURNALS_CAS1})'
        ),
        "fallback_query": (
            '"chimeric antigen receptor macrophage*"[Title/Abstract] OR '
            '"CAR macrophage*"[Title/Abstract] OR '
            '"CAR-M"[Title/Abstract] OR '
            '"CAR-Mac"[Title/Abstract] OR '
            '("chimeric antigen receptor"[Title] AND "macrophage*"[Title])'
        ),
        "max_results": 30,
    },
]