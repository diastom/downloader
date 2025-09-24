import asyncio
import json
import logging
import urllib.parse
from aiogram import Router, types, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.common import UserFlow, get_main_menu_keyboard
from tasks import download_tasks
from utils import helpers, database
from utils.decorators import cooldown
from utils.models import PublicArchive

logger = logging.getLogger(__name__)
router = Router()

URL_REGEX = r'https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)'
SUPPORTED_VIDEO_DOMAINS = [helpers.PORNHUB_DOMAIN, helpers.EPORNER_DOMAIN] # Add other yt-dlp sites here

# --- FSM States for Download Flow ---
class DownloadFSM(StatesGroup):
    yt_dlp_selecting_quality = State()

# --- Main Link Handler for Download Flow ---
@router.message(UserFlow.downloading, F.text.regexp(URL_REGEX))
@cooldown(seconds=5)
async def handle_link(message: types.Message, state: FSMContext, session: AsyncSession, bot: Bot):
    url = message.text.strip()
    user_id = message.from_user.id
    domain = urllib.parse.urlparse(url).netloc.lower().replace('www.', '')

    # Check if the domain is a supported video domain
    if domain not in SUPPORTED_VIDEO_DOMAINS:
        await message.answer(
            "این سایت در حال حاضر برای دانلود ویدیو پشتیبانی نمی‌شود. لطفاً یک لینک از سایت‌های پشتیبانی شده ارسال کنید.",
            reply_markup=get_main_menu_keyboard()
        )
        await state.set_state(UserFlow.main_menu)
        return

    # --- Check Public Archive ---
    url_hash = PublicArchive.create_hash(url)
    archived_item = await database.get_public_archive_item(session, url_hash)
    if archived_item:
        logger.info(f"URL {url} found in public archive. Forwarding message.")
        await message.answer("این ویدیو قبلاً دانلود شده است. در حال ارسال برای شما...")
        try:
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=archived_item.channel_id,
                message_id=archived_item.message_id
            )
            await message.answer("✅ ویدیو ارسال شد.", reply_markup=get_main_menu_keyboard())
            await state.set_state(UserFlow.main_menu)
            return # CRITICAL FIX: Ensure we exit after successful forward.
        except Exception as e:
            logger.error(f"Failed to forward message from archive: {e}. Proceeding with re-download.")
            await message.answer("خطایی در ارسال از آرشیو رخ داد. با این حال، ما دانلود مجدد را برای شما شروع می‌کنیم...")

    # --- Proceed with new download ---
    is_allowed, reason = await helpers.check_subscription(session, user_id, domain)
    if not is_allowed:
        await message.answer(reason)
        return

    await database.log_download_activity(session, user_id, domain)
    await handle_yt_dlp_link(message, state, url)


async def handle_yt_dlp_link(message: types.Message, state: FSMContext, url: str):
    """
    Handles video links, extracts quality formats, and presents them to the user.
    """
    status_msg = await message.answer("🔎 در حال استخراج اطلاعات ویدیو...")

    try:
        info = await asyncio.to_thread(helpers.get_full_video_info, url)

        if not info:
            await status_msg.edit_text("❌ خطا: اطلاعات ویدیو قابل استخراج نیست. لینک ممکن است خراب، پشتیبانی نشده یا نیازمند کوکی باشد.")
            return

        formats = [f for f in info.get('formats', []) if f.get('vcodec') != 'none' and f.get('height')]
        if not formats:
            await status_msg.edit_text("هیچ کیفیت قابل دانلودی برای این ویدیو یافت نشد.")
            return

        best_formats = {}
        for f in formats:
            h = f.get('height')
            if h:
                current_tbr = f.get('tbr') or 0
                if h not in best_formats or current_tbr > (best_formats[h].get('tbr') or 0):
                    best_formats[h] = f

        await state.set_state(DownloadFSM.yt_dlp_selecting_quality)
        await state.update_data(
            yt_info=info,
            yt_url=url,
            user_id=message.from_user.id
        )

        keyboard_buttons = []
        for h, f in sorted(best_formats.items(), reverse=True):
            size_mb = (f.get('filesize') or f.get('filesize_approx') or 0) / (1024*1024)
            keyboard_buttons.append([
                types.InlineKeyboardButton(
                    text=f"{h}p ({size_mb:.2f} MB)",
                    callback_data=f"yt_{f['format_id']}"
                )
            ])
        keyboard_buttons.append([types.InlineKeyboardButton(text="بهترین کیفیت (خودکار)", callback_data='yt_best')])

        await status_msg.edit_text(
            f"✅ کیفیت‌های موجود برای '{info.get('title', 'video')}':",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        )
    except Exception as e:
        logger.error(f"Error in handle_yt_dlp_link: {e}", exc_info=True)
        await status_msg.edit_text(f"❌ خطای ناشناخته‌ای در پردازش لینک شما رخ داد: {e}")
        await state.set_state(UserFlow.main_menu)


@router.callback_query(DownloadFSM.yt_dlp_selecting_quality, F.data.startswith("yt_"))
async def handle_yt_dlp_quality_choice(query: types.CallbackQuery, state: FSMContext):
    """Processes the user's quality selection and starts the download task."""
    await query.answer()
    selected_format = query.data.split('_', 1)[1]
    data = await state.get_data()

    info = data.get('yt_info')
    url = data.get('yt_url')
    user_id = data.get('user_id')

    if not all([info, url, user_id]):
        await query.message.edit_text("خطا: اطلاعات دانلود منقضی شده است. لطفاً دوباره لینک را ارسال کنید.", reply_markup=get_main_menu_keyboard())
        await state.set_state(UserFlow.main_menu)
        return

    await query.message.edit_text(f"✅ درخواست شما برای '{info.get('title', 'video')}' به صف دانلود اضافه شد.")

    # This is the new, simplified download task
    download_tasks.download_video_task.delay(
        chat_id=query.message.chat.id,
        url=url,
        selected_format=selected_format,
        video_info_json=json.dumps(info),
        user_id=user_id
    )
    # Return user to the main menu after starting the download
    await state.set_state(UserFlow.main_menu)