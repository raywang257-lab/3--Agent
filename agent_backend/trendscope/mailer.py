from __future__ import annotations

import html
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any

from .config import Settings


def mask_email(address: str) -> str:
    local, separator, domain = address.partition("@")
    if not separator:
        return "***"
    visible = local[:2] if len(local) > 2 else local[:1]
    return f"{visible}***@{domain}"


def build_email_brief(task: Any, run: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    if not events:
        raise ValueError("没有已人工确认的热点，不允许发送邮件")
    completed_at = str(run.get("completed_at") or "")[:19].replace("T", " ")
    subject = f"【TrendScope】{task.topic}热点简报：{len(events)} 个已确认事件"
    text_lines = [
        f"{task.topic}热点简报", f"数据截止：{completed_at}",
        f"AI筛选：{run.get('candidates_created', 0)} 个候选 → {run.get('events_created', 0)} 个入选 → {len(events)} 个人工确认", "",
    ]
    html_sections: list[str] = []
    for index, event in enumerate(events, start=1):
        sources = event.get("sources", [])[:3]
        text_lines.extend([
            f"{index}. {event['canonical_title']}", f"AI总结：{event['summary']}",
            f"为什么现在：{event['why_now']}", f"建议动作：{event['recommended_action']}",
            f"风险：{event['risk']}", f"真实性：{event['truth_status']}",
            *[f"来源：{source['title']} - {source['url']}" for source in sources], "",
        ])
        links = "".join(
            f'<li><a href="{html.escape(source["url"], quote=True)}">{html.escape(source["title"])}</a>'
            f'（{html.escape(source["source"])}）</li>' for source in sources
        )
        html_sections.append(
            f'<section style="padding:18px 0;border-bottom:1px solid #e5e7eb">'
            f'<h2 style="font-size:18px;margin:0 0 10px">{index}. {html.escape(event["canonical_title"])}</h2>'
            f'<p><b>AI总结：</b>{html.escape(event["summary"])}</p>'
            f'<p><b>为什么现在：</b>{html.escape(event["why_now"])}</p>'
            f'<p><b>建议动作：</b>{html.escape(event["recommended_action"])}</p>'
            f'<p><b>风险：</b>{html.escape(event["risk"])}</p><ul>{links}</ul></section>'
        )
    html_body = (
        '<div style="font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;max-width:760px;margin:auto;color:#172033">'
        f'<h1>{html.escape(task.topic)}热点简报</h1><p>数据截止：{html.escape(completed_at)}</p>'
        f'<p>AI筛选：{run.get("candidates_created", 0)} 个候选 → {run.get("events_created", 0)} 个入选 → {len(events)} 个人工确认</p>'
        + "".join(html_sections) + "</div>"
    )
    return {"subject": subject, "text": "\n".join(text_lines), "html": html_body, "selected_count": len(events)}


def send_email(settings: Settings, brief: dict[str, Any]) -> int:
    if not settings.email_configured:
        raise RuntimeError("邮件 SMTP 尚未配置")
    message = EmailMessage()
    message["Subject"] = brief["subject"]
    message["From"] = settings.email_from or settings.smtp_username
    message["To"] = ", ".join(settings.email_recipients)
    message.set_content(brief["text"])
    message.add_alternative(brief["html"], subtype="html")
    context = ssl.create_default_context()
    if settings.smtp_use_ssl:
        with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=30, context=context) as client:
            client.login(settings.smtp_username, settings.smtp_password)
            client.send_message(message)
    else:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30) as client:
            if settings.smtp_use_tls:
                client.starttls(context=context)
            client.login(settings.smtp_username, settings.smtp_password)
            client.send_message(message)
    return len(settings.email_recipients)
