from __future__ import annotations

import os
import smtplib
from datetime import datetime, time, timezone
from email.message import EmailMessage
from zoneinfo import ZoneInfo

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models.entities import (
    CreditTransaction,
    DerivedProductRecommendation,
    FastMossSyncLog,
    ModelCallLog,
    TaskExecution,
)


SHANGHAI = ZoneInfo("Asia/Shanghai")


def today_utc_window() -> tuple[datetime, datetime, datetime]:
    now = datetime.now(SHANGHAI)
    local_start = datetime.combine(now.date(), time.min, tzinfo=SHANGHAI)
    local_end = datetime.combine(now.date(), time.max, tzinfo=SHANGHAI)
    return now, local_start.astimezone(timezone.utc).replace(tzinfo=None), local_end.astimezone(timezone.utc).replace(tzinfo=None)


def build_report() -> tuple[str, str]:
    now, start_utc, end_utc = today_utc_window()
    with SessionLocal() as db:
        derived_count = db.scalar(
            select(func.count(DerivedProductRecommendation.id)).where(
                DerivedProductRecommendation.created_at >= start_utc,
                DerivedProductRecommendation.created_at <= end_utc,
            )
        ) or 0
        matched_count = db.scalar(
            select(func.count(DerivedProductRecommendation.id)).where(
                DerivedProductRecommendation.created_at >= start_utc,
                DerivedProductRecommendation.created_at <= end_utc,
                DerivedProductRecommendation.supplier_search_status == "matched",
            )
        ) or 0
        model_total = db.scalar(
            select(func.count(ModelCallLog.id)).where(
                ModelCallLog.created_at >= start_utc,
                ModelCallLog.created_at <= end_utc,
            )
        ) or 0
        model_failed = db.scalar(
            select(func.count(ModelCallLog.id)).where(
                ModelCallLog.created_at >= start_utc,
                ModelCallLog.created_at <= end_utc,
                ModelCallLog.status != "success",
            )
        ) or 0
        sync_count = db.scalar(
            select(func.count(FastMossSyncLog.id)).where(
                FastMossSyncLog.started_at >= start_utc,
                FastMossSyncLog.started_at <= end_utc,
            )
        ) or 0
        task_total = db.scalar(
            select(func.count(TaskExecution.id)).where(
                TaskExecution.created_at >= start_utc,
                TaskExecution.created_at <= end_utc,
            )
        ) or 0
        consumed = db.scalar(
            select(func.coalesce(func.sum(-CreditTransaction.credits), 0)).where(
                CreditTransaction.created_at >= start_utc,
                CreditTransaction.created_at <= end_utc,
                CreditTransaction.transaction_type == "consume",
            )
        ) or 0

    subject = f"益行跨境 AI｜{now:%Y-%m-%d %H:%M} 业务统计"
    body = (
        "益行跨境 AI 平台业务统计\n\n"
        f"统计时间：{now:%Y-%m-%d %H:%M:%S}\n"
        f"今日生成衍生品：{int(derived_count)} 个\n"
        f"今日 1688 匹配成功：{int(matched_count)} 个\n"
        f"今日大模型调用：{int(model_total)} 次，失败 {int(model_failed)} 次\n"
        f"今日 FastMoss 同步：{int(sync_count)} 次\n"
        f"今日任务执行：{int(task_total)} 个\n"
        f"今日积分消耗：{int(consumed)} 分\n"
    )
    return subject, body


def send_report() -> None:
    sender = os.environ["REPORT_SMTP_USER"].strip()
    password = os.environ["REPORT_SMTP_PASSWORD"].strip()
    recipient = os.environ.get("REPORT_EMAIL_TO", "616553527@qq.com").strip()
    host = os.environ.get("REPORT_SMTP_HOST", "smtp.qq.com").strip()
    port = int(os.environ.get("REPORT_SMTP_PORT", "465"))
    subject, body = build_report()
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    with smtplib.SMTP_SSL(host, port, timeout=30) as smtp:
        smtp.login(sender, password)
        smtp.send_message(message)
    print(body, end="")


if __name__ == "__main__":
    send_report()
