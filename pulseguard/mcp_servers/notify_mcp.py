import json
from datetime import UTC, datetime
from typing import Any

import httpx
from fastmcp import FastMCP
from pydantic import BaseModel

from pulseguard.config import settings
from pulseguard.logging_config import configure_logging, get_logger
from pulseguard.models.escalation import EscalationBrief
from pulseguard.redis_client import get_async_redis
from pulseguard.tracing import tool_trace

configure_logging()
logger = get_logger(__name__)

mcp = FastMCP("pulseguard-notify-mcp")

_QUEUE_DEPTH_KEY = "pulseguard:escalation:queue_depth"
_ACK_KEY_PREFIX = "pulseguard:escalation:ack:"


class ErrorResponse(BaseModel):
    error: str
    code: str


def _severity_emoji(severity: str) -> str:
    return {"P1": "🔴", "P2": "🟠", "P3": "🟡"}.get(severity, "⚪")


def _format_slack_message(brief: EscalationBrief) -> dict[str, Any]:
    emoji = _severity_emoji(brief.severity)
    return {
        "text": f"{emoji} PulseGuard Escalation: {brief.severity} — {brief.carrier.upper()} — {brief.category}",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {brief.severity} Escalation: {brief.carrier.upper()}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Category:*\n{brief.category}"},
                    {"type": "mrkdwn", "text": f"*Platform:*\n{brief.source_platform}"},
                    {"type": "mrkdwn", "text": f"*Sentiment:*\n{brief.sentiment_score:.2f}"},
                    {
                        "type": "mrkdwn",
                        "text": f"*Churn Risk:*\n{'⚠️ YES' if brief.churn_risk else 'No'}",
                    },
                ],
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Summary:*\n{brief.summary}"},
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Recommended Action:*\n{brief.recommended_action}",
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "View Original Post"},
                        "url": brief.original_post_url,
                        "action_id": "view_post",
                    }
                ],
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Signal ID: `{brief.signal_id}` | Trace: `{brief.escalation_trace_id}`",
                    }
                ],
            },
        ],
    }


def _format_email_body(brief: EscalationBrief) -> str:
    attempted = brief.attempted_resolution or "None"
    return f"""PulseGuard AI — Escalation Brief
================================
Signal ID:     {brief.signal_id}
Priority:      {brief.severity}
Carrier:       {brief.carrier.upper()}
Category:      {brief.category}
Platform:      {brief.source_platform}
Escalated At:  {brief.escalated_at.isoformat()}

Summary
-------
{brief.summary}

Sentiment Score: {brief.sentiment_score:.2f}
Churn Risk: {"YES" if brief.churn_risk else "No"}

Original Post
-------------
{brief.original_post_url}

Attempted Resolution
--------------------
{attempted}

Recommended Action
------------------
{brief.recommended_action}

Trace ID: {brief.escalation_trace_id}
---
PulseGuard AI | Automated Escalation System
"""


@mcp.tool()
@tool_trace("notify", "send_slack_alert")
async def send_slack_alert(brief: dict[str, Any], channel: str = "") -> dict[str, Any]:
    """Send escalation brief to configured Slack webhook."""
    if not settings.slack_webhook_url:
        logger.warning("slack_not_configured")
        return {"sent": False, "reason": "SLACK_WEBHOOK_URL not configured"}

    try:
        eb = EscalationBrief(**brief)
        payload = _format_slack_message(eb)
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(settings.slack_webhook_url, json=payload)
            resp.raise_for_status()
        logger.info("slack_alert_sent", signal_id=eb.signal_id, severity=eb.severity)
        return {"sent": True, "signal_id": eb.signal_id}
    except Exception as exc:
        logger.error("slack_alert_error", error=str(exc))
        return ErrorResponse(error=str(exc), code="SLACK_ERROR").model_dump()


@mcp.tool()
@tool_trace("notify", "send_email_brief")
async def send_email_brief(brief: dict[str, Any], recipient: str = "") -> dict[str, Any]:
    """Send escalation brief via email (SendGrid if key set, else SMTP)."""
    to_addr = recipient or settings.notification_email
    if not to_addr:
        return {"sent": False, "reason": "No recipient configured"}

    try:
        eb = EscalationBrief(**brief)
        subject = f"[{eb.severity}] PulseGuard Escalation: {eb.carrier.upper()} — {eb.category}"
        body = _format_email_body(eb)

        if settings.sendgrid_api_key:
            await _send_via_sendgrid(subject, body, to_addr)
        elif settings.smtp_host:
            await _send_via_smtp(subject, body, to_addr)
        else:
            return {"sent": False, "reason": "No email provider configured"}

        logger.info("email_brief_sent", signal_id=eb.signal_id, recipient=to_addr)
        return {"sent": True, "signal_id": eb.signal_id, "recipient": to_addr}
    except Exception as exc:
        logger.error("email_brief_error", error=str(exc))
        return ErrorResponse(error=str(exc), code="EMAIL_ERROR").model_dump()


async def _send_via_sendgrid(subject: str, body: str, to_addr: str) -> None:
    import sendgrid
    from sendgrid.helpers.mail import Mail

    sg = sendgrid.SendGridAPIClient(api_key=settings.sendgrid_api_key)
    message = Mail(
        from_email=settings.smtp_user or "noreply@pulseguard.ai",
        to_emails=to_addr,
        subject=subject,
        plain_text_content=body,
    )
    sg.send(message)


async def _send_via_smtp(subject: str, body: str, to_addr: str) -> None:
    from email.message import EmailMessage

    import aiosmtplib

    msg = EmailMessage()
    msg["From"] = settings.smtp_user
    msg["To"] = to_addr
    msg["Subject"] = subject
    msg.set_content(body)

    await aiosmtplib.send(
        msg,
        hostname=settings.smtp_host,
        port=settings.smtp_port,
        username=settings.smtp_user,
        password=settings.smtp_password,
        start_tls=True,
    )


@mcp.tool()
@tool_trace("notify", "acknowledge_escalation")
async def acknowledge_escalation(signal_id: str, ack_by: str) -> dict[str, Any]:
    """Mark a human acknowledgement received for an escalation."""
    if not signal_id or not ack_by:
        return ErrorResponse(
            error="signal_id and ack_by are required", code="INVALID_PARAM"
        ).model_dump()
    try:
        redis = get_async_redis()
        ack_data = json.dumps(
            {
                "acknowledged": True,
                "acknowledged_by": ack_by,
                "acknowledged_at": datetime.now(UTC).isoformat(),
            }
        )
        await redis.set(f"{_ACK_KEY_PREFIX}{signal_id}", ack_data)
        await redis.decr(_QUEUE_DEPTH_KEY)
        logger.info("escalation_acknowledged", signal_id=signal_id, ack_by=ack_by)
        return {"acknowledged": True, "signal_id": signal_id, "acknowledged_by": ack_by}
    except Exception as exc:
        logger.error("acknowledge_escalation_error", error=str(exc))
        return ErrorResponse(error=str(exc), code="REDIS_ERROR").model_dump()


@mcp.tool()
@tool_trace("notify", "get_queue_depth")
async def get_queue_depth() -> dict[str, Any]:
    """Return current count of unacknowledged escalations."""
    try:
        redis = get_async_redis()
        depth = await redis.get(_QUEUE_DEPTH_KEY)
        return {"queue_depth": int(depth or 0)}
    except Exception as exc:
        logger.error("get_queue_depth_error", error=str(exc))
        return ErrorResponse(error=str(exc), code="REDIS_ERROR").model_dump()


if __name__ == "__main__":
    mcp.run()
