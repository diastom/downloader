import asyncio
from datetime import datetime, timedelta
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup

from ...config import settings
from ...utils import database
from ...utils.helpers import ALL_SUPPORTED_SITES

router = Router()
# This router will only handle messages from users whose ID is in the admin list
router.message.filter(F.from_user.id.in_(settings.admin_ids))
router.callback_query.filter(F.from_user.id.in_(settings.admin_ids))

# --- FSM States ---
class AdminFSM(StatesGroup):
    panel = State()
    await_broadcast = State()
    await_forward = State()
    await_sub_user_id = State()
    manage_user_sub = State()
    texts_panel = State()
    await_help_text = State()

# --- Keyboards ---
def get_admin_panel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📊 آمار"), KeyboardButton(text="📢 همگانی")],
        [KeyboardButton(text="⚙️ مدیریت اشتراک"), KeyboardButton(text="📝 متن ها")],
        [KeyboardButton(text="❌ خروج از پنل")]
    ], resize_keyboard=True)

# --- Helper to build the subscription panel ---
async def get_subscription_panel(target_user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    user_data = database.get_user_data(target_user_id)
    sub = user_data.get('subscription', {})
    username = user_data.get('username') or "N/A"

    expiry_date_str = sub.get('expiry_date')
    remain_days = "Unlimited"
    if expiry_date_str:
        try:
            delta = datetime.fromisoformat(expiry_date_str) - datetime.now()
            remain_days = max(0, delta.days)
        except (ValueError, TypeError): remain_days = "Invalid"

    limit = sub.get('download_limit', -1)
    limit_text = "Unlimited" if limit == -1 else str(limit)

    info_text = (f"👤 @{username}\nUID: `{target_user_id}`\n"
                 f"Days Left: **{remain_days}**\nLimit: **{limit_text}**/day")

    keyboard = []
    status_text = "ACTIVE ✅" if sub.get('is_active') else "DEACTIVATED ❌"
    keyboard.append([InlineKeyboardButton(text=status_text, callback_data=f"sub_toggle_active")])

    all_sites = [site for category in ALL_SUPPORTED_SITES.values() for site in category]
    row = []
    for site in all_sites:
        status = "☑️" if sub.get('allowed_sites', {}).get(site) else "✖️"
        row.append(InlineKeyboardButton(text=f"{site} {status}", callback_data=f"sub_toggle_site_{site}"))
        if len(row) >= 2:
            keyboard.append(row)
            row = []
    if row: keyboard.append(row)

    keyboard.append([InlineKeyboardButton(text="Activate All", callback_data="sub_activate_all"),
                     InlineKeyboardButton(text="Deactivate All", callback_data="sub_deactivate_all")])

    keyboard.append([InlineKeyboardButton(text="-10d", callback_data="sub_add_days_-10"),
                     InlineKeyboardButton(text="+10d", callback_data="sub_add_days_10"),
                     InlineKeyboardButton(text="+30d", callback_data="sub_add_days_30")])

    keyboard.append([InlineKeyboardButton(text="Limit: -10", callback_data="sub_add_limit_-10"),
                     InlineKeyboardButton(text="Limit: +10", callback_data="sub_add_limit_10"),
                     InlineKeyboardButton(text="Limit: No Limit", callback_data="sub_add_limit_0")])

    return info_text, InlineKeyboardMarkup(inline_keyboard=keyboard)


# --- FSM Handlers ---

@router.message(Command("admin"))
async def admin_panel_entry(message: types.Message, state: FSMContext):
    await message.answer("به پنل ادمین خوش آمدید.", reply_markup=get_admin_panel_keyboard())
    await state.set_state(AdminFSM.panel)

@router.message(AdminFSM.panel, F.text == "📊 آمار")
async def show_stats(message: types.Message):
    db = database.get_all_users()
    total_users = len(db)
    today_str = str(datetime.now().date())
    downloads_today, active_subs, expired_subs = 0, 0, 0
    site_usage = {}

    for data in db.values():
        if isinstance(data, dict):
            if data.get('stats', {}).get('downloads_today', {}).get('date') == today_str:
                downloads_today += data['stats']['downloads_today'].get('count', 0)
            if data.get('subscription', {}).get('is_active'):
                active_subs += 1
            for site, count in data.get('stats', {}).get('site_usage', {}).items():
                site_usage[site] = site_usage.get(site, 0) + count

    top_sites = "\n".join([f"• {s}: {c}" for s, c in sorted(site_usage.items(), key=lambda item: item[1], reverse=True)[:5]])
    stats_text = (f"📊 **Bot Statistics**\n\n"
                  f"👥 **Users:** {total_users}\n"
                  f"📥 **Downloads (Today):** {downloads_today}\n"
                  f"💳 **Active Subs:** {active_subs}\n\n"
                  f"🌐 **Top Sites:**\n{top_sites}")
    await message.answer(stats_text, parse_mode="Markdown")

@router.message(AdminFSM.panel, F.text == "⚙️ مدیریت اشتراک")
async def ask_for_user_id(message: types.Message, state: FSMContext):
    await message.answer("Please enter the User ID (UID) to manage:")
    await state.set_state(AdminFSM.await_sub_user_id)

@router.message(AdminFSM.await_sub_user_id)
async def receive_user_id_for_sub(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Invalid ID. Please enter a number.")
        return
    target_user_id = int(message.text)
    await state.update_data(target_user_id=target_user_id)
    info_text, keyboard = await get_subscription_panel(target_user_id)
    await message.answer(info_text, reply_markup=keyboard, parse_mode="Markdown")
    await state.set_state(AdminFSM.manage_user_sub)

@router.callback_query(AdminFSM.manage_user_sub, F.data.startswith("sub_"))
async def handle_sub_management_callback(query: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id = data['target_user_id']
    user_data = database.get_user_data(user_id)
    sub = user_data['subscription']
    action = query.data.replace("sub_", "")

    if action == "toggle_active":
        sub['is_active'] = not sub['is_active']
    elif action.startswith("toggle_site_"):
        site = action.replace("toggle_site_", "")
        sub['allowed_sites'][site] = not sub['allowed_sites'].get(site, False)
    elif action == "activate_all":
        for site in sub['allowed_sites']: sub['allowed_sites'][site] = True
    elif action == "deactivate_all":
        for site in sub['allowed_sites']: sub['allowed_sites'][site] = False
    elif action.startswith("add_days_"):
        days = int(action.replace("add_days_", ""))
        base_time = datetime.now()
        if sub['expiry_date']:
            current_expiry = datetime.fromisoformat(sub['expiry_date'])
            if current_expiry > base_time: base_time = current_expiry
        sub['expiry_date'] = str(base_time + timedelta(days=days))
    elif action.startswith("add_limit_"):
        limit_change = int(action.replace("add_limit_", ""))
        if limit_change == 0: sub['download_limit'] = -1
        else:
            current_limit = sub.get('download_limit', -1)
            sub['download_limit'] = limit_change if current_limit == -1 else current_limit + limit_change

    database.update_user_data(user_id, user_data)
    info_text, keyboard = await get_subscription_panel(user_id)
    await query.message.edit_text(info_text, reply_markup=keyboard, parse_mode="Markdown")
    await query.answer("Updated!")

@router.message(AdminFSM.panel, F.text == "❌ خروج از پنل")
async def admin_exit(message: types.Message, state: FSMContext):
    await message.answer("You have exited the Admin Panel.", reply_markup=types.ReplyKeyboardRemove())
    await state.clear()

# ... (Broadcast and Texts panel handlers would be similarly fleshed out) ...
