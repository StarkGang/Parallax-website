"""Tests for payment fixes: per-event pricing, retry persistence, webhooks and telegram alerts."""

import hashlib
import hmac
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.commerce import PaymentOrder, PaymentTransaction, Registration, Ticket
from app.models.edition import ConventionEdition, Event, EventCategory
from app.models.user import User
from app.services.payments import process_webhook
from app.services.telegram import send_telegram_payment_notification
from app.services.tickets import _payment_summary


@pytest.mark.asyncio
async def test_ticket_payment_summary_uses_event_fee_not_multi_event_order(
    db_session: AsyncSession,
):
    """The receipt line item must show the individual event fee, not the total multi-event order price."""
    # 1. Create order for ₹600 (3 events at ₹200 each)
    edition_id = uuid.uuid4()
    user_id = uuid.uuid4()
    order = PaymentOrder(
        edition_id=edition_id,
        user_id=user_id,
        purpose="registration",
        amount_paise=60000,
        status="paid",
        gateway_order_id="order_multi_123",
        paid_at=datetime.now(UTC),
    )
    db_session.add(order)
    await db_session.flush()

    # 2. Create registration for one of the ₹200 events
    event_id = uuid.uuid4()
    reg = Registration(
        edition_id=edition_id,
        user_id=user_id,
        event_id=event_id,
        kind="addon",
        fee_paise=20000,  # ₹200
        status="confirmed",
        registration_number="REG-EVT01",
        order_id=order.id,
    )
    db_session.add(reg)
    await db_session.flush()

    summary = await _payment_summary(db_session, reg)
    # The line item must reflect the ₹200 event fee, not the ₹600 order sum
    assert summary["amountPaise"] == 20000
    assert summary["itemAmountPaise"] == 20000
    assert summary["orderAmountPaise"] == 60000
    assert summary["gatewayOrderId"] == "order_multi_123"


@pytest.mark.asyncio
async def test_webhook_payment_failed_does_not_fail_order(db_session: AsyncSession):
    """A single failed payment attempt in Razorpay must not mark the order as failed,

    allowing user retries inside the checkout modal.
    """
    edition_id = uuid.uuid4()
    user_id = uuid.uuid4()
    gateway_order_id = f"order_retry_{uuid.uuid4().hex[:8]}"

    order = PaymentOrder(
        edition_id=edition_id,
        user_id=user_id,
        purpose="registration",
        amount_paise=25000,
        status="created",
        gateway_order_id=gateway_order_id,
    )
    db_session.add(order)
    await db_session.flush()

    webhook_payload = {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_failed_attempt_01",
                    "order_id": gateway_order_id,
                    "amount": 25000,
                    "status": "failed",
                    "error_description": "Payment was declined by bank",
                }
            }
        },
    }

    await process_webhook(db_session, webhook_payload, event_id="evt_fail_1")
    await db_session.flush()

    refreshed_order = await db_session.get(PaymentOrder, order.id)
    assert refreshed_order is not None
    # Order must still be created / retryable, NOT terminal "failed"
    assert refreshed_order.status == "created"


@pytest.mark.asyncio
async def test_webhook_order_paid_marks_order_paid(db_session: AsyncSession):
    """The order.paid webhook marks the order as paid properly."""
    edition_id = uuid.uuid4()
    user_id = uuid.uuid4()
    gateway_order_id = f"order_paid_{uuid.uuid4().hex[:8]}"

    order = PaymentOrder(
        edition_id=edition_id,
        user_id=user_id,
        purpose="registration",
        amount_paise=30000,
        status="created",
        gateway_order_id=gateway_order_id,
    )
    db_session.add(order)
    await db_session.flush()

    webhook_payload = {
        "event": "order.paid",
        "payload": {
            "order": {
                "entity": {
                    "id": gateway_order_id,
                    "amount": 30000,
                    "status": "paid",
                }
            },
            "payment": {
                "entity": {
                    "id": "pay_captured_xyz",
                    "order_id": gateway_order_id,
                    "amount": 30000,
                    "status": "captured",
                }
            },
        },
    }

    await process_webhook(db_session, webhook_payload, event_id="evt_paid_1")
    await db_session.flush()

    refreshed_order = await db_session.get(PaymentOrder, order.id)
    assert refreshed_order is not None
    assert refreshed_order.status == "paid"


@pytest.mark.asyncio
async def test_telegram_payment_notification_deduplication():
    """Telegram payment notifications must deduplicate duplicate events for the same order."""
    unique_order_id = f"order_dedup_{uuid.uuid4().hex[:8]}"

    # Mock settings so token and chat_id are present
    with patch("app.services.telegram.get_settings") as mock_settings:
        settings_obj = MagicMockSettings()
        mock_settings.return_value = settings_obj

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_resp = AsyncMock()
            mock_resp.is_success = True
            mock_resp.status_code = 200
            mock_post.return_value = mock_resp

            res1 = await send_telegram_payment_notification(
                event_type="initiated",
                order_id=unique_order_id,
                amount_paise=50000,
                purpose="pass",
                gateway_order_id="order_rzp_123",
                attendee_name="Test Attendee",
            )
            assert res1.get("sent") is True

            # Immediate second call with identical order and event_type -> suppressed
            res2 = await send_telegram_payment_notification(
                event_type="initiated",
                order_id=unique_order_id,
                amount_paise=50000,
                purpose="pass",
                gateway_order_id="order_rzp_123",
                attendee_name="Test Attendee",
            )
            assert res2.get("sent") is False
            assert res2.get("reason") == "duplicate_suppressed"


@pytest.mark.asyncio
async def test_dispatch_payment_telegram_alert_logs_and_never_raises():
    """Telegram alert dispatcher handles and logs exceptions without raising, ensuring serverless safety."""
    from app.services.telegram import dispatch_payment_telegram_alert

    # Calling dispatch when background task or network throws should log and not crash
    with patch("app.services.telegram.send_telegram_payment_notification", side_effect=RuntimeError("Vercel network timeout")):
        with patch("app.services.telegram.logger.error") as mock_logger_err:
            dispatch_payment_telegram_alert(
                event_type="success",
                order_id=f"order_{uuid.uuid4().hex[:6]}",
                amount_paise=10000,
                purpose="test",
            )
            import asyncio
            # Yield event loop so background task executes
            await asyncio.sleep(0.05)
            assert mock_logger_err.called


class MagicMockSettings:
    effective_telegram_bot_token = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"
    effective_telegram_chat_id = "-100123456789"
    # Actual delivery is suppressed under the test profile; this test opts back
    # in to prove deduplication, with HTTP mocked below.
    is_test = False

