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

            # 2. فیلتر کردن و ساختن لیستی از رزولوشن‌های ویدئویی موجود
            available_resolutions = {}
            for f in formats:
                # vcodec!='none' یعنی فرمت فقط صوتی نیست و height یعنی رزولوشن دارد
                if f.get('vcodec') != 'none' and f.get('height'):
                    height = f['height']
                    # جلوگیری از نمایش کیفیت‌های تکراری
                    if height not in available_resolutions:
                         # تخمین حجم فایل برای نمایش به کاربر
                         filesize = f.get('filesize') or f.get('filesize_approx')
                         note = f"{height}p"
                         if filesize:
                             note += f" (~{filesize / (1024*1024):.2f} MB)"
                         available_resolutions[height] = note
            
            if not available_resolutions:
                print("هیچ کیفیت قابل دانلودی برای این ویدئو پیدا نشد.")
                exit()
            
            # مرتب‌سازی کیفیت‌ها از بالاترین به پایین‌ترین
            sorted_resolutions = sorted(available_resolutions.items(), key=lambda item: item[0], reverse=True)

            print("\nکیفیت‌های موجود:")
            for i, (height, note) in enumerate(sorted_resolutions):
                print(f"  {i + 1}: {note}")

            # 3. دریافت انتخاب کاربر
            choice = -1
            while choice < 1 or choice > len(sorted_resolutions):
                try:
                    raw_choice = input(f"لطفا کیفیت مورد نظر را انتخاب کنید (1-{len(sorted_resolutions)}):\n> ")
                    choice = int(raw_choice)
                except (ValueError, IndexError):
                    print("انتخاب نامعتبر است. لطفا یک عدد از لیست بالا وارد کنید.")

            selected_height = sorted_resolutions[choice - 1][0]
            
            print(f"\nعنوان ویدئو: {video_title}")
            print(f"کیفیت انتخاب شده: {selected_height}p")

            # 4. ساختن "فرمت استرینگ" برای yt-dlp و تنظیمات نهایی دانلود
            # این دستور به yt-dlp می‌گوید بهترین ویدئو با ارتفاع مشخص را با بهترین صدای ممکن ترکیب کن
            format_string = f'bestvideo[height={selected_height}]+bestaudio/best[height={selected_height}]'
            safe_title = sanitize_filename(video_title)

            ydl_opts = {
                'format': format_string,
                'outtmpl': f'{safe_title} - {selected_height}p.%(ext)s',
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

