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

# --- Keyboards ---
def get_admin_panel_keyboard() -> ReplyKeyboardMarkup:
    """Creates the main admin reply keyboard."""
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📊 آمار"), KeyboardButton(text="📢 همگانی")],
        [KeyboardButton(text="⚙️ مدیریت اشتراک"), KeyboardButton(text="📝 متن ها")],
        [KeyboardButton(text="❌ خروج از پنل")]
    ], resize_keyboard=True)

async def get_subscription_panel(session: AsyncSession, target_user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    """Creates the inline keyboard for managing a user's subscription."""
    user = await database.get_or_create_user(session, target_user_id)

    expiry_date = user.sub_expiry_date
    remain_days = "Unlimited"
    if expiry_date:
        delta = expiry_date - datetime.now()
        remain_days = max(0, delta.days)

    limit = user.sub_download_limit
    limit_text = "Unlimited" if limit == -1 else str(limit)

    info_text = f"👤 @{user.username or 'N/A'}\nUID: `{user.id}`\nDays Left: **{remain_days}**\nLimit: **{limit_text}**/day"

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
        [InlineKeyboardButton(text="Limit: -10", callback_data="sub_add_limit_-10"),
         InlineKeyboardButton(text="Limit: +10", callback_data="sub_add_limit_10"),
         InlineKeyboardButton(text="Limit: No Limit", callback_data="sub_add_limit_0")],
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
    stats = await database.get_bot_stats(session)

    def fmt_count(value: int) -> str:
        return f"{value:02d}"

    def fmt_size(bytes_value: int) -> str:
        gb_value = bytes_value / (1024 ** 3)
        return f"{gb_value:.2f}GB"

    popular_sites = stats["popular_sites"] or []
    if popular_sites:
        popular_lines = "\n".join(f"• {site}" for site in popular_sites)
    else:
        popular_lines = "• No data yet"

    stats_text = (
        "📊 Bot Stats\n\n"
        "👥 Users\n"
        f"• Total Users: {fmt_count(stats['total_users'])}\n"
        f"• Users (Today): {fmt_count(stats['users_today'])}\n\n"
        "💳 Subscriptions\n"
        f"• Active Subscriptions: {fmt_count(stats['active_subscriptions'])}\n"
        f"• Expired Subscriptions: {fmt_count(stats['expired_subscriptions'])}\n\n"
        "🌐 Most Popular Sites\n"
        f"{popular_lines}\n\n"
        "📥 Downloads\n"
        f"• Total Downloads: {fmt_count(stats['total_downloads'])}\n"
        f"• Downloads (Today): {fmt_count(stats['downloads_today'])}\n\n"
        "🏷 Sizes\n"
        f"• Total Downloads Size: {fmt_size(stats['total_size_bytes'])}\n"
        f"• Downloads Size (Today): {fmt_size(stats['size_today_bytes'])}\n\n"
        "@OviaRobot"
    )

    await message.answer(stats_text)

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
    elif action.startswith("add_limit_"):
        limit_action = action.replace("add_limit_", "")
        if limit_action == "0":
            user.sub_download_limit = -1
        else:
            limit_change = int(limit_action)
            current_limit = 0 if user.sub_download_limit == -1 else user.sub_download_limit
            user.sub_download_limit = max(0, current_limit + limit_change)
        await query.answer("Download limit changed.")
    
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

