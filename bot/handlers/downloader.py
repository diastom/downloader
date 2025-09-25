import asyncio
import json
import logging
import urllib.parse
from aiogram import Router, types, F, Bot
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlalchemy.ext.asyncio import AsyncSession

from bot.handlers.common import UserFlow, get_task_done_keyboard
from tasks import download_tasks
from utils import helpers, database
from utils.decorators import cooldown
from utils.models import PublicArchive

logger = logging.getLogger(__name__)
router = Router()

URL_REGEX = r'https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)'

# --- Site Configuration ---
SITE_CONFIG = {
    helpers.TOONILY_COM_DOMAIN: {"get_chapters": helpers.find_all_chapters_com, "needs_selenium": True},
    helpers.TOONILY_ME_DOMAIN: {"get_chapters": helpers.mn2_get_chapters, "needs_selenium": False},
    helpers.MANHWACLAN_DOMAIN: {"get_chapters": helpers.mc_get_chapters_and_title, "needs_selenium": False},
    helpers.MANGA_DISTRICT_DOMAIN: {"get_chapters": helpers.md_get_chapters_and_title, "needs_selenium": False},
    helpers.COMICK_DOMAIN: {"get_chapters": helpers.cm_get_info_and_chapters, "needs_selenium": True},
}
MANHWA_DOMAINS = SITE_CONFIG.keys()
VIDEO_DOMAINS = [helpers.PORNHUB_DOMAIN, helpers.EPORNER_DOMAIN]

# --- FSM States ---
class DownloadFSM(StatesGroup):
    manhwa_selecting_chapters = State()
    manhwa_awaiting_zip_option = State()
    gallery_awaiting_zip_option = State()
    erome_awaiting_choice = State()

# --- Main Link Handler ---
async def _process_download_link(message: types.Message, state: FSMContext, session: AsyncSession, bot: Bot):
    url = message.text.strip()
    user_id = message.from_user.id
    domain = urllib.parse.urlparse(url).netloc.lower().replace('www.', '')

    all_supported_domains = list(MANHWA_DOMAINS) + helpers.GALLERY_DL_SITES + helpers.GALLERY_DL_ZIP_SITES + [helpers.EROME_DOMAIN] + VIDEO_DOMAINS
    if domain not in all_supported_domains:
        await message.answer("This site is not currently supported for downloads.")
        return

    is_allowed, reason = await helpers.check_subscription(session, user_id, domain)
    if not is_allowed:
        await message.answer(reason)
        return

    await database.log_download_activity(session, user_id, domain)

    # --- Video duplicate check ---
    if domain in VIDEO_DOMAINS:
        url_hash = PublicArchive.create_hash(url)
        archived_item = await database.get_public_archive_item(session, url_hash)
        if archived_item:
            logger.info(f"URL {url} found in public archive. Forwarding message.")
            await message.answer("This video has been downloaded before. Forwarding it to you...")
            try:
                await bot.copy_message(chat_id=user_id, from_chat_id=archived_item.channel_id, message_id=archived_item.message_id)
                await bot.send_message(
                    chat_id=user_id,
                    text="تسک شما انجام شد ✅",
                    reply_markup=get_task_done_keyboard()
                )
                return
            except Exception as e:
                logger.error(f"Failed to forward message from archive: {e}. Proceeding with re-download.")
                await message.answer("Failed to forward from archive. Proceeding with a fresh download...")

    # --- Route to the correct handler ---
    if domain in MANHWA_DOMAINS:
        await handle_manhwa_link(message, state, url, domain)
    elif domain in helpers.GALLERY_DL_SITES or domain in helpers.GALLERY_DL_ZIP_SITES:
        await handle_gallery_dl_link(message, state, url)
    elif domain == helpers.EROME_DOMAIN:
        await handle_erome_link(message, state, url)
    elif domain in VIDEO_DOMAINS:
        await handle_yt_dlp_link(message, state, url, domain)
    else:
        await message.answer("Could not determine the correct downloader for this site.")


@router.message(StateFilter(UserFlow.downloading), F.text.regexp(URL_REGEX))
@cooldown(seconds=10)
async def handle_link(message: types.Message, state: FSMContext, session: AsyncSession, bot: Bot):
    await _process_download_link(message, state, session, bot)


@router.message(StateFilter(None, UserFlow.main_menu, UserFlow.encoding), F.text.regexp(URL_REGEX))
@cooldown(seconds=10)
async def auto_start_download(message: types.Message, state: FSMContext, session: AsyncSession, bot: Bot):
    await state.set_state(UserFlow.downloading)
    await _process_download_link(message, state, session, bot)


async def handle_yt_dlp_link(message: types.Message, state: FSMContext, url: str, domain: str):
    status_msg = await message.answer("🔎 Extracting video information...")
    info = await asyncio.to_thread(helpers.get_full_video_info, url)
    if not info:
        await status_msg.edit_text("❌ Error: Could not extract video information.")
        return
    formats = [f for f in info.get('formats', []) if f.get('vcodec') != 'none' and f.get('height')]
    if not formats:
        await status_msg.edit_text("No downloadable video qualities found.")
        return
    best_format = max(
        formats,
        key=lambda f: ((f.get('height') or 0), (f.get('tbr') or 0), (f.get('filesize') or f.get('filesize_approx') or 0))
    )
    height = best_format.get('height')
    approx_size = (best_format.get('filesize') or best_format.get('filesize_approx') or 0) / (1024 * 1024)
    format_id = best_format.get('format_id')
    if not format_id:
        await status_msg.edit_text("❌ Error: Could not determine the best quality format.")
        return
    quality_display = f"{height}p" if height else "Best available"
    size_display = f"{approx_size:.2f} MB" if approx_size else "نامشخص"
    await status_msg.edit_text(
        "🎯 بهترین کیفیت موجود انتخاب شد.\n"
        f"کیفیت خروجی: {quality_display}\n"
        f"حجم تقریبی: {size_display}\n"
        "درخواست شما به صف دانلود اضافه شد."
    )
    download_tasks.download_video_task.delay(
        chat_id=message.chat.id,
        url=url,
        selected_format=format_id,
        video_info_json=json.dumps(info),
        user_id=message.from_user.id,
        source_domain=domain,
    )
    await state.clear()

async def handle_erome_link(message: types.Message, state: FSMContext, url: str):
    status_msg = await message.answer("🔎 Analyzing Erome album, this may take a moment...")
    driver = None
    try:
        driver = await asyncio.to_thread(helpers.setup_chrome_driver)
        if not driver:
            raise Exception("Could not start browser driver.")

        title, media_urls = await asyncio.to_thread(helpers.er_get_album_media_selenium, url, driver)

        if not media_urls or (not media_urls.get('images') and not media_urls.get('videos')):
            await status_msg.edit_text("No images or videos found in this album.")
            return

        await state.set_state(DownloadFSM.erome_awaiting_choice)
        await state.update_data(
            er_title=title,
            er_media=media_urls,
            user_id=message.from_user.id
        )

        num_images = len(media_urls.get('images', []))
        num_videos = len(media_urls.get('videos', []))

        keyboard_buttons = []
        if num_images > 0:
            keyboard_buttons.append([types.InlineKeyboardButton(text=f"🖼️ Download {num_images} Images", callback_data="er_choice_images")])
        if num_videos > 0:
             keyboard_buttons.append([types.InlineKeyboardButton(text=f"🎬 Download {num_videos} Videos", callback_data="er_choice_videos")])
        if num_images > 0 and num_videos > 0:
            keyboard_buttons.append([types.InlineKeyboardButton(text="📥 Download Both", callback_data="er_choice_both")])

        await status_msg.edit_text(
            f"✅ Album '{title}' analyzed. What would you like to download?",
            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        )

    except Exception as e:
        logger.error(f"Error handling Erome link {url}: {e}", exc_info=True)
        await status_msg.edit_text(f"An error occurred: {str(e)}")
    finally:
        if driver:
            driver.quit()

async def handle_gallery_dl_link(message: types.Message, state: FSMContext, url: str):
    user_id = message.from_user.id
    await state.set_state(DownloadFSM.gallery_awaiting_zip_option)
    await state.update_data(gdl_url=url, user_id=user_id)
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="Yes, create ZIP", callback_data="gdl_zip_yes")], [types.InlineKeyboardButton(text="No, send individually", callback_data="gdl_zip_no")]])
    await message.answer("This looks like a gallery. Compress to a single ZIP?", reply_markup=keyboard)

async def handle_manhwa_link(message: types.Message, state: FSMContext, url: str, domain: str):
    config = SITE_CONFIG[domain]
    status_msg = await message.answer(f"🔎 Analyzing link from {domain}...")
    driver = None
    try:
        if config["needs_selenium"]:
            driver = await asyncio.to_thread(helpers.setup_chrome_driver)
        get_chapters_func = config["get_chapters"]
        chapters, title = await asyncio.to_thread(get_chapters_func, url, driver) if driver else await asyncio.to_thread(get_chapters_func, url)
        if not chapters:
            await status_msg.edit_text("No chapters found.")
            return
        await state.set_state(DownloadFSM.manhwa_selecting_chapters)
        await state.update_data(
            chapters=chapters,
            title=title,
            prefix=domain,
            selected_indices=[],
            current_page=0,
            user_id=message.from_user.id,
        )
        keyboard = helpers.create_chapter_keyboard(chapters, [], 0, domain)
        await status_msg.edit_text(f"✅ Found {len(chapters)} chapters for '{title}'. Select chapters:", reply_markup=keyboard)
    except Exception as e:
        logger.error(f"Error handling manhwa link {url}: {e}", exc_info=True)
        await status_msg.edit_text(f"An error occurred: {e}")
    finally:
        if driver: driver.quit()

# --- FSM Callback Handlers ---

@router.callback_query(DownloadFSM.erome_awaiting_choice, F.data.startswith("er_choice_"))
async def handle_erome_choice(query: types.CallbackQuery, state: FSMContext):
    await query.answer()
    choice = query.data.replace("er_choice_", "")
    data = await state.get_data()

    title = data.get('er_title')
    media = data.get('er_media')
    user_id = data.get('user_id')

    if not all([title, media, user_id]):
        await query.message.edit_text("Error: Download information has expired. Please send the link again.")
        await state.clear()
        return

    await query.message.edit_text(f"✅ Your request for '{title}' has been added to the queue.")

    download_tasks.process_erome_album_task.delay(
        chat_id=query.message.chat.id,
        user_id=user_id,
        album_title=title,
        media_urls=media,
        choice=choice
    )
    await state.clear()


@router.callback_query(DownloadFSM.gallery_awaiting_zip_option, F.data.startswith("gdl_zip_"))
async def handle_gallery_dl_zip_choice(query: types.CallbackQuery, state: FSMContext):
    await query.answer()
    create_zip = query.data == "gdl_zip_yes"
    data = await state.get_data()
    await query.message.edit_text(f"✅ Request for '{urllib.parse.urlparse(data['gdl_url']).netloc}' added to queue.")
    download_tasks.process_gallery_dl_task.delay(query.message.chat.id, data['gdl_url'], create_zip=create_zip, user_id=data['user_id'])
    await state.clear()

@router.callback_query(DownloadFSM.manhwa_selecting_chapters)
async def handle_manhwa_chapter_selection(query: types.CallbackQuery, state: FSMContext):
    await query.answer()
    data = await state.get_data()
    prefix = data['prefix']
    action = query.data[len(prefix) + 1:]
    if action.startswith("toggle_"):
        index = int(action.split('_')[-1])
        if index in data['selected_indices']: data['selected_indices'].remove(index)
        else: data['selected_indices'].append(index)
    elif action.startswith("page_"):
        data['current_page'] = int(action.split('_')[-1])
    elif action == "select_all":
        data['selected_indices'] = list(range(len(data['chapters'])))
    elif action == "deselect_all":
        data['selected_indices'] = []
    elif action == "start_download":
        if not data['selected_indices']:
            await query.answer("Please select at least one chapter.", show_alert=True)
            return
        await state.set_state(DownloadFSM.manhwa_awaiting_zip_option)
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[[types.InlineKeyboardButton(text="Yes, create ZIP", callback_data="manhwa_zip_yes")], [types.InlineKeyboardButton(text="No, send as files", callback_data="manhwa_zip_no")]])
        await query.message.edit_text("Compress downloads into ZIP files?", reply_markup=keyboard)
        return
    await state.update_data(current_page=data['current_page'], selected_indices=data['selected_indices'])
    keyboard = helpers.create_chapter_keyboard(data['chapters'], data['selected_indices'], data['current_page'], prefix)
    await query.message.edit_reply_markup(reply_markup=keyboard)

@router.callback_query(DownloadFSM.manhwa_awaiting_zip_option, F.data.startswith("manhwa_zip_"))
async def handle_manhwa_zip_choice(query: types.CallbackQuery, state: FSMContext):
    await query.answer()
    create_zip = query.data == "manhwa_zip_yes"
    data = await state.get_data()
    chapters_to_download = [data['chapters'][i] for i in sorted(data['selected_indices'])]
    await query.message.edit_text(f"✅ Request for {len(chapters_to_download)} chapters of '{data['title']}' sent to queue.")
    download_tasks.process_manhwa_task.delay(
        chat_id=query.message.chat.id,
        manhwa_title=data['title'],
        chapters_to_download=chapters_to_download,
        create_zip=create_zip,
        site_key=data['prefix'],
        user_id=data['user_id'],
    )
    await state.clear()