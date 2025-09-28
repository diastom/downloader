import asyncio
import logging
from typing import Iterable

from aiogram import Bot, F, Router, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from utils import database
from utils.db_session import AsyncSessionLocal
from utils.payments import (
    create_nowpayments_invoice,
    get_live_price,
    get_nowpayments_invoice_status,
)

logger = logging.getLogger(__name__)

router = Router()

PAYMENT_CURRENCY = "trx"
STATUS_SUCCESS = {"finished", "confirmed", "completed", "paid"}
STATUS_FAILED = {"failed", "expired", "refunded", "partially_refunded"}
CHECK_INTERVAL_SECONDS = 20
MAX_STATUS_CHECKS = 45  # ~15 minutes


def _format_plan_description(plan, *, crypto_amount: float) -> str:
    download_limit = "نامحدود" if plan.download_limit == -1 else f"{plan.download_limit}"
    encode_limit = "نامحدود" if plan.encode_limit == -1 else f"{plan.encode_limit}"
    return (
        f"{plan.title}\n"
        f"مدت: {plan.duration_days} روز\n"
        f"دانلود روزانه: {download_limit}\n"
        f"انکد روزانه: {encode_limit}\n"
        f"قیمت: {plan.price_toman:,} تومان (~{crypto_amount} {PAYMENT_CURRENCY.upper()})"
    )


def _build_plans_keyboard(plans: Iterable, *, price_per_coin: float) -> InlineKeyboardMarkup:
    buttons = []
    for plan in plans:
        crypto_amount = round(plan.price_toman / price_per_coin, 6)
        buttons.append([
            InlineKeyboardButton(
                text=f"{plan.title} ({crypto_amount} {PAYMENT_CURRENCY.upper()})",
                callback_data=f"buy_plan_{plan.id}",
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@router.message(Command("buy"))
async def show_buy_menu(message: types.Message, session: AsyncSession):
    plans = await database.list_subscription_plans(session)
    if not plans:
        await message.answer("در حال حاضر اشتراکی برای خرید فعال نیست. لطفاً بعداً تلاش کنید.")
        return

    try:
        price_per_coin = await get_live_price(PAYMENT_CURRENCY)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load live price: %s", exc)
        await message.answer("دریافت قیمت لحظه‌ای با خطا مواجه شد. لطفاً کمی بعد دوباره تلاش کنید.")
        return

    descriptions = [
        _format_plan_description(plan, crypto_amount=round(plan.price_toman / price_per_coin, 6))
        for plan in plans
    ]

    keyboard = _build_plans_keyboard(plans, price_per_coin=price_per_coin)
    text = "پلن مورد نظر خود را انتخاب کنید:\n\n" + "\n\n".join(descriptions)
    await message.answer(text, reply_markup=keyboard)


async def _poll_invoice_status(*, bot: Bot, invoice_id: str, user_id: int, plan_id: int, api_key: str) -> None:
    attempts = 0
    while attempts < MAX_STATUS_CHECKS:
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
        attempts += 1

        try:
            invoice_info = await get_nowpayments_invoice_status(api_key=api_key, invoice_id=invoice_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to fetch invoice status for %s: %s", invoice_id, exc)
            continue

        status = (
            invoice_info.get("status")
            or invoice_info.get("invoice_status")
            or invoice_info.get("payment_status")
        )
        if not status:
            continue

        async with AsyncSessionLocal() as new_session:
            await database.update_payment_transaction_status(
                new_session,
                payment_id=invoice_id,
                status=status,
            )

            if status.lower() in STATUS_SUCCESS:
                plan = await database.get_subscription_plan(new_session, plan_id)
                if not plan:
                    await bot.send_message(user_id, "پلن خریداری‌شده دیگر وجود ندارد. لطفاً با پشتیبانی تماس بگیرید.")
                    return

                user = await database.apply_subscription_plan(new_session, user_id=user_id, plan=plan)
                await bot.send_message(
                    user_id,
                    (
                        "پرداخت شما با موفقیت تأیید شد.\n"
                        f"اشتراک شما تا تاریخ {user.sub_expiry_date:%Y-%m-%d} فعال شد."
                    ),
                )
                return

            if status.lower() in STATUS_FAILED:
                await bot.send_message(
                    user_id,
                    "پرداخت ناموفق بود یا منقضی شده است. در صورت کسر وجه، با پشتیبانی تماس بگیرید.",
                )
                return

    # Timed out
    async with AsyncSessionLocal() as new_session:
        await database.update_payment_transaction_status(
            new_session,
            payment_id=invoice_id,
            status="timeout",
        )
    await bot.send_message(
        user_id,
        "وضعیت پرداخت طی زمان مقرر مشخص نشد. لطفاً در صورت انجام پرداخت با پشتیبانی تماس بگیرید.",
    )


@router.callback_query(F.data.startswith("buy_plan_"))
async def handle_plan_purchase(query: CallbackQuery, session: AsyncSession):
    await query.answer()

    try:
        plan_id = int(query.data.replace("buy_plan_", ""))
    except ValueError:
        await query.message.answer("پلن انتخابی نامعتبر است.")
        return

    plan = await database.get_subscription_plan(session, plan_id)
    if not plan or not plan.is_active:
        await query.message.answer("این پلن در حال حاضر فعال نیست.")
        return

    api_key = await database.get_payment_setting(session, "nowpayments_api_key")
    if not api_key:
        await query.message.answer("درگاه پرداخت موقتاً در دسترس نیست. لطفاً با پشتیبانی تماس بگیرید.")
        return

    try:
        price_per_coin = await get_live_price(PAYMENT_CURRENCY)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to load live price: %s", exc)
        await query.message.answer("دریافت قیمت لحظه‌ای با خطا مواجه شد. لطفاً کمی بعد دوباره تلاش کنید.")
        return

    crypto_amount = round(plan.price_toman / price_per_coin, 6)
    loop = asyncio.get_running_loop()
    order_id = f"{query.from_user.id}-{plan.id}-{int(loop.time() * 1000)}"

    try:
        payment_response = await create_nowpayments_invoice(
            api_key=api_key,
            amount=crypto_amount,
            currency=PAYMENT_CURRENCY,
            order_id=order_id,
            description=f"Plan {plan.title}",
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to create invoice: %s", exc)
        await query.message.answer("ایجاد پرداخت با خطا مواجه شد. لطفاً کمی بعد دوباره تلاش کنید.")
        return

    invoice_id = str(
        payment_response.get("id")
        or payment_response.get("invoice_id")
        or payment_response.get("payment_id")
    )
    invoice_url = payment_response.get("invoice_url") or payment_response.get("pay_url")
    pay_amount = payment_response.get("pay_amount", crypto_amount)
    pay_currency = payment_response.get("pay_currency", PAYMENT_CURRENCY)

    if not invoice_id or not invoice_url:
        logger.error("Unexpected invoice response: %s", payment_response)
        await query.message.answer("خطای غیرمنتظره‌ای رخ داد. لطفاً با پشتیبانی تماس بگیرید.")
        return

    await database.create_payment_transaction(
        session,
        user_id=query.from_user.id,
        plan_id=plan.id,
        payment_id=invoice_id,
        invoice_url=invoice_url,
        pay_amount=str(pay_amount),
        pay_currency=pay_currency,
    )

    text = (
        "برای تکمیل خرید روی لینک زیر کلیک کنید و مبلغ را پرداخت نمایید:\n"
        f"لینک پرداخت: {invoice_url}\n"
        f"مبلغ قابل پرداخت: {pay_amount} {pay_currency.upper()}"
    )
    await query.message.answer(text)

    asyncio.create_task(
        _poll_invoice_status(
            bot=query.message.bot,
            invoice_id=invoice_id,
            user_id=query.from_user.id,
            plan_id=plan.id,
            api_key=api_key,
        )
    )
