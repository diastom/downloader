# Import کردن کتابخانه‌های مورد نیاز
import yt_dlp        # برای استخراج و دانلود ویدئو
import os            # برای کار با فایل‌ها و مسیرها
import re

def sanitize_filename(filename):
    """
    کاراکترهای غیرمجاز را از نام فایل حذف می‌کند تا برای ذخیره‌سازی مناسب باشد.
    """
    return re.sub(r'[\\/*?:"<>|]', "", filename)

# --- بخش اصلی اسکریپت ---
if __name__ == "__main__":
    video_url = input("لطفا لینک ویدئو را وارد کرده و Enter را بزنید:\n> ")

    if not video_url:
        print("هیچ لینکی وارد نشده است. برنامه بسته می‌شود.")
    else:
        try:
            # 1. استخراج اطلاعات ویدئو و لیست کامل فرمت‌ها بدون دانلود
            print("در حال استخراج اطلاعات ویدئو و کیفیت‌های موجود...")
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info_dict = ydl.extract_info(video_url, download=False)

            video_title = info_dict.get('title', 'video')
            formats = info_dict.get('formats', [])

            # 2. انتخاب خودکار بهترین کیفیت ممکن
            candidates = [f for f in formats if f.get('vcodec') != 'none' and f.get('height')]
            if not candidates:
                print("هیچ کیفیت قابل دانلودی برای این ویدئو پیدا نشد.")
                exit()

            av_candidates = [f for f in candidates if f.get('acodec') and f.get('acodec') != 'none']
            selection_pool = av_candidates if av_candidates else candidates
            best_format = max(
                selection_pool,
                key=lambda f: ((f.get('height') or 0), (f.get('tbr') or 0), (f.get('filesize') or f.get('filesize_approx') or 0))
            )

            height = best_format.get('height')
            approx_size = best_format.get('filesize') or best_format.get('filesize_approx')
            if approx_size:
                approx_size /= (1024 * 1024)

            if best_format in av_candidates and best_format.get('format_id'):
                format_string = best_format['format_id']
            elif height:
                format_string = f'bestvideo[height={height}]+bestaudio/best'
            else:
                format_string = 'bestvideo+bestaudio/best'

            print(f"\nعنوان ویدئو: {video_title}")
            if height:
                print(f"کیفیت انتخاب شده: {height}p")
            if approx_size:
                print(f"حجم تقریبی: {approx_size:.2f} مگابایت")

            safe_title = sanitize_filename(video_title)

            ydl_opts = {
                'format': format_string,
                'outtmpl': f'{safe_title}.%(ext)s' if not height else f'{safe_title} - {height}p.%(ext)s',
                'merge_output_format': 'mp4',
            }

            # 5. شروع فرآیند دانلود کامل با yt-dlp
            # خود کتابخانه نوار پیشرفت و اطلاعات دانلود را نمایش می‌دهد
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])
            
            print("\nدانلود با موفقیت به پایان رسید.")

        except yt_dlp.utils.DownloadError as e:
            # این خطاها معمولا واضح هستند و خود yt-dlp آنها را نمایش می‌دهد
            print(f"\nخطا در هنگام پردازش لینک: {e}")
        except Exception as e:
            print(f"\nیک خطای پیش‌بینی نشده رخ داد: {e}")

