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
_ESCALATION_KEY = "pulseguard:escalations"


class ErrorResponse(BaseModel):
    error: str
    code: str


def _severity_emoji(severity: str) -> str:
    return {"P1": "🔴", "P2": "🟠", "P3": "🟡"}.get(severity, "⚪")


def _format_slack_message(brief: EscalationBrief) -> dict[str, Any]:
    emoji = _severity_emoji(brief.severity)
    blocks: list[dict[str, Any]] = [
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
    ]
    # Slack buttons require an absolute http(s) URL — original_post_url is
    # attacker-reachable (it's carried straight through from the ingested
    # signal), so a non-http(s) scheme here gets dropped rather than handed
    # to Slack as-is.
    if brief.original_post_url.startswith(("http://", "https://")):
        blocks.append(
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
            }
        )
    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Signal ID: `{brief.signal_id}` | Trace: `{brief.escalation_trace_id}`",
                }
            ],
        }
    )
    return {
        "text": f"{emoji} PulseGuard Escalation: {brief.severity} — {brief.carrier.upper()} — {brief.category}",
        "blocks": blocks,
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
@tool_trace("notify", "send_webhook_alert")
async def send_webhook_alert(brief: dict[str, Any]) -> dict[str, Any]:
    """POST the escalation brief to a generic configured webhook.

    This is the "plug into anything" integration: point it at a Zapier/Make/
    n8n workflow, a ServiceNow inbound webhook action, or a custom internal
    endpoint, and PulseGuard becomes additive to whatever system-of-record a
    CX team already uses instead of a parallel, non-integrated alert.

    If WEBHOOK_SECRET is set, the raw JSON body is signed the way Stripe/
    GitHub webhooks are — HMAC-SHA256 over the exact bytes sent, hex-encoded,
    in an X-PulseGuard-Signature header — so the receiver can verify the
    request actually came from this PulseGuard instance before acting on it.
    """
    if not settings.webhook_url:
        return {"sent": False, "reason": "WEBHOOK_URL not configured"}

    try:
        import hashlib
        import hmac

        eb = EscalationBrief(**brief)
        body = eb.model_dump_json().encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if settings.webhook_secret:
            signature = hmac.new(
                settings.webhook_secret.encode("utf-8"), body, hashlib.sha256
            ).hexdigest()
            headers["X-PulseGuard-Signature"] = f"sha256={signature}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(settings.webhook_url, content=body, headers=headers)
            resp.raise_for_status()
        logger.info("webhook_alert_sent", signal_id=eb.signal_id, severity=eb.severity)
        return {"sent": True, "signal_id": eb.signal_id}
    except Exception as exc:
        logger.error("webhook_alert_error", error=str(exc))
        return ErrorResponse(error=str(exc), code="WEBHOOK_ERROR").model_dump()


@mcp.tool()
@tool_trace("notify", "send_teams_alert")
async def send_teams_alert(brief: dict[str, Any]) -> dict[str, Any]:
    """Post the escalation brief to a Microsoft Teams channel.

    TEAMS_WEBHOOK_URL must be a channel Workflow's webhook URL (Teams
    channel -> Workflows -> "Post to a channel when a webhook request is
    received"), not a legacy Office 365 Connector URL — Microsoft retired
    incoming webhook connectors in 2026, and old connector URLs no longer
    deliver. A Workflow endpoint accepts the same adaptive-card attachment
    shape sent here.
    """
    if not settings.teams_webhook_url:
        return {"sent": False, "reason": "TEAMS_WEBHOOK_URL not configured"}

    try:
        eb = EscalationBrief(**brief)
        emoji = _severity_emoji(eb.severity)
        card = {
            "type": "AdaptiveCard",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.4",
            "body": [
                {
                    "type": "TextBlock",
                    "text": f"{emoji} {eb.severity} Escalation: {eb.carrier.upper()}",
                    "weight": "bolder",
                    "size": "medium",
                },
                {"type": "TextBlock", "text": eb.summary, "wrap": True},
                {
                    "type": "FactSet",
                    "facts": [
                        {"title": "Category", "value": eb.category},
                        {"title": "Platform", "value": eb.source_platform},
                        {"title": "Churn risk", "value": "Yes" if eb.churn_risk else "No"},
                        {"title": "Recommended action", "value": eb.recommended_action},
                    ],
                },
            ],
            "actions": [
                {
                    "type": "Action.OpenUrl",
                    "title": "View original post",
                    "url": eb.original_post_url,
                }
            ],
        }
        payload = {
            "type": "message",
            "attachments": [
                {"contentType": "application/vnd.microsoft.card.adaptive", "content": card}
            ],
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(settings.teams_webhook_url, json=payload)
            resp.raise_for_status()
        logger.info("teams_alert_sent", signal_id=eb.signal_id, severity=eb.severity)
        return {"sent": True, "signal_id": eb.signal_id}
    except Exception as exc:
        logger.error("teams_alert_error", error=str(exc))
        return ErrorResponse(error=str(exc), code="TEAMS_ERROR").model_dump()


@mcp.tool()
@tool_trace("notify", "send_zendesk_ticket")
async def send_zendesk_ticket(brief: dict[str, Any]) -> dict[str, Any]:
    """Create a Zendesk ticket from the escalation brief.

    PulseGuard never stores a customer's real identity (CLAUDE.md: author
    handles are always hashed, content is always PII-sanitised) — so this
    can't and doesn't create the ticket "as" the customer. It opens an
    internal ticket for the CX team, using the hashed signal_id as Zendesk's
    required unique_external_id so repeat escalations for the same signal
    map to a stable identity without ever exposing PII to Zendesk.
    """
    if not (settings.zendesk_subdomain and settings.zendesk_email and settings.zendesk_api_token):
        return {"sent": False, "reason": "Zendesk credentials not configured"}

    try:
        eb = EscalationBrief(**brief)
        ticket = {
            "ticket": {
                "subject": f"[PulseGuard {eb.severity}] {eb.carrier.upper()} — {eb.category}",
                "comment": {"body": _format_email_body(eb)},
                "priority": {"P1": "urgent", "P2": "high", "P3": "normal"}.get(
                    eb.severity, "normal"
                ),
                "tags": ["pulseguard", eb.carrier, eb.severity.lower()],
                "requester": {
                    "name": "PulseGuard AI",
                    "unique_external_id": f"pulseguard-{eb.signal_id}",
                },
            }
        }
        url = f"https://{settings.zendesk_subdomain}.zendesk.com/api/v2/tickets.json"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                json=ticket,
                auth=(f"{settings.zendesk_email}/token", settings.zendesk_api_token),
            )
            resp.raise_for_status()
        ticket_id = resp.json().get("ticket", {}).get("id")
        logger.info("zendesk_ticket_created", signal_id=eb.signal_id, ticket_id=ticket_id)
        return {"sent": True, "signal_id": eb.signal_id, "ticket_id": ticket_id}
    except Exception as exc:
        logger.error("zendesk_ticket_error", error=str(exc))
        return ErrorResponse(error=str(exc), code="ZENDESK_ERROR").model_dump()


@mcp.tool()
@tool_trace("notify", "send_freshdesk_ticket")
async def send_freshdesk_ticket(brief: dict[str, Any]) -> dict[str, Any]:
    """Create a Freshdesk ticket from the escalation brief.

    Same PII posture as send_zendesk_ticket: no real customer identity is
    sent. Freshdesk's ticket-creation API requires one of
    requester_id/email/phone/twitter_id/facebook_id/unique_external_id — this
    uses unique_external_id keyed on the hashed signal_id for the same reason.
    """
    if not (settings.freshdesk_domain and settings.freshdesk_api_key):
        return {"sent": False, "reason": "Freshdesk credentials not configured"}

    try:
        eb = EscalationBrief(**brief)
        ticket = {
            "subject": f"[PulseGuard {eb.severity}] {eb.carrier.upper()} — {eb.category}",
            "description": _format_email_body(eb),
            "priority": {"P1": 4, "P2": 3, "P3": 2}.get(eb.severity, 2),
            "status": 2,  # Open
            "tags": ["pulseguard", eb.carrier, eb.severity.lower()],
            "unique_external_id": f"pulseguard-{eb.signal_id}",
        }
        url = f"https://{settings.freshdesk_domain}.freshdesk.com/api/v2/tickets"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=ticket, auth=(settings.freshdesk_api_key, "X"))
            resp.raise_for_status()
        ticket_id = resp.json().get("id")
        logger.info("freshdesk_ticket_created", signal_id=eb.signal_id, ticket_id=ticket_id)
        return {"sent": True, "signal_id": eb.signal_id, "ticket_id": ticket_id}
    except Exception as exc:
        logger.error("freshdesk_ticket_error", error=str(exc))
        return ErrorResponse(error=str(exc), code="FRESHDESK_ERROR").model_dump()


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
        brief_raw = await redis.hget(_ESCALATION_KEY, signal_id)
        if not brief_raw:
            return ErrorResponse(
                error=f"Escalation {signal_id} not found", code="NOT_FOUND"
            ).model_dump()

        brief = EscalationBrief(**json.loads(brief_raw))
        if brief.acknowledged:
            # Idempotent: repeat-acknowledging an already-acked escalation
            # must not decrement the queue depth a second time.
            return {
                "acknowledged": True,
                "signal_id": signal_id,
                "acknowledged_by": brief.acknowledged_by,
            }

        brief.acknowledged = True
        brief.acknowledged_by = ack_by
        brief.acknowledged_at = datetime.now(UTC)
        await redis.hset(_ESCALATION_KEY, signal_id, brief.model_dump_json())
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
