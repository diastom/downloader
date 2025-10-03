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

SUPPORTED_SITES = [site for category in ALL_SUPPORTED_SITES.values() for site in category]

# --- FSM States ---
class AdminFSM(StatesGroup):
    panel = State()
    await_broadcast = State()
    await_sub_user_id = State()
    manage_user_sub = State()
    await_help_text = State()
    sales_menu = State()
    await_plan_name = State()
    await_plan_sites = State()
    await_plan_features = State()
    await_plan_duration = State()
    await_plan_download_limit = State()
    await_plan_encode_limit = State()
    await_plan_price = State()
    await_plan_description = State()
    await_wallet_address = State()
    await_banner_photo = State()

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


def _normalize_allowed_sites(sites: list[str] | set[str]) -> list[str]:
    selected = {site for site in sites if site in SUPPORTED_SITES}
    return [site for site in SUPPORTED_SITES if site in selected]


def _format_allowed_sites_lines(sites: list[str] | None) -> list[str]:
    normalized = _normalize_allowed_sites(sites or [])
    return normalized or ["هیچ سایتی فعال نشده است."]


def _format_feature_summary(allow_thumbnail: bool, allow_watermark: bool) -> str:
    features = []
    if allow_thumbnail:
        features.append("تامبنیل")
    if allow_watermark:
        features.append("واترمارک")
    return "، ".join(features) if features else "هیچ‌کدام"


def _build_site_selection_text(selected_sites: list[str]) -> str:
    lines = ["سایت‌های مجاز برای این پلن را انتخاب کنید.", "", "سایت‌های انتخاب‌شده:"]
    lines.extend(_format_allowed_sites_lines(selected_sites))
    lines.append("")
    lines.append("با دکمه‌ها می‌توانید دسترسی هر سایت را تغییر دهید و سپس گزینه «ادامه» را بزنید.")
    return "\n".join(lines)


def _build_site_selection_keyboard(selected_sites: list[str]) -> InlineKeyboardMarkup:
    selected = set(_normalize_allowed_sites(selected_sites))
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for site in SUPPORTED_SITES:
        status = "✅" if site in selected else "❌"
        row.append(InlineKeyboardButton(text=f"{status} {site}", callback_data=f"sales_plan_site_toggle:{site}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append([
        InlineKeyboardButton(text="انتخاب همه", callback_data="sales_plan_sites_select_all"),
        InlineKeyboardButton(text="حذف همه", callback_data="sales_plan_sites_clear")
    ])
    rows.append([InlineKeyboardButton(text="ادامه ▶️", callback_data="sales_plan_sites_done")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _build_feature_selection_text(allow_thumbnail: bool, allow_watermark: bool) -> str:
    lines = ["امکانات این پلن را مشخص کنید:",
             f"تامبنیل: {'فعال' if allow_thumbnail else 'غیرفعال'}",
             f"واترمارک: {'فعال' if allow_watermark else 'غیرفعال'}",
             "",
             "پس از اعمال تغییرات روی «ادامه» بزنید."]
    return "\n".join(lines)


def _build_feature_selection_keyboard(allow_thumbnail: bool, allow_watermark: bool) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"{'✅' if allow_thumbnail else '❌'} تامبنیل", callback_data="sales_plan_feature_toggle:thumbnail"),
            InlineKeyboardButton(text=f"{'✅' if allow_watermark else '❌'} واترمارک", callback_data="sales_plan_feature_toggle:watermark"),
        ],
        [InlineKeyboardButton(text="ادامه ▶️", callback_data="sales_plan_features_done")]
    ])


def _get_site_selection_payload(selected_sites: list[str]) -> tuple[str, InlineKeyboardMarkup]:
    return _build_site_selection_text(selected_sites), _build_site_selection_keyboard(selected_sites)


def _get_feature_selection_payload(allow_thumbnail: bool, allow_watermark: bool) -> tuple[str, InlineKeyboardMarkup]:
    return _build_feature_selection_text(allow_thumbnail, allow_watermark), _build_feature_selection_keyboard(allow_thumbnail, allow_watermark)


def _format_limit_value(value: int) -> str:
    return "نامحدود" if value is None or value < 0 else f"{value}"


async def build_subscription_overview(session: AsyncSession) -> tuple[str, InlineKeyboardMarkup]:
    plans = await database.get_subscription_plans(session, include_inactive=True)
    if not plans:
        text = "هنوز هیچ اشتراکی تعریف نشده است."
    else:
        lines = ["انواع اشتراک‌ها:"]
        for idx, plan in enumerate(plans, start=1):
            site_lines = "\n".join(_format_allowed_sites_lines(getattr(plan, 'allowed_sites', [])))
            feature_summary = _format_feature_summary(getattr(plan, 'allow_thumbnail', False), getattr(plan, 'allow_watermark', False))
            plan_text = (
                f"\n{idx}. {plan.name}\n"
                f"مدت اشتراک: {plan.duration_days} روز\n"
                f"سقف دانلود روزانه: {_format_limit_value(plan.download_limit_per_day)}\n"
                f"سقف ویرایش ویدئو روزانه: {_format_limit_value(plan.encode_limit_per_day)}\n"
                f"قیمت: {plan.price_toman:,} تومان\n"
                f"سایت‌های فعال:\n{site_lines}\n"
                f"امکانات: {feature_summary}"
            )
            lines.append(plan_text)
            if plan.description:
                lines.append(f"توضیحات: {plan.description}")
        text = "\n".join(lines)

    banner_file_id = await database.get_subscription_banner_file_id(session)
    banner_status = "تنظیم شده ✅" if banner_file_id else "تنظیم نشده ❌"
    text = f"{text}\n\nبنر فعلی: {banner_status}"

    buttons = [[InlineKeyboardButton(text="➕ افزودن نوع جدید اشتراک", callback_data="sales_add_plan")]]
    if plans:
        buttons.append([InlineKeyboardButton(text="🗑 حذف نوع اشتراک", callback_data="sales_delete_plan")])
    buttons.append([InlineKeyboardButton(text="🖼 تنظیم عکس بنر", callback_data="sales_set_banner")])
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
    await state.set_state(AdminFSM.panel)
    await message.answer("Welcome to the Admin Panel.", reply_markup=get_admin_panel_keyboard())


async def _return_to_panel(state: FSMContext) -> None:
    """Helper to ensure the FSM is returned to the main panel state."""
    await state.set_state(AdminFSM.panel)

@router.message(F.text == "📊 آمار")
async def show_stats(message: types.Message, state: FSMContext, session: AsyncSession):
    await _return_to_panel(state)
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

@router.message(F.text == "⚙️ مدیریت اشتراک")
async def ask_for_user_id(message: types.Message, state: FSMContext):
    await state.set_state(AdminFSM.await_sub_user_id)
    await message.answer("Please enter the User ID (UID) to manage:")


@router.message(F.text == "تنظیمات فروش")
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


@router.callback_query(F.data == "sales_set_banner")
async def sales_set_banner(query: CallbackQuery, state: FSMContext):
    await query.answer()
    await state.set_state(AdminFSM.await_banner_photo)
    await query.message.answer(
        "لطفاً تصویر بنر جدید اشتراک‌ها را ارسال کنید. برای حذف بنر فعلی عبارت «حذف» و برای لغو «لغو» را ارسال نمایید.",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(AdminFSM.await_banner_photo)
async def sales_receive_banner(message: types.Message, state: FSMContext, session: AsyncSession):
    text = (message.text or "").strip()
    lower_text = text.lower()

    if message.photo:
        file_id = message.photo[-1].file_id
        await database.set_subscription_banner_file_id(session, file_id)
        response = "عکس بنر با موفقیت ذخیره شد."
    elif lower_text in {"لغو", "انصراف", "/cancel", "cancel"}:
        response = "تنظیم عکس بنر لغو شد."
        await state.set_state(AdminFSM.sales_menu)
        await message.answer(response, reply_markup=get_sales_keyboard())
        overview_text, keyboard = await build_subscription_overview(session)
        await message.answer(overview_text, reply_markup=keyboard)
        return
    elif lower_text in {"حذف", "پاک کردن", "remove", "delete"}:
        await database.set_subscription_banner_file_id(session, None)
        response = "عکس بنر حذف شد."
    else:
        await message.answer(
            "لطفاً یک تصویر معتبر ارسال کنید یا برای حذف «حذف» و برای انصراف «لغو» را ارسال نمایید."
        )
        return

    await state.set_state(AdminFSM.sales_menu)
    await message.answer(response, reply_markup=get_sales_keyboard())
    overview_text, keyboard = await build_subscription_overview(session)
    await message.answer(overview_text, reply_markup=keyboard)


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
    plan = {"name": name, "allowed_sites": [], "allow_thumbnail": False, "allow_watermark": False}
    await state.update_data(new_plan=plan)
    await state.set_state(AdminFSM.await_plan_sites)
    text, keyboard = _get_site_selection_payload(plan["allowed_sites"])
    await message.answer(text, reply_markup=keyboard)


@router.callback_query(AdminFSM.await_plan_sites, F.data.startswith("sales_plan_site_toggle:"))
async def sales_plan_toggle_site(query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    plan = data.get("new_plan", {})
    if not plan:
        await query.answer("اطلاعات پلن یافت نشد.", show_alert=True)
        return
    site = query.data.replace("sales_plan_site_toggle:", "")
    if site not in SUPPORTED_SITES:
        await query.answer("سایت نامعتبر است.", show_alert=True)
        return
    allowed = set(_normalize_allowed_sites(plan.get("allowed_sites", [])))
    if site in allowed:
        allowed.remove(site)
    else:
        allowed.add(site)
    plan["allowed_sites"] = [s for s in SUPPORTED_SITES if s in allowed]
    await state.update_data(new_plan=plan)
    text, keyboard = _get_site_selection_payload(plan["allowed_sites"])
    await query.message.edit_text(text, reply_markup=keyboard)
    await query.answer("دسترسی سایت به‌روزرسانی شد.")


@router.callback_query(AdminFSM.await_plan_sites, F.data == "sales_plan_sites_select_all")
async def sales_plan_sites_select_all(query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    plan = data.get("new_plan", {})
    if not plan:
        await query.answer("اطلاعات پلن یافت نشد.", show_alert=True)
        return
    plan["allowed_sites"] = list(SUPPORTED_SITES)
    await state.update_data(new_plan=plan)
    text, keyboard = _get_site_selection_payload(plan["allowed_sites"])
    await query.message.edit_text(text, reply_markup=keyboard)
    await query.answer("همه سایت‌ها فعال شدند.")


@router.callback_query(AdminFSM.await_plan_sites, F.data == "sales_plan_sites_clear")
async def sales_plan_sites_clear(query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    plan = data.get("new_plan", {})
    if not plan:
        await query.answer("اطلاعات پلن یافت نشد.", show_alert=True)
        return
    plan["allowed_sites"] = []
    await state.update_data(new_plan=plan)
    text, keyboard = _get_site_selection_payload(plan["allowed_sites"])
    await query.message.edit_text(text, reply_markup=keyboard)
    await query.answer("تمام سایت‌ها غیرفعال شدند.")


@router.callback_query(AdminFSM.await_plan_sites, F.data == "sales_plan_sites_done")
async def sales_plan_sites_done(query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    plan = data.get("new_plan", {})
    if not plan:
        await query.answer("اطلاعات پلن یافت نشد.", show_alert=True)
        return
    await state.update_data(new_plan=plan)
    await state.set_state(AdminFSM.await_plan_features)
    text, keyboard = _get_feature_selection_payload(plan.get("allow_thumbnail", False), plan.get("allow_watermark", False))
    await query.message.edit_text(text, reply_markup=keyboard)
    await query.answer()


@router.callback_query(AdminFSM.await_plan_features, F.data.startswith("sales_plan_feature_toggle:"))
async def sales_plan_feature_toggle(query: CallbackQuery, state: FSMContext):
    feature = query.data.replace("sales_plan_feature_toggle:", "")
    data = await state.get_data()
    plan = data.get("new_plan", {})
    if not plan:
        await query.answer("اطلاعات پلن یافت نشد.", show_alert=True)
        return
    if feature == "thumbnail":
        plan["allow_thumbnail"] = not plan.get("allow_thumbnail", False)
        response = "وضعیت تامبنیل تغییر کرد."
    elif feature == "watermark":
        plan["allow_watermark"] = not plan.get("allow_watermark", False)
        response = "وضعیت واترمارک تغییر کرد."
    else:
        await query.answer("گزینه نامعتبر است.", show_alert=True)
        return
    await state.update_data(new_plan=plan)
    text, keyboard = _get_feature_selection_payload(plan.get("allow_thumbnail", False), plan.get("allow_watermark", False))
    await query.message.edit_text(text, reply_markup=keyboard)
    await query.answer(response)


@router.callback_query(AdminFSM.await_plan_features, F.data == "sales_plan_features_done")
async def sales_plan_features_done(query: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    plan = data.get("new_plan", {})
    if not plan:
        await query.answer("اطلاعات پلن یافت نشد.", show_alert=True)
        return
    await state.update_data(new_plan=plan)
    await state.set_state(AdminFSM.await_plan_duration)
    await query.message.edit_text("مدت اشتراک را به تعداد روز وارد کنید:")
    await query.answer("لطفاً مدت اشتراک را وارد کنید.")


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
    await message.answer("سقف ویرایش ویدئو روزانه را وارد کنید (برای نامحدود عدد -1 را ارسال کنید):")
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

@router.message(F.text == "📢 همگانی")
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

@router.message(F.text == "📝 متن ها")
async def texts_panel_command(message: types.Message, state: FSMContext):
    await _return_to_panel(state)
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
@router.message(F.text == "❌ خروج از پنل")
async def admin_exit(message: types.Message, state: FSMContext, session: AsyncSession):
    """Handles exiting the admin panel and shows the main user panel."""
    await message.answer("You have exited the Admin Panel.", reply_markup=ReplyKeyboardRemove())
    await state.clear()
    # Call the start handler to show the user panel
    await handle_start(message, session)
# --- END OF CORRECTION ---

