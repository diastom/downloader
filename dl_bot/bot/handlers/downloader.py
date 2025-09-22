import asyncio
import json
import logging
import urllib.parse
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import or_f
from sqlalchemy.ext.asyncio import AsyncSession

from dl_bot.tasks import download_tasks
from dl_bot.utils import helpers, database
from dl_bot.utils.decorators import cooldown

logger = logging.getLogger(__name__)
router = Router()

URL_REGEX = r'https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)'

# --- Site Configuration ---
# Maps domain to the correct helper functions and settings
SITE_CONFIG = {
    helpers.TOONILY_COM_DOMAIN: {"get_chapters": helpers.find_all_chapters_com, "needs_selenium": True, "task": "tasks.process_toonily_com"},
    helpers.TOONILY_ME_DOMAIN: {"get_chapters": helpers.mn2_get_chapters, "needs_selenium": False, "task": "tasks.process_toonily_me"},
    helpers.MANHWACLAN_DOMAIN: {"get_chapters": helpers.mc_get_chapters_and_title, "needs_selenium": False, "task": "tasks.process_manhwaclan"},
    helpers.MANGA_DISTRICT_DOMAIN: {"get_chapters": helpers.md_get_chapters_and_title, "needs_selenium": False, "task": "tasks.process_mangadistrict"},
    helpers.COMICK_DOMAIN: {"get_chapters": helpers.cm_get_info_and_chapters, "needs_selenium": True, "task": "tasks.process_comick"},
}
MANHWA_DOMAINS = SITE_CONFIG.keys()

# --- FSM States ---
class DownloadFSM(StatesGroup):
    manhwa_selecting_chapters = State()
    manhwa_awaiting_zip_option = State()
    gallery_awaiting_zip_option = State()
    yt_dlp_selecting_quality = State()

# --- Main Link Handler ---
@router.message(F.text.regexp(URL_REGEX))
@cooldown(seconds=10) # Reduced cooldown for testing
async def handle_link(message: types.Message, state: FSMContext, session: AsyncSession):
    url = message.text.strip()
    user_id = message.from_user.id
    domain = urllib.parse.urlparse(url).netloc.lower().replace('www.', '')

    is_allowed, reason = await helpers.check_subscription(session, user_id, domain)
    if not is_allowed:
        await message.answer(reason)
        return

    await database.log_download_activity(session, user_id, domain)

    if domain in MANHWA_DOMAINS:
        await handle_manhwa_link(message, state, url, domain)
    elif domain in helpers.GALLERY_DL_ZIP_SITES:
        await handle_gallery_zip_link(message, state, url)
    elif domain in helpers.GALLERY_DL_SITES:
        await message.answer(f"✅ Your request for '{domain}' has been added to the queue.")
        download_tasks.process_gallery_dl_task.delay(message.chat.id, url, create_zip=False)
    elif domain in [helpers.PORNHUB_DOMAIN, helpers.EPORNER_DOMAIN, helpers.EROME_DOMAIN]:
        await handle_yt_dlp_link(message, state, url)
    else:
        # Default to yt-dlp for any other link
        await message.answer("Unrecognized link. Attempting download with the general-purpose downloader...")
        await handle_yt_dlp_link(message, state, url, default_to_best=True)

# --- Specific Link Type Handlers ---

async def handle_manhwa_link(message: types.Message, state: FSMContext, url: str, domain: str):
    config = SITE_CONFIG[domain]
    status_msg = await message.answer(f"🔎 Analyzing link from {domain}...")

    driver = None
    try:
        if config["needs_selenium"]:
            driver = await asyncio.to_thread(helpers.setup_chrome_driver)
            if not driver: raise Exception("Could not start browser driver.")

        chapters, title = await asyncio.to_thread(config["get_chapters"], url, driver) if driver else await asyncio.to_thread(config["get_chapters"], url)

        if not chapters:
            await status_msg.edit_text("No chapters found or an error occurred.")
            return

        await state.set_state(DownloadFSM.manhwa_selecting_chapters)
        await state.update_data(
            chapters=chapters, title=title, site_task=config["task"],
            selected_indices=[], current_page=0, prefix=domain.split('.')[0]
        )

        keyboard = helpers.create_chapter_keyboard(chapters, [], 0, domain.split('.')[0])
        await status_msg.edit_text(f"✅ Found {len(chapters)} chapters for '{title}'. Please select chapters to download:", reply_markup=keyboard)

    except Exception as e:
        logger.error(f"Error handling manhwa link {url}: {e}", exc_info=True)
        await status_msg.edit_text(f"An error occurred: {e}")
    finally:
        if driver:
            driver.quit()

async def handle_gallery_zip_link(message: types.Message, state: FSMContext, url: str):
    await state.update_data(url=url)
    keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton("Yes, create ZIP file", callback_data="gdl_zip_yes")],
        [types.InlineKeyboardButton("No, send as separate files", callback_data="gdl_zip_no")]
    ])
    await message.answer("This site supports downloading as a ZIP file. Would you like to compress the files?", reply_markup=keyboard)
    await state.set_state(DownloadFSM.gallery_awaiting_zip_option)

async def handle_yt_dlp_link(message: types.Message, state: FSMContext, url: str, default_to_best: bool = False):
    status_msg = await message.answer(" extracting video info...")
    info = await asyncio.to_thread(helpers.get_full_video_info, url)
    if not info:
        await status_msg.edit_text("Error extracting video info.")
        return

    if default_to_best:
        download_tasks.download_and_upload_video_task.delay(message.chat.id, url, 'best', json.dumps(info), message.from_user.id)
        await status_msg.edit_text("✅ Your request has been added to the queue with the best available quality.")
        return

    # ... (Quality selection logic from previous implementation) ...

# --- FSM Callback Handlers ---

@router.callback_query(DownloadFSM.manhwa_selecting_chapters)
async def handle_manhwa_chapter_selection(query: types.CallbackQuery, state: FSMContext):
    """Handles pagination, selection, and download command for manhwa chapters."""
    data = await state.get_data()
    prefix = data['prefix']
    action = query.data.replace(f"{prefix}_", "")

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
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton("Yes, create ZIP", callback_data="manhwa_zip_yes")],
            [types.InlineKeyboardButton("No, send as images", callback_data="manhwa_zip_no")]
        ])
        await query.message.edit_text("Compress downloads into ZIP files?", reply_markup=keyboard)
        await state.update_data(selected_indices=data['selected_indices']) # Save final selection
        return

    await state.update_data(current_page=data['current_page'], selected_indices=data['selected_indices'])
    keyboard = helpers.create_chapter_keyboard(data['chapters'], data['selected_indices'], data['current_page'], prefix)
    await query.message.edit_reply_markup(reply_markup=keyboard)


@router.callback_query(DownloadFSM.manhwa_awaiting_zip_option, F.data.startswith("manhwa_zip_"))
async def handle_manhwa_zip_choice(query: types.CallbackQuery, state: FSMContext):
    """Dispatches the appropriate Celery task for the selected manhwa."""
    create_zip = query.data == "manhwa_zip_yes"
    data = await state.get_data()

    chapters_to_download = [data['chapters'][i] for i in sorted(data['selected_indices'])]

    await query.message.edit_text(f"✅ Request for {len(chapters_to_download)} chapters of '{data['title']}' sent to the queue.")

    # Call the single generic manhwa task with the domain as the key
    download_tasks.process_manhwa_task.delay(
        chat_id=query.message.chat.id,
        manhwa_title=data['title'],
        chapters_to_download=chapters_to_download,
        create_zip=create_zip,
        site_key=data['prefix'] # The prefix is the domain, e.g., "toonily"
    )

    await state.clear()

# ... (Other callback handlers for gallery-dl and yt-dlp) ...
