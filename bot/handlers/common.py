import html

from aiogram import Router, types, F
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardRemove,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from sqlalchemy.ext.asyncio import AsyncSession
from utils import database, payments
from utils.helpers import ALL_SUPPORTED_SITES
from decimal import Decimal
from datetime import datetime

router = Router()

SUPPORTED_SITES = [site for category in ALL_SUPPORTED_SITES.values() for site in category]

# --- States for the main user flow ---
class UserFlow(StatesGroup):
    main_menu = State()
    downloading = State()
    encoding = State()


class PurchaseFlow(StatesGroup):
    select_plan = State()
    select_currency = State()
    await_link = State()

def get_main_menu_keyboard():
    """Legacy helper retained for compatibility; no inline keyboard is returned."""
    return None

def get_main_reply_keyboard():
    """Returns the main persistent reply keyboard."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="راهنما 📚")]],
        resize_keyboard=True
    )

def get_task_done_keyboard():
    """Legacy helper kept for compatibility; no keyboard is attached now."""
    return None


def _format_limit(limit: int) -> str:
    return "نامحدود" if limit is None or limit < 0 else str(limit)


def _format_decimal(amount: Decimal) -> str:
    text = format(amount, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text

def _get_plan_sites(plan) -> list[str]:
    allowed = set(getattr(plan, "allowed_sites", []) or [])
    return [site for site in SUPPORTED_SITES if site in allowed]


def _get_plan_sites_lines(plan, banner_available: bool = False) -> list[str]:
    if banner_available:
        return ["در بنر ذکر شده است"]
    sites = _get_plan_sites(plan)
    return sites if sites else ["بدون دسترسی به سایت‌های ویژه"]

def _get_plan_feature_labels(plan) -> list[str]:
    labels = []
    if getattr(plan, "allow_thumbnail", False):
        labels.append("تامبنیل")
    if getattr(plan, "allow_watermark", False):
        labels.append("واترمارک")
    return labels

def _get_plan_feature_text(plan) -> str:
    labels = _get_plan_feature_labels(plan)
    return " + ".join(labels) if labels else "ندارد"


def _get_plan_description(plan) -> str | None:
    description = getattr(plan, "description", None)
    if not description:
        return None
    description = description.strip()
    return description or None

def _user_has_active_subscription(user) -> bool:
    if not user.sub_is_active:
        return False
    if user.sub_expiry_date is None:
        return True
    return user.sub_expiry_date >= datetime.utcnow()


async def _edit_purchase_message(
    message: types.Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: ParseMode | None = None,
):
    extra = {"reply_markup": reply_markup}
    if parse_mode:
        extra["parse_mode"] = parse_mode
    if message.content_type == "photo" and message.photo:
        await message.edit_caption(caption=text, **extra)
    else:
        await message.edit_text(text, **extra)


async def _get_purchase_banner_info(
    state: FSMContext,
    session: AsyncSession,
) -> tuple[bool, str | None]:
    data = await state.get_data()
    context = data.get("purchase_context") or {}
    file_id = context.get("banner_file_id")
    if file_id is None:
        file_id = await database.get_subscription_banner_file_id(session)
        context["banner_file_id"] = file_id or ""
        await state.update_data(purchase_context=context)
    return bool(file_id), (file_id or None)


def _format_remaining_days(user) -> str:
    if user.sub_expiry_date is None:
        return "نامحدود"
    remaining = user.sub_expiry_date - datetime.utcnow()
    days_left = max(0, remaining.days)
    return f"{days_left:02d}"


async def _build_active_subscription_response(bot, user) -> tuple[str, InlineKeyboardMarkup]:
    bot_username = "@Bot"
    try:
        bot_user = await bot.get_me()
        if bot_user.username:
            bot_username = f"@{bot_user.username}"
    except Exception:
        pass

    message_text = (
        "شما یک اشتراک فعال دارید!\n\n"
        f"روزهای باقی ماند: {_format_remaining_days(user)}\n"
        f"سقف دانلود روزانه: {_format_limit(user.sub_download_limit)}\n"
        f"سقف ویرایش ویدئو روزانه: {_format_limit(user.sub_encode_limit)}\n\n"
        f"{bot_username}"
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="بروزرسانی وضعیت", callback_data="buy_refresh")]]
    )

    return message_text, keyboard

@router.message(CommandStart())
async def handle_start(message: types.Message, state: FSMContext, session: AsyncSession):
    """
    Handler for the /start command. Greets the user and shows the main menu.
    """
    user = message.from_user
    await database.get_or_create_user(session, user_id=user.id, username=user.username)
    await state.set_state(UserFlow.main_menu)

    start_message = (
        "خوش آمدید!\n\n"
        "کافیست لینک یکی از سایت‌های پشتیبانی‌شده را بفرستید تا دانلود شروع شود، یا ویدیوی خود را ارسال کنید تا وارد پنل ویرایش ویدئو شوید."
    )
    await message.answer(start_message, reply_markup=get_main_reply_keyboard())

@router.callback_query(F.data == "start_download")
async def start_download_flow(query: types.CallbackQuery, state: FSMContext):
    """Reminds the user how to begin a download."""
    await state.set_state(UserFlow.downloading)
    await query.message.edit_text(
        "برای شروع دانلود کافیست لینک خود را بفرستید."
    )
    await query.answer()

@router.callback_query(F.data == "start_encode")
async def start_encode_flow(query: types.CallbackQuery, state: FSMContext):
    """Reminds the user how to begin an encode."""
    await state.set_state(UserFlow.encoding)
    await query.message.edit_text(
        "برای ورود به پنل ویرایش ویدئو، ویدیوی مورد نظر خود را ارسال کنید."
    )
    await query.answer()


@router.message(F.text == "راهنما 📚")
@router.message(Command("help"))
async def handle_help(message: types.Message, session: AsyncSession):
    """
    Handler for the /help command. Displays the help text.
    """
    help_text = await database.get_text(session, key="help_text", default="متن راهنما هنوز تنظیم نشده است.")
    await message.answer(help_text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


@router.message(Command("buy"))
async def handle_buy_command(message: types.Message, state: FSMContext, session: AsyncSession):
    user = await database.get_or_create_user(
        session, user_id=message.from_user.id, username=message.from_user.username
    )
    if _user_has_active_subscription(user):
        text, keyboard = await _build_active_subscription_response(message.bot, user)
        await message.answer(text, reply_markup=keyboard)
        return

    plans = await database.get_subscription_plans(session)
    if not plans:
        await message.answer("در حال حاضر هیچ اشتراکی برای فروش تعریف نشده است.")
        return

    wallet_map = await database.get_wallet_settings_map(session)
    available_currencies = [payments.CURRENCIES[code] for code in payments.CURRENCIES if code in wallet_map]
    if not available_currencies:
        await message.answer("متأسفانه هیچ ولتی برای دریافت پرداخت‌ها تنظیم نشده است. لطفاً بعداً تلاش کنید.")
        return

    banner_file_id = await database.get_subscription_banner_file_id(session)

    info_lines = [
        "<b>بعد از پرداخت اشتراک شما بلافاصله فعال می‌شود.</b>",
        "💡 می‌تونید از طریق موجودی مجموعه ( @Uploaderi ) هم اشتراک تهیه کنید.",
        " • فقط کافیه به @xdevil پیام بدین",
        "",
        "پلن مورد نظر خود را انتخاب کنید 👇",
    ]

    buttons = []
    for plan in plans:
        buttons.append(
            [
                InlineKeyboardButton(
                    text=f"انتخاب {plan.name}", callback_data=f"buy_plan_{plan.id}"
                )
            ]
        )

    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await state.set_state(PurchaseFlow.select_plan)
    await state.update_data(purchase_context={"banner_file_id": banner_file_id or ""})
    response_text = "\n".join(info_lines).strip()
    if banner_file_id:
        await message.answer_photo(banner_file_id, caption=response_text, reply_markup=keyboard)
    else:
        await message.answer(response_text, reply_markup=keyboard)


@router.callback_query(F.data == "buy_cancel")
async def handle_buy_cancel(query: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(UserFlow.main_menu)
    try:
        await _edit_purchase_message(query.message, "فرآیند خرید لغو شد.")
    except Exception:
        await query.message.answer("فرآیند خرید لغو شد.")
    await query.answer()


@router.callback_query(F.data.startswith("buy_plan_"))
async def handle_buy_plan_selection(query: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    await query.answer()
    try:
        plan_id = int(query.data.replace("buy_plan_", ""))
    except ValueError:
        await query.message.answer("شناسه اشتراک نامعتبر است.")
        return

    plan = await database.get_subscription_plan_by_id(session, plan_id)
    if not plan:
        await query.message.answer("این اشتراک در دسترس نیست.")
        return

    wallet_map = await database.get_wallet_settings_map(session)
    available = {code: payments.CURRENCIES[code] for code in payments.CURRENCIES if code in wallet_map}
    if not available:
        await query.message.answer("هیچ ولت فعالی برای دریافت پرداخت وجود ندارد.")
        await state.clear()
        await state.set_state(UserFlow.main_menu)
        return

    currency_buttons = [
        [InlineKeyboardButton(text=meta.display_name, callback_data=f"buy_currency_{code}")]
        for code, meta in available.items()
    ]
    currency_buttons.append([InlineKeyboardButton(text="لغو", callback_data="buy_cancel")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=currency_buttons)

    banner_available, _ = await _get_purchase_banner_info(state, session)
    site_lines = "\n".join(_get_plan_sites_lines(plan, banner_available))
    feature_text = _get_plan_feature_text(plan)
    description = _get_plan_description(plan) or "ثبت نشده است"
    summary = (
        f"اشتراک انتخابی: {plan.name}\n"
        f"مدت اشتراک: {plan.duration_days} روز\n"
        f"سقف دانلود روزانه: {_format_limit(plan.download_limit_per_day)}\n"
        f"سقف ویرایش ویدئو روزانه: {_format_limit(plan.encode_limit_per_day)}\n"
        f"سایت‌های فعال:\n{site_lines}\n"
        f"امکانات: {feature_text}\n"
        f"توضیحات: {description}\n"
        f"قیمت: {plan.price_toman:,} تومان\n\n"
        "ارز موردنظر برای پرداخت را انتخاب کنید:"
    )

    await state.update_data(selected_plan_id=plan.id)
    await state.set_state(PurchaseFlow.select_currency)
    await _edit_purchase_message(query.message, summary, reply_markup=keyboard)


@router.callback_query(F.data.startswith("buy_currency_"))
async def handle_buy_currency_selection(query: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    await query.answer()
    currency_code = query.data.replace("buy_currency_", "")
    meta = payments.CURRENCIES.get(currency_code)
    if not meta:
        await query.message.answer("این ارز پشتیبانی نمی‌شود.")
        return

    data = await state.get_data()
    plan_id = data.get("selected_plan_id")
    if not plan_id:
        await query.message.answer("لطفاً ابتدا یک اشتراک را انتخاب کنید.")
        return

    plan = await database.get_subscription_plan_by_id(session, plan_id)
    if not plan:
        await query.message.answer("این اشتراک دیگر در دسترس نیست.")
        await state.clear()
        await state.set_state(UserFlow.main_menu)
        return

    wallet = await database.get_wallet_setting(session, currency_code)
    if not wallet:
        await query.message.answer("برای این ارز ولتی ثبت نشده است.")
        return

    try:
        price_toman = await payments.get_currency_price_toman(currency_code)
        expected_amount = payments.calculate_crypto_amount(price_toman, plan.price_toman, meta.decimals)
    except Exception as exc:
        await query.message.answer(f"خطا در محاسبه مبلغ پرداخت: {exc}")
        return

    transaction = await database.create_purchase_transaction(
        session,
        user_id=query.from_user.id,
        plan_id=plan.id,
        currency_code=currency_code,
        expected_amount=expected_amount,
        expected_toman=plan.price_toman,
        wallet_address=wallet.address,
    )

    currency_label = "ترون" if currency_code == "TRX" else meta.display_name
    amount_suffix = "TRX" if currency_code == "TRX" else meta.code
    instructions = "\n".join(
        [
            f"قیمت {currency_label}: {price_toman:,.0f} تومان",
            f"مبلغ قابل پرداخت: {_format_decimal(expected_amount)} {amount_suffix}",
            f"آدرس ولت: <code>{html.escape(wallet.address)}</code>",
        ]
    )

    action_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="ارسال لینک ID", callback_data="buy_send_link")],
            [InlineKeyboardButton(text="لغو", callback_data="buy_cancel")],
        ]
    )

    await state.set_state(PurchaseFlow.await_link)
    await state.update_data(
        selected_plan_id=plan.id,
        currency_code=currency_code,
        expected_amount=str(expected_amount),
        transaction_id=transaction.id,
    )
    await _edit_purchase_message(
        query.message,
        instructions,
        reply_markup=action_keyboard,
        parse_mode=ParseMode.HTML,
    )


@router.callback_query(F.data == "buy_send_link")
async def prompt_for_transaction_link(query: types.CallbackQuery):
    await query.answer()
    current_text = (query.message.caption or query.message.text or "").rstrip()
    prompt = "لطفاً لینک تراکنش خود را ارسال کنید (مطابق با سایت اکسپلورر معرفی‌شده)."
    if prompt not in current_text:
        if current_text:
            current_text = f"{current_text}\n\n{prompt}"
        else:
            current_text = prompt
    action_keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="لغو", callback_data="buy_cancel")]]
    )
    await _edit_purchase_message(
        query.message,
        current_text,
        reply_markup=action_keyboard,
        parse_mode=ParseMode.HTML,
    )


@router.message(PurchaseFlow.await_link)
async def receive_transaction_link(message: types.Message, state: FSMContext, session: AsyncSession):
    link = (message.text or "").strip()
    if not link:
        await message.answer("لطفاً لینک تراکنش را ارسال کنید.")
        return

    data = await state.get_data()
    plan_id = data.get("selected_plan_id")
    currency_code = data.get("currency_code")
    transaction_id = data.get("transaction_id")
    expected_amount_str = data.get("expected_amount")

    if not all([plan_id, currency_code, transaction_id, expected_amount_str]):
        await message.answer("اطلاعات خرید کامل نیست. لطفاً دوباره /buy را امتحان کنید.")
        await state.clear()
        await state.set_state(UserFlow.main_menu)
        return

    wallet = await database.get_wallet_setting(session, currency_code)
    if not wallet:
        await message.answer("آدرس ولت یافت نشد. لطفاً با پشتیبانی تماس بگیرید.")
        await state.clear()
        await state.set_state(UserFlow.main_menu)
        return

    verification = await payments.verify_transaction(currency_code, wallet.address, link)
    if not verification.success or verification.amount is None:
        await message.answer(verification.message)
        return

    expected_amount = Decimal(expected_amount_str)
    if verification.amount < expected_amount:
        await message.answer(
            "مبلغ تراکنش کمتر از مقدار مورد نیاز است. لطفاً مبلغ صحیح را واریز کنید یا با پشتیبانی در تماس باشید."
        )
        return

    plan = await database.get_subscription_plan_by_id(session, plan_id)
    if not plan:
        await message.answer("اشتراک انتخابی دیگر در دسترس نیست. لطفاً با پشتیبانی تماس بگیرید.")
        await state.clear()
        await state.set_state(UserFlow.main_menu)
        return

    await database.update_purchase_transaction_status(
        session,
        transaction_id,
        status="completed",
        actual_amount=verification.amount,
        transaction_hash=verification.tx_hash,
        payment_link=link,
    )

    await database.apply_subscription_plan_to_user(session, user_id=message.from_user.id, plan=plan)

    await message.answer(
        (
            "✅ اشتراک شما با موفقیت فعال شد.\n"
            "می‌توانید از تمامی سایت‌های پشتیبانی‌شده استفاده کنید."
        )
    )
    await state.clear()
    await state.set_state(UserFlow.main_menu)


@router.callback_query(F.data == "buy_refresh")
async def refresh_subscription_status(query: types.CallbackQuery, session: AsyncSession):
    await query.answer("وضعیت بروزرسانی شد.")
    user = await database.get_or_create_user(
        session, user_id=query.from_user.id, username=query.from_user.username
    )

    if not _user_has_active_subscription(user):
        await query.message.edit_text(
            "اشتراک شما منقضی شده یا فعال نیست. برای خرید جدید /buy را ارسال کنید."
        )
        return

    text, keyboard = await _build_active_subscription_response(query.message.bot, user)
    await query.message.edit_text(text, reply_markup=keyboard)

@router.message(Command("cancel"))
async def handle_cancel(message: types.Message, state: FSMContext):
    """
    Universal command to cancel any active FSM state and return to the main menu.
    """
    current_state = await state.get_state()
    if current_state is None or current_state == UserFlow.main_menu:
        await message.answer("در حال حاضر در هیچ عملیاتی نیستید. برای شروع /start را بزنید.", reply_markup=ReplyKeyboardRemove())
        return

    await state.set_state(UserFlow.main_menu)
    await message.answer(
        "عملیات لغو شد. می‌توانید لینک یا ویدیوی جدیدی ارسال کنید.",
        reply_markup=get_main_menu_keyboard(),
    )

# Callback handler to return to the main menu
@router.callback_query(F.data == "return_to_main_menu")
async def return_to_main_menu(query: types.CallbackQuery, state: FSMContext):
    await state.set_state(UserFlow.main_menu)
    await query.message.edit_text(
        "به صفحه اصلی بازگشتید. برای شروع کافیست لینک یا ویدیوی خود را بفرستید.",
        reply_markup=get_main_menu_keyboard()
    )
    await query.answer()
