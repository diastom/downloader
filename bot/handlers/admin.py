import asyncio
from datetime import datetime, timedelta
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
    ReplyKeyboardRemove,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

# --- START OF CORRECTION ---
# Import the necessary start handler and keyboard from the common handlers
from bot.handlers.common import handle_start
# --- END OF CORRECTION ---

from config import settings
from utils import database
from utils.helpers import ALL_SUPPORTED_SITES

router = Router()
# Ensure these handlers only work for admins
router.message.filter(F.from_user.id.in_(settings.admin_ids))
router.callback_query.filter(F.from_user.id.in_(settings.admin_ids))

# --- FSM States ---
class AdminFSM(StatesGroup):
    panel = State()
    await_broadcast = State()
    await_sub_user_id = State()
    manage_user_sub = State()
    await_help_text = State()
    sales_menu = State()
    await_plan_title = State()
    await_plan_duration = State()
    await_plan_download_limit = State()
    await_plan_encode_limit = State()
    await_plan_price = State()
    await_api_key = State()

# --- Keyboards ---
def get_admin_panel_keyboard() -> ReplyKeyboardMarkup:
    """Creates the main admin reply keyboard."""
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📊 آمار"), KeyboardButton(text="📢 همگانی")],
        [KeyboardButton(text="⚙️ مدیریت اشتراک"), KeyboardButton(text="📝 متن ها")],
        [KeyboardButton(text="🛒 تنظیمات فروش")],
        [KeyboardButton(text="❌ خروج از پنل")]
    ], resize_keyboard=True)


def _format_limit(value: int) -> str:
    return "نامحدود" if value == -1 else f"{value}"


async def build_sales_overview(session: AsyncSession) -> tuple[str, InlineKeyboardMarkup]:
    _ = await database.list_subscription_plans(session, include_inactive=True)
    text = "لطفاً یکی از گزینه‌های فروش را انتخاب کنید."
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="اشتراک ها", callback_data="sales_manage_plans")],
            [InlineKeyboardButton(text="مدیریت API", callback_data="sales_manage_api")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="sales_back")],
        ]
    )
    return text, keyboard


async def build_plan_management_keyboard(session: AsyncSession) -> tuple[str, InlineKeyboardMarkup]:
    plans = await database.list_subscription_plans(session, include_inactive=True)
    overview_lines = []
    for index, plan in enumerate(plans, start=1):
        overview_lines.append(
            "\n".join(
                [
                    f"{index}. {plan.title}",
                    f"مدت: {plan.duration_days} روز",
                    f"قیمت: {plan.price_toman:,} تومان",
                ]
            )
        )
    overview = "\n\n".join(overview_lines) if overview_lines else "هیچ اشتراکی تعریف نشده است."

    keyboard_buttons = [
        [InlineKeyboardButton(text="➕ افزودن نوع جدید اشتراک", callback_data="sales_add_plan")],
        [InlineKeyboardButton(text="➖ حذف نوع اشتراک", callback_data="sales_remove_plan")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="sales_back_overview")],
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
    return overview, keyboard


def build_plan_removal_keyboard(plans: list, *, empty_text: str) -> tuple[str, InlineKeyboardMarkup]:
    if not plans:
        text = empty_text
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text="🔙 بازگشت", callback_data="sales_manage_plans")]]
        )
        return text, keyboard

    rows = []
    for plan in plans:
        rows.append([InlineKeyboardButton(text=plan.title, callback_data=f"sales_delete_{plan.id}")])
    rows.append([InlineKeyboardButton(text="لغو", callback_data="sales_manage_plans")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
    return "کدام اشتراک حذف شود؟", keyboard


def mask_api_key(api_key: str | None) -> str:
    if not api_key:
        return "ثبت نشده"
    if len(api_key) <= 6:
        return "*" * len(api_key)
    return f"{api_key[:4]}{'*' * (len(api_key) - 8)}{api_key[-4:]}"

async def get_subscription_panel(session: AsyncSession, target_user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Creates the inline keyboard for managing a user's subscription."""
    user = await database.get_or_create_user(session, target_user_id)

    expiry_date = user.sub_expiry_date
    remain_days = "Unlimited"
    if expiry_date:
        delta = expiry_date - datetime.now()
        remain_days = max(0, delta.days)

    download_limit = user.sub_download_limit
    download_limit_text = "Unlimited" if download_limit == -1 else str(download_limit)
    encode_limit = user.sub_encode_limit
    encode_limit_text = "Unlimited" if encode_limit == -1 else str(encode_limit)

    info_text = (
        f"👤 @{user.username or 'N/A'}\n"
        f"UID: `{user.id}`\n"
        f"Days Left: **{remain_days}**\n"
        f"Download Limit: **{download_limit_text}**/day\n"
        f"Encode Limit: **{encode_limit_text}**/day"
    )

    # --- Feature Toggles ---
    thumb_status = "✅" if user.allow_thumbnail else "❌"
    water_status = "✅" if user.allow_watermark else "❌"

    keyboard = []
    status_text = "ACTIVE ✅" if user.sub_is_active else "DEACTIVATED ❌"
    keyboard.append([InlineKeyboardButton(text=status_text, callback_data="sub_toggle_active")])

    # Feature access buttons
    keyboard.append([
        InlineKeyboardButton(text=f"Thumbnail {thumb_status}", callback_data="sub_toggle_thumbnail"),
        InlineKeyboardButton(text=f"Watermark {water_status}", callback_data="sub_toggle_watermark")
    ])

    all_sites = [site for category in ALL_SUPPORTED_SITES.values() for site in category]
    row = []
    for site in all_sites:
        status = "☑️" if user.sub_allowed_sites.get(site, False) else "✖️"
        row.append(InlineKeyboardButton(text=f"{site} {status}", callback_data=f"sub_toggle_site_{site}"))
        if len(row) >= 2:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    keyboard.extend([
        [InlineKeyboardButton(text="Activate All Sites", callback_data="sub_activate_all"),
         InlineKeyboardButton(text="Deactivate All Sites", callback_data="sub_deactivate_all")],
        [InlineKeyboardButton(text="-10d", callback_data="sub_add_days_-10"),
         InlineKeyboardButton(text="+10d", callback_data="sub_add_days_10"),
         InlineKeyboardButton(text="+30d", callback_data="sub_add_days_30")],
        [InlineKeyboardButton(text="DL Limit: -10", callback_data="sub_add_download_limit_-10"),
         InlineKeyboardButton(text="DL No Limit", callback_data="sub_add_download_limit_0"),
         InlineKeyboardButton(text="DL Limit: +10", callback_data="sub_add_download_limit_10")],
        [InlineKeyboardButton(text="ENC Limit: -10", callback_data="sub_add_encode_limit_-10"),
         InlineKeyboardButton(text="ENC No Limit", callback_data="sub_add_encode_limit_0"),
         InlineKeyboardButton(text="ENC Limit: +10", callback_data="sub_add_encode_limit_10")],
        [InlineKeyboardButton(text="🔙 Back to Admin Panel", callback_data="sub_back_to_panel")]
    ])

    return info_text, InlineKeyboardMarkup(inline_keyboard=keyboard)

# --- Handlers ---
@router.message(Command("admin"))
async def admin_panel_entry(message: types.Message, state: FSMContext):
    await message.answer("Welcome to the Admin Panel.", reply_markup=get_admin_panel_keyboard())
    await state.set_state(AdminFSM.panel)

@router.message(AdminFSM.panel, F.text == "📊 آمار")
async def show_stats(message: types.Message, session: AsyncSession):
    stats = await database.get_bot_statistics(session)

    def fmt_count(value: int) -> str:
        return f"{value:02d}"

    def fmt_size(total_bytes: int) -> str:
        gigabytes = total_bytes / (1024 ** 3)
        return f"{gigabytes:.2f}GB"

    top_sites = stats["top_sites"] or []
    top_sites_text = "\n".join(f"• {site}" for site in top_sites) if top_sites else "• No data yet"

    stats_text = (
        "📊 Bot Stats\n\n"
        "👥 Users\n"
        f"• Total Users: {fmt_count(stats['total_users'])}\n"
        f"• Users (Today): {fmt_count(stats['users_today'])}\n\n"
        "💳 Subscriptions\n"
        f"• Active Subscriptions: {fmt_count(stats['active_subscriptions'])}\n"
        f"• Expired Subscriptions: {fmt_count(stats['expired_subscriptions'])}\n\n"
        "🌐 Most Popular Sites\n"
        f"{top_sites_text}\n\n"
        "📥 Downloads\n"
        f"• Total Downloads: {fmt_count(stats['total_downloads'])}\n"
        f"• Downloads (Today): {fmt_count(stats['downloads_today'])}\n\n"
        "🏷 Sizes\n"
        f"• Total Downloads Size: {fmt_size(stats['total_bytes'])}\n"
        f"• Downloads Size (Today): {fmt_size(stats['today_bytes'])}\n\n"
        "@OviaRobot"
    )

    await message.answer(stats_text)


@router.message(AdminFSM.panel, F.text == "🛒 تنظیمات فروش")
async def show_sales_settings(message: types.Message, state: FSMContext, session: AsyncSession):
    text, keyboard = await build_sales_overview(session)
    await message.answer(text, reply_markup=keyboard)
    await state.set_state(AdminFSM.sales_menu)


@router.callback_query(AdminFSM.sales_menu, F.data == "sales_back")
async def sales_back_to_panel(query: CallbackQuery, state: FSMContext):
    await query.message.delete()
    await state.set_state(AdminFSM.panel)
    await query.answer("به پنل اصلی بازگشتید.")


@router.callback_query(AdminFSM.sales_menu, F.data == "sales_back_overview")
async def sales_back_overview(query: CallbackQuery, state: FSMContext, session: AsyncSession):
    text, keyboard = await build_sales_overview(session)
    await query.message.edit_text(text, reply_markup=keyboard)
    await query.answer()


@router.callback_query(AdminFSM.sales_menu, F.data == "sales_manage_plans")
async def sales_manage_plans(query: CallbackQuery, session: AsyncSession):
    text, keyboard = await build_plan_management_keyboard(session)
    await query.message.edit_text(text, reply_markup=keyboard)
    await query.answer()


@router.callback_query(AdminFSM.sales_menu, F.data == "sales_add_plan")
async def sales_add_plan(query: CallbackQuery, state: FSMContext):
    await state.update_data(new_plan={})
    await state.set_state(AdminFSM.await_plan_title)
    await query.message.edit_text(
        "عنوان اشتراک جدید را وارد کنید:\nبرای لغو /cancel را بزنید.",
        reply_markup=None,
    )
    await query.answer()


def _parse_numeric_value(value: str, *, allow_unlimited: bool = False) -> int | None:
    normalized = value.strip().replace(",", "")
    if allow_unlimited and normalized.lower() in {"-1", "نامحدود", "بی نهایت", "unlimited"}:
        return -1
    try:
        return int(normalized)
    except ValueError:
        return None


@router.message(AdminFSM.await_plan_title)
async def sales_collect_title(message: types.Message, state: FSMContext):
    if not message.text:
        await message.answer("لطفاً عنوان متنی وارد کنید.")
        return
    await state.update_data(new_plan={"title": message.text.strip()})
    await state.set_state(AdminFSM.await_plan_duration)
    await message.answer("مدت اشتراک را به روز وارد کنید (مثلاً 30).")


@router.message(AdminFSM.await_plan_duration)
async def sales_collect_duration(message: types.Message, state: FSMContext):
    duration = _parse_numeric_value(message.text or "")
    if duration is None or duration <= 0:
        await message.answer("مدت باید یک عدد صحیح بزرگ‌تر از صفر باشد. دوباره تلاش کنید.")
        return
    data = await state.get_data()
    data.setdefault("new_plan", {})["duration_days"] = duration
    await state.update_data(new_plan=data["new_plan"])
    await state.set_state(AdminFSM.await_plan_download_limit)
    await message.answer("سقف دانلود روزانه را وارد کنید. برای نامحدود عدد -1 یا کلمه نامحدود را وارد کنید.")


@router.message(AdminFSM.await_plan_download_limit)
async def sales_collect_download_limit(message: types.Message, state: FSMContext):
    download_limit = _parse_numeric_value(message.text or "", allow_unlimited=True)
    if download_limit is None or download_limit < -1:
        await message.answer("عدد وارد شده معتبر نیست. دوباره تلاش کنید.")
        return
    data = await state.get_data()
    data.setdefault("new_plan", {})["download_limit"] = download_limit
    await state.update_data(new_plan=data["new_plan"])
    await state.set_state(AdminFSM.await_plan_encode_limit)
    await message.answer("سقف انکد روزانه را وارد کنید. مانند قبل می‌توانید -1 برای نامحدود وارد کنید.")


@router.message(AdminFSM.await_plan_encode_limit)
async def sales_collect_encode_limit(message: types.Message, state: FSMContext):
    encode_limit = _parse_numeric_value(message.text or "", allow_unlimited=True)
    if encode_limit is None or encode_limit < -1:
        await message.answer("عدد وارد شده معتبر نیست. دوباره تلاش کنید.")
        return
    data = await state.get_data()
    data.setdefault("new_plan", {})["encode_limit"] = encode_limit
    await state.update_data(new_plan=data["new_plan"])
    await state.set_state(AdminFSM.await_plan_price)
    await message.answer("قیمت اشتراک را به تومان وارد کنید (مثلاً 300000).")


@router.message(AdminFSM.await_plan_price)
async def sales_collect_price(message: types.Message, state: FSMContext, session: AsyncSession):
    price = _parse_numeric_value(message.text or "")
    if price is None or price <= 0:
        await message.answer("قیمت باید یک عدد صحیح بزرگ‌تر از صفر باشد. دوباره تلاش کنید.")
        return

    data = await state.get_data()
    plan_data = data.get("new_plan", {})
    plan_data["price_toman"] = price

    await database.create_subscription_plan(
        session,
        title=plan_data.get("title", "اشتراک"),
        description=None,
        duration_days=plan_data.get("duration_days", 30),
        download_limit=plan_data.get("download_limit", -1),
        encode_limit=plan_data.get("encode_limit", -1),
        price_toman=plan_data.get("price_toman", price),
    )

    await state.set_state(AdminFSM.sales_menu)
    await state.update_data(new_plan={})
    await message.answer("اشتراک جدید با موفقیت ثبت شد.")
    text, keyboard = await build_plan_management_keyboard(session)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(AdminFSM.sales_menu, F.data == "sales_remove_plan")
async def sales_remove_plan(query: CallbackQuery, session: AsyncSession):
    plans = await database.list_subscription_plans(session, include_inactive=True)
    text, keyboard = build_plan_removal_keyboard(plans, empty_text="اشتراکی برای حذف وجود ندارد.")
    await query.message.edit_text(text, reply_markup=keyboard)
    await query.answer()


@router.callback_query(AdminFSM.sales_menu, F.data.startswith("sales_delete_"))
async def sales_delete_plan(query: CallbackQuery, session: AsyncSession):
    try:
        plan_id = int(query.data.replace("sales_delete_", ""))
    except ValueError:
        await query.answer("شناسه اشتراک نامعتبر است.", show_alert=True)
        return

    deleted = await database.delete_subscription_plan(session, plan_id)
    if deleted:
        await query.answer("اشتراک حذف شد.")
    else:
        await query.answer("حذف اشتراک با مشکل مواجه شد.", show_alert=True)
    text, keyboard = await build_plan_management_keyboard(session)
    await query.message.edit_text(text, reply_markup=keyboard)


@router.callback_query(AdminFSM.sales_menu, F.data == "sales_manage_api")
async def sales_manage_api(query: CallbackQuery, session: AsyncSession):
    api_key = await database.get_payment_setting(session, "nowpayments_api_key")
    text = f"کلید فعلی: {mask_api_key(api_key)}"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="ثبت / تغییر API Key", callback_data="sales_set_api")],
            [InlineKeyboardButton(text="حذف API Key", callback_data="sales_clear_api")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="sales_back_overview")],
        ]
    )
    await query.message.edit_text(text, reply_markup=keyboard)
    await query.answer()


@router.callback_query(AdminFSM.sales_menu, F.data == "sales_set_api")
async def sales_set_api(query: CallbackQuery, state: FSMContext):
    await state.set_state(AdminFSM.await_api_key)
    await query.message.edit_text("API Key جدید NowPayments را ارسال کنید. برای لغو /cancel را بزنید.")
    await query.answer()


@router.message(AdminFSM.await_api_key)
async def sales_receive_api_key(message: types.Message, state: FSMContext, session: AsyncSession):
    api_key = (message.text or "").strip()
    if not api_key:
        await message.answer("API Key نمی‌تواند خالی باشد. دوباره تلاش کنید یا /cancel را بزنید.")
        return

    await database.set_payment_setting(session, "nowpayments_api_key", api_key)
    await state.set_state(AdminFSM.sales_menu)
    text, keyboard = await build_sales_overview(session)
    await message.answer("API Key با موفقیت ذخیره شد.")
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(AdminFSM.sales_menu, F.data == "sales_clear_api")
async def sales_clear_api(query: CallbackQuery, session: AsyncSession):
    await database.clear_payment_setting(session, "nowpayments_api_key")
    text, keyboard = await build_sales_overview(session)
    await query.message.edit_text("API Key حذف شد.")
    await query.message.answer(text, reply_markup=keyboard)
    await query.answer("API Key حذف شد.")

@router.message(AdminFSM.panel, F.text == "⚙️ مدیریت اشتراک")
async def ask_for_user_id(message: types.Message, state: FSMContext):
    await message.answer("Please enter the User ID (UID) to manage:")
    await state.set_state(AdminFSM.await_sub_user_id)

@router.message(AdminFSM.await_sub_user_id)
async def receive_user_id_for_sub(message: types.Message, state: FSMContext, session: AsyncSession):
    if not message.text or not message.text.isdigit():
        await message.answer("Invalid ID. Please enter a number.")
        return
    target_user_id = int(message.text)
    await state.update_data(target_user_id=target_user_id)
    info_text, keyboard = await get_subscription_panel(session, target_user_id)
    await message.answer(info_text, reply_markup=keyboard, parse_mode="Markdown")
    await state.set_state(AdminFSM.manage_user_sub)

@router.callback_query(AdminFSM.manage_user_sub, F.data.startswith("sub_"))
async def handle_sub_management_callback(query: CallbackQuery, state: FSMContext, session: AsyncSession):
    state_data = await state.get_data()
    target_user_id = state_data.get('target_user_id')
    if not target_user_id:
        await query.answer("Error: User session expired. Please try again.", show_alert=True)
        return

    action = query.data.replace("sub_", "")
    user = await database.get_or_create_user(session, target_user_id)

    if action == "back_to_panel":
        await query.message.delete()
        await state.set_state(AdminFSM.panel)
        # We don't need to resend the panel, as the user will use the reply keyboard
        await query.answer("Returned to main panel.")
        return

    # --- Feature Toggles ---
    if action == "toggle_thumbnail":
        user.allow_thumbnail = not user.allow_thumbnail
        await query.answer(f"Thumbnail access: {'Enabled' if user.allow_thumbnail else 'Disabled'}")
    elif action == "toggle_watermark":
        user.allow_watermark = not user.allow_watermark
        await query.answer(f"Watermark access: {'Enabled' if user.allow_watermark else 'Disabled'}")

    # --- Subscription Toggles ---
    elif action.startswith("toggle_site_"):
        site_name = action.replace("toggle_site_", "")
        current_sites = user.sub_allowed_sites.copy()
        current_sites[site_name] = not current_sites.get(site_name, False)
        user.sub_allowed_sites = current_sites
        flag_modified(user, "sub_allowed_sites")
        await query.answer(f"{site_name} access changed.")
    elif action == "toggle_active":
        user.sub_is_active = not user.sub_is_active
        await query.answer(f"Subscription: {'Activated' if user.sub_is_active else 'Deactivated'}")
    elif action == "activate_all":
        user.sub_allowed_sites = {site: True for category in ALL_SUPPORTED_SITES.values() for site in category}
        flag_modified(user, "sub_allowed_sites")
        await query.answer("All sites activated.")
    elif action == "deactivate_all":
        user.sub_allowed_sites = {site: False for category in ALL_SUPPORTED_SITES.values() for site in category}
        flag_modified(user, "sub_allowed_sites")
        await query.answer("All sites deactivated.")
    elif action.startswith("add_days_"):
        days = int(action.replace("add_days_", ""))
        base_time = user.sub_expiry_date or datetime.now()
        if base_time < datetime.now():
            base_time = datetime.now()
        user.sub_expiry_date = base_time + timedelta(days=days)
        await query.answer(f"{abs(days)} days {'added' if days > 0 else 'removed'}.")
    elif action.startswith("add_download_limit_"):
        limit_action = action.replace("add_download_limit_", "")
        if limit_action == "0":
            user.sub_download_limit = -1
        else:
            limit_change = int(limit_action)
            current_limit = 0 if user.sub_download_limit == -1 else user.sub_download_limit
            user.sub_download_limit = max(0, current_limit + limit_change)
        await query.answer("Download limit changed.")
    elif action.startswith("add_encode_limit_"):
        limit_action = action.replace("add_encode_limit_", "")
        if limit_action == "0":
            user.sub_encode_limit = -1
        else:
            limit_change = int(limit_action)
            current_limit = 0 if user.sub_encode_limit == -1 else user.sub_encode_limit
            user.sub_encode_limit = max(0, current_limit + limit_change)
        await query.answer("Encode limit changed.")
    
    await session.commit()
    info_text, keyboard = await get_subscription_panel(session, target_user_id)
    await query.message.edit_text(info_text, reply_markup=keyboard, parse_mode="Markdown")

@router.message(AdminFSM.panel, F.text == "📢 همگانی")
async def broadcast_entry(message: types.Message, state: FSMContext):
    await message.answer("Please send the message you want to broadcast to all users. To cancel, type /cancel.")
    await state.set_state(AdminFSM.await_broadcast)

@router.message(AdminFSM.await_broadcast)
async def process_broadcast(message: types.Message, state: FSMContext, session: AsyncSession):
    all_users = await database.get_all_users(session)
    sent_count, failed_count = 0, 0
    status_msg = await message.answer(f"Broadcasting message to {len(all_users)} users...")

    for user in all_users:
        try:
            await message.copy_to(chat_id=user.id)
            sent_count += 1
            await asyncio.sleep(0.1)
        except Exception:
            failed_count += 1
    
    await status_msg.edit_text(f"✅ Broadcast sent to {sent_count} users.\n❌ Failed for {failed_count} users.")
    await state.set_state(AdminFSM.panel)

@router.message(AdminFSM.panel, F.text == "📝 متن ها")
async def texts_panel_command(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Edit Help Text", callback_data="texts_edit_help")]])
    await message.answer("Which text do you want to edit?", reply_markup=keyboard)

@router.callback_query(F.data == "texts_edit_help")
async def texts_panel_callback(query: types.CallbackQuery, state: FSMContext):
    await query.message.edit_text("Please send the new help text. To cancel, type /cancel.")
    await state.set_state(AdminFSM.await_help_text)

@router.message(AdminFSM.await_help_text)
async def await_help_text_handler(message: types.Message, state: FSMContext, session: AsyncSession):
    await database.set_text(session, key="help_text", value=message.text)
    await message.answer("✅ Help text updated successfully.")
    await state.set_state(AdminFSM.panel)

# --- START OF CORRECTION ---
@router.message(AdminFSM.panel, F.text == "❌ خروج از پنل")
async def admin_exit(message: types.Message, state: FSMContext, session: AsyncSession):
    """Handles exiting the admin panel and shows the main user panel."""
    await message.answer("You have exited the Admin Panel.", reply_markup=ReplyKeyboardRemove())
    await state.clear()
    # Call the start handler to show the user panel
    await handle_start(message, session)
# --- END OF CORRECTION ---


@router.message(F.text == "/cancel")
async def admin_cancel(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None or current_state == AdminFSM.panel.state:
        await message.answer("هیچ عملیات فعالی برای لغو وجود ندارد.")
        return
    await state.set_state(AdminFSM.panel)
    await message.answer("عملیات لغو شد.", reply_markup=get_admin_panel_keyboard())

