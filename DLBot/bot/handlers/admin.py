import asyncio
from datetime import datetime, timedelta
from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from utils import database
from utils.helpers import ALL_SUPPORTED_SITES

router = Router()
router.message.filter(F.from_user.id.in_(settings.admin_ids))
router.callback_query.filter(F.from_user.id.in_(settings.admin_ids))

class AdminFSM(StatesGroup):
    panel = State()
    await_broadcast = State()
    await_sub_user_id = State()
    manage_user_sub = State()
    await_help_text = State()

def get_admin_panel_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📊 آمار"), KeyboardButton(text="📢 همگانی")],
        [KeyboardButton(text="⚙️ مدیریت اشتراک"), KeyboardButton(text="📝 متن ها")],
        [KeyboardButton(text="❌ خروج از پنل")]
    ], resize_keyboard=True)

async def get_subscription_panel(session: AsyncSession, target_user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    user = await database.get_or_create_user(session, target_user_id)

    expiry_date = user.sub_expiry_date
    remain_days = "Unlimited"
    if expiry_date:
        delta = expiry_date - datetime.now()
        remain_days = max(0, delta.days)

    limit = user.sub_download_limit
    limit_text = "Unlimited" if limit == -1 else str(limit)

    info_text = f"👤 @{user.username}\nUID: `{user.id}`\nDays Left: **{remain_days}**\nLimit: **{limit_text}**/day"

    keyboard = []
    status_text = "ACTIVE ✅" if user.sub_is_active else "DEACTIVATED ❌"
    keyboard.append([InlineKeyboardButton(text=status_text, callback_data="sub_toggle_active")])

    all_sites = [site for category in ALL_SUPPORTED_SITES.values() for site in category]
    row = []
    for site in all_sites:
        status = "☑️" if user.sub_allowed_sites.get(site) else "✖️"
        row.append(InlineKeyboardButton(text=f"{site} {status}", callback_data=f"sub_toggle_site_{site}"))
        if len(row) >= 2:
            keyboard.append(row); row = []
    if row: keyboard.append(row)

    keyboard.extend([
        [InlineKeyboardButton("Activate All", "sub_activate_all"), InlineKeyboardButton("Deactivate All", "sub_deactivate_all")],
        [InlineKeyboardButton("-10d", "sub_add_days_-10"), InlineKeyboardButton("+10d", "sub_add_days_10"), InlineKeyboardButton("+30d", "sub_add_days_30")],
        [InlineKeyboardButton("Limit: -10", "sub_add_limit_-10"), InlineKeyboardButton("Limit: +10", "sub_add_limit_10"), InlineKeyboardButton("Limit: No Limit", "sub_add_limit_0")]
    ])
    return info_text, InlineKeyboardMarkup(inline_keyboard=keyboard)

@router.message(Command("admin"))
async def admin_panel_entry(message: types.Message, state: FSMContext):
    await message.answer("به پنل ادمین خوش آمدید.", reply_markup=get_admin_panel_keyboard())
    await state.set_state(AdminFSM.panel)

@router.message(AdminFSM.panel, F.text == "📊 آمار")
async def show_stats(message: types.Message, session: AsyncSession):
    all_users = await database.get_all_users(session)
    active_subs = sum(1 for u in all_users if u.sub_is_active)
    total_downloads = sum(sum(u.stats_site_usage.values()) for u in all_users if u.stats_site_usage)
    stats_text = f"📊 **Bot Stats**\n\n👥 Users: {len(all_users)}\n💳 Active Subs: {active_subs}\n📥 Total Downloads: {total_downloads}"
    await message.answer(stats_text, parse_mode="Markdown")

@router.message(AdminFSM.panel, F.text == "⚙️ مدیریت اشتراک")
async def ask_for_user_id(message: types.Message, state: FSMContext):
    await message.answer("Please enter the User ID (UID) to manage:")
    await state.set_state(AdminFSM.await_sub_user_id)

@router.message(AdminFSM.await_sub_user_id)
async def receive_user_id_for_sub(message: types.Message, state: FSMContext, session: AsyncSession):
    if not message.text.isdigit():
        await message.answer("Invalid ID. Please enter a number."); return
    target_user_id = int(message.text)
    await state.update_data(target_user_id=target_user_id)
    info_text, keyboard = await get_subscription_panel(session, target_user_id)
    await message.answer(info_text, reply_markup=keyboard, parse_mode="Markdown")
    await state.set_state(AdminFSM.manage_user_sub)

@router.callback_query(AdminFSM.manage_user_sub, F.data.startswith("sub_"))
async def handle_sub_management_callback(query: types.CallbackQuery, state: FSMContext, session: AsyncSession):
    data = await state.get_data()
    user = await database.get_or_create_user(session, data['target_user_id'])
    action = query.data.replace("sub_", "")

    if action == "toggle_active": user.sub_is_active = not user.sub_is_active
    elif action.startswith("toggle_site_"):
        site = action.replace("toggle_site_", "")
        current_sites = user.sub_allowed_sites.copy()
        current_sites[site] = not current_sites.get(site, False)
        user.sub_allowed_sites = current_sites
    # ... other actions like adding days, limits etc. would modify the user object ...

    await session.commit()
    info_text, keyboard = await get_subscription_panel(session, user.id)
    await query.message.edit_text(info_text, reply_markup=keyboard, parse_mode="Markdown")
    await query.answer("Updated!")

@router.message(AdminFSM.panel, F.text == "📝 متن ها")
async def texts_panel_command(message: types.Message, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton("ویرایش متن راهنما", callback_data="texts_edit_help")]])
    await message.answer("کدام متن را می‌خواهید ویرایش کنید؟", reply_markup=keyboard)

@router.callback_query(F.data == "texts_edit_help")
async def texts_panel_callback(query: types.CallbackQuery, state: FSMContext):
    await query.message.edit_text("لطفاً متن جدید راهنما را ارسال کنید. برای لغو /cancel را بزنید.")
    await state.set_state(AdminFSM.await_help_text)

@router.message(AdminFSM.await_help_text)
async def await_help_text_handler(message: types.Message, state: FSMContext, session: AsyncSession):
    await database.set_text(session, key="help_text", value=message.text)
    await message.answer("✅ متن راهنما با موفقیت به‌روزرسانی شد.")
    await state.set_state(AdminFSM.panel) # Return to main panel

@router.message(AdminFSM.panel, F.text == "❌ خروج از پنل")
async def admin_exit(message: types.Message, state: FSMContext):
    await message.answer("You have exited the Admin Panel.", reply_markup=types.ReplyKeyboardRemove())
    await state.clear()
