import asyncio
from datetime import datetime, timedelta
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery, ReplyKeyboardRemove
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

# --- START OF CORRECTION ---
# Import the necessary start handler and keyboard from the common handlers
from bot.handlers.common import handle_start
# --- END OF CORRECTION ---

from config import settings
from utils import database, payments
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
    await_plan_name = State()
    await_plan_duration = State()
    await_plan_download_limit = State()
    await_plan_encode_limit = State()
    await_plan_price = State()
    await_plan_description = State()
    await_wallet_address = State()

# --- Keyboards ---
def get_admin_panel_keyboard() -> ReplyKeyboardMarkup:
    """Creates the main admin reply keyboard."""
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📊 آمار"), KeyboardButton(text="📢 همگانی")],
        [KeyboardButton(text="⚙️ مدیریت اشتراک"), KeyboardButton(text="📝 متن ها")],
        [KeyboardButton(text="تنظیمات فروش"), KeyboardButton(text="❌ خروج از پنل")]
    ], resize_keyboard=True)


def get_sales_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="اشتراک ها"), KeyboardButton(text="مدیریت ولت ها")],
        [KeyboardButton(text="🔙 بازگشت")]
    ], resize_keyboard=True)


def _format_limit_value(value: int) -> str:
    return "نامحدود" if value is None or value < 0 else f"{value}"


async def build_subscription_overview(session: AsyncSession) -> tuple[str, InlineKeyboardMarkup]:
    plans = await database.get_subscription_plans(session, include_inactive=True)
    if not plans:
        text = "هنوز هیچ اشتراکی تعریف نشده است."
    else:
        lines = ["انواع اشتراک‌ها:"]
        for idx, plan in enumerate(plans, start=1):
            lines.append(
                (
                    f"\n{idx}. {plan.name}\n"
                    f"مدت اشتراک: {plan.duration_days} روز\n"
                    f"سقف دانلود روزانه: {_format_limit_value(plan.download_limit_per_day)}\n"
                    f"سقف انکد روزانه: {_format_limit_value(plan.encode_limit_per_day)}\n"
                    f"قیمت: {plan.price_toman:,} تومان"
                )
            )
            if plan.description:
                lines.append(f"توضیحات: {plan.description}")
        text = "\n".join(lines)

    buttons = [[InlineKeyboardButton(text="➕ افزودن نوع جدید اشتراک", callback_data="sales_add_plan")]]
    if plans:
        buttons.append([InlineKeyboardButton(text="🗑 حذف نوع اشتراک", callback_data="sales_delete_plan")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    return text, keyboard


async def build_wallet_overview(session: AsyncSession) -> tuple[str, InlineKeyboardMarkup]:
    wallets = await database.get_wallet_settings_map(session)
    lines = ["مدیریت ولت‌ها:"]
    buttons = []
    for code, meta in payments.CURRENCIES.items():
        wallet = wallets.get(code)
        if wallet:
            lines.append(f"\n{meta.display_name}: {wallet.address}")
        else:
            lines.append(f"\n{meta.display_name}: تنظیم نشده")
        buttons.append([InlineKeyboardButton(text=meta.display_name, callback_data=f"wallet_edit_{code}")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    return "\n".join(lines), keyboard

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

@router.message(AdminFSM.panel, F.text == "⚙️ مدیریت اشتراک")
async def ask_for_user_id(message: types.Message, state: FSMContext):
    await message.answer("Please enter the User ID (UID) to manage:")
    await state.set_state(AdminFSM.await_sub_user_id)


@router.message(AdminFSM.panel, F.text == "تنظیمات فروش")
async def open_sales_menu(message: types.Message, state: FSMContext):
    await state.set_state(AdminFSM.sales_menu)
    await message.answer(
        "بخش تنظیمات فروش فعال شد. یکی از گزینه‌های زیر را انتخاب کنید.",
        reply_markup=get_sales_keyboard(),
    )


@router.message(AdminFSM.sales_menu, F.text == "🔙 بازگشت")
async def exit_sales_menu(message: types.Message, state: FSMContext):
    await state.set_state(AdminFSM.panel)
    await message.answer("به منوی اصلی مدیریت بازگشتید.", reply_markup=get_admin_panel_keyboard())


@router.message(AdminFSM.sales_menu, F.text == "اشتراک ها")
async def show_sales_plans(message: types.Message, session: AsyncSession):
    text, keyboard = await build_subscription_overview(session)
    await message.answer(text, reply_markup=keyboard)


@router.message(AdminFSM.sales_menu, F.text == "مدیریت ولت ها")
async def show_wallets_overview(message: types.Message, session: AsyncSession):
    text, keyboard = await build_wallet_overview(session)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data == "sales_add_plan")
async def sales_add_plan(query: CallbackQuery, state: FSMContext):
    await query.answer()
    await query.message.answer("نام اشتراک جدید را وارد کنید:")
    await state.set_state(AdminFSM.await_plan_name)
    await state.update_data(new_plan={})


@router.callback_query(F.data == "sales_delete_plan")
async def sales_delete_plan_menu(query: CallbackQuery, session: AsyncSession):
    await query.answer()
    plans = await database.get_subscription_plans(session, include_inactive=True)
    if not plans:
        await query.message.answer("اشتراکی برای حذف وجود ندارد.")
        return
    buttons = [
        [InlineKeyboardButton(text=f"{plan.name} ({plan.id})", callback_data=f"sales_delete_plan_{plan.id}")]
        for plan in plans
    ]
    buttons.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="sales_back_to_plans")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    await query.message.answer("کدام اشتراک حذف شود؟", reply_markup=keyboard)


@router.callback_query(F.data == "sales_back_to_plans")
async def sales_back_to_plans(query: CallbackQuery, session: AsyncSession):
    await query.answer()
    text, keyboard = await build_subscription_overview(session)
    await query.message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("sales_delete_plan_"))
async def sales_delete_plan_confirm(query: CallbackQuery, session: AsyncSession):
    await query.answer()
    try:
        plan_id = int(query.data.replace("sales_delete_plan_", ""))
    except ValueError:
        await query.message.answer("شناسه اشتراک نامعتبر است.")
        return
    deleted = await database.delete_subscription_plan(session, plan_id)
    if deleted:
        await query.message.answer("اشتراک مورد نظر حذف شد.")
        text, keyboard = await build_subscription_overview(session)
        await query.message.answer(text, reply_markup=keyboard)
    else:
        await query.message.answer("حذف انجام نشد. لطفاً دوباره تلاش کنید.")


@router.message(AdminFSM.await_plan_name)
async def sales_plan_receive_name(message: types.Message, state: FSMContext):
    name = (message.text or "").strip()
    if not name:
        await message.answer("نام معتبر نیست. دوباره تلاش کنید:")
        return
    await state.update_data(new_plan={"name": name})
    await message.answer("مدت اشتراک را به تعداد روز وارد کنید:")
    await state.set_state(AdminFSM.await_plan_duration)


@router.message(AdminFSM.await_plan_duration)
async def sales_plan_receive_duration(message: types.Message, state: FSMContext):
    try:
        duration = int(message.text)
        if duration <= 0:
            raise ValueError
    except (TypeError, ValueError):
        await message.answer("عدد روز باید بزرگتر از صفر باشد. دوباره وارد کنید:")
        return
    data = await state.get_data()
    plan = data.get("new_plan", {})
    plan["duration_days"] = duration
    await state.update_data(new_plan=plan)
    await message.answer("سقف دانلود روزانه را وارد کنید (برای نامحدود عدد -1 را ارسال کنید):")
    await state.set_state(AdminFSM.await_plan_download_limit)


@router.message(AdminFSM.await_plan_download_limit)
async def sales_plan_receive_download_limit(message: types.Message, state: FSMContext):
    try:
        limit = int(message.text)
    except (TypeError, ValueError):
        await message.answer("لطفاً یک عدد صحیح وارد کنید:")
        return
    data = await state.get_data()
    plan = data.get("new_plan", {})
    plan["download_limit_per_day"] = limit
    await state.update_data(new_plan=plan)
    await message.answer("سقف انکد روزانه را وارد کنید (برای نامحدود عدد -1 را ارسال کنید):")
    await state.set_state(AdminFSM.await_plan_encode_limit)


@router.message(AdminFSM.await_plan_encode_limit)
async def sales_plan_receive_encode_limit(message: types.Message, state: FSMContext):
    try:
        limit = int(message.text)
    except (TypeError, ValueError):
        await message.answer("لطفاً یک عدد صحیح وارد کنید:")
        return
    data = await state.get_data()
    plan = data.get("new_plan", {})
    plan["encode_limit_per_day"] = limit
    await state.update_data(new_plan=plan)
    await message.answer("قیمت اشتراک را به تومان وارد کنید:")
    await state.set_state(AdminFSM.await_plan_price)


@router.message(AdminFSM.await_plan_price)
async def sales_plan_receive_price(message: types.Message, state: FSMContext):
    try:
        price = int(message.text.replace(",", ""))
        if price <= 0:
            raise ValueError
    except (TypeError, ValueError):
        await message.answer("قیمت باید یک عدد بزرگتر از صفر باشد. دوباره تلاش کنید:")
        return
    data = await state.get_data()
    plan = data.get("new_plan", {})
    plan["price_toman"] = price
    await state.update_data(new_plan=plan)
    await message.answer("در صورت نیاز توضیحاتی برای اشتراک وارد کنید (یا - برای خالی بودن):")
    await state.set_state(AdminFSM.await_plan_description)


@router.message(AdminFSM.await_plan_description, F.text)
async def sales_plan_receive_description(message: types.Message, state: FSMContext, session: AsyncSession):
    description = message.text.strip()
    if description == "-":
        description = None
    data = await state.get_data()
    plan = data.get("new_plan", {})
    if not plan:
        await message.answer("داده‌های اشتراک یافت نشد. لطفاً دوباره تلاش کنید.")
        await state.set_state(AdminFSM.sales_menu)
        return
    plan["description"] = description
    await database.create_subscription_plan(session, **plan)
    await message.answer("اشتراک جدید با موفقیت ذخیره شد.")
    await state.set_state(AdminFSM.sales_menu)
    text, keyboard = await build_subscription_overview(session)
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("wallet_edit_"))
async def wallet_edit_prompt(query: CallbackQuery, state: FSMContext, session: AsyncSession):
    await query.answer()
    currency_code = query.data.replace("wallet_edit_", "")
    meta = payments.CURRENCIES.get(currency_code)
    if not meta:
        await query.message.answer("ارز انتخابی پشتیبانی نمی‌شود.")
        return
    wallet = await database.get_wallet_setting(session, currency_code)
    current_address = wallet.address if wallet else "-"
    await state.set_state(AdminFSM.await_wallet_address)
    await state.update_data(wallet_currency=currency_code)
    await query.message.answer(
        (
            f"آدرس ولت جدید برای {meta.display_name} را ارسال کنید.\n"
            f"آدرس فعلی: {current_address}\n"
            f"{meta.instructions}"
        )
    )


@router.message(AdminFSM.await_wallet_address)
async def wallet_receive_address(message: types.Message, state: FSMContext, session: AsyncSession):
    text = (message.text or "").strip()
    if text in {"/cancel", "لغو", "cancel"}:
        await state.set_state(AdminFSM.sales_menu)
        await message.answer("عملیات لغو شد.", reply_markup=get_sales_keyboard())
        return
    data = await state.get_data()
    currency_code = data.get("wallet_currency")
    if not currency_code:
        await message.answer("خطا در تشخیص ارز. لطفاً از ابتدا تلاش کنید.")
        await state.set_state(AdminFSM.sales_menu)
        return
    if not text:
        await message.answer("آدرس نمی‌تواند خالی باشد. دوباره ارسال کنید:")
        return
    await database.set_wallet_setting(session, currency_code=currency_code, address=text)
    await message.answer("آدرس ولت با موفقیت ذخیره شد.")
    await state.set_state(AdminFSM.sales_menu)
    overview_text, keyboard = await build_wallet_overview(session)
    await message.answer(overview_text, reply_markup=keyboard)

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
    stored_text = message.html_text if message.html_text is not None else message.text
    await database.set_text(session, key="help_text", value=stored_text)
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

