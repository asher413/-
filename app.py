import os
from flask import Flask, request
import yt_dlp

app = Flask(__name__)

# --- הגדרות מערכת (ערוך כאן) ---
ACCESS_MODE = "whitelist"  # אפשרויות: "whitelist" (רק המספר המצוין יורשה) או "blacklist" (כולם יורשו חוץ מהמספר המצוין)
TARGET_PHONE = "0501234567" # המספר שעליו תתבצע הבדיקה
FORBIDDEN_WORDS = ["מילה_אסורה1", "זמר_לא_מתאים", "תוכן_רע"] # מילים לסינון בכותרת ובשם הערוץ

# --- פונקציות עזר למניעת חסימות ---
def get_yt_options(is_search=True):
    opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'bestaudio/best',
        # User-Agent עדכני כדי להיראות כמו דפדפן אמיתי
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'nocheckcertificate': True,
        'geo_bypass': True,
        'extract_flat': is_search, # בחיפוש אנחנו רק רוצים רשימה, לא לינק ישיר
    }
    
    # שימוש בקוקיז אם הקובץ קיים (קריטי למניעת חסימות)
    if os.path.exists('cookies.txt'):
        opts['cookiefile'] = 'cookies.txt'
    
    return opts

def is_filtered(text):
    """בודק אם הטקסט מכיל מילים אסורות"""
    if not text: return False
    return any(word.lower() in text.lower() for word in FORBIDDEN_WORDS)

@app.route('/youtube', methods=['GET', 'POST'])
def main_logic():
    phone = request.args.get("ApiPhone", "")
    step = request.args.get("step", "menu")

    # --- 1. אבטחת גישה (חסימה/אישור מספר) ---
    if ACCESS_MODE == "whitelist" and phone != TARGET_PHONE:
        return "id_list_message=t-אין לך הרשאה לגשת לשירות זה&goto_main=/"
    if ACCESS_MODE == "blacklist" and phone == TARGET_PHONE:
        return "id_list_message=t-הגישה למספרך נחסמה&goto_main=/"

    # --- 2. תפריט ראשי ---
    if step == "menu":
        return ("read=t-לשירים חדשים הקש 1. לחיפוש קולי מתקדם הקש 2.=selection,1,1,1,7,st-javascript,y,no"
                "&target=/youtube?step=handle_choice")

    # --- 3. טיפול בבחירה (שירים חדשים או חיפוש) ---
    if step == "handle_choice":
        selection = request.args.get("selection")
        if selection == "1":
            return f"target=/youtube?step=search&query=שירים חדשים 2024" # חיפוש אוטומטי
        elif selection == "2":
            return "read=t-נא אמרו את שם השיר או הזמר=query,1,1,1,7,st-voice,y,no&target=/youtube?step=search"

    # --- 4. ביצוע חיפוש וסינון תוצאות ---
    if step == "search":
        query = request.args.get("query", "")
        with yt_dlp.YoutubeDL(get_yt_options(is_search=True)) as ydl:
            try:
                # חיפוש של 20 תוצאות
                info = ydl.extract_info(f"ytsearch20:{query}", download=False)
                entries = info.get('entries', [])
                
                # סינון לפי מילים אסורות
                valid_results = [e for e in entries if not is_filtered(e.get('title')) and not is_filtered(e.get('uploader'))]
                
                if not valid_results:
                    return "id_list_message=t-לא נמצאו תוצאות מתאימות לחיפוש זה&goto_main=/"

                # לקיחת התוצאה הראשונה
                first_video = valid_results[0]
                first_id = first_video['id']
                first_title = first_video['title']
                
                # העברת שאר התוצאות כפרמטר (מוגבל באורך, אז נעביר רק את ה-ID שלהן)
                others = ",".join([v['id'] for v in valid_results[1:10]]) # שולח עד 9 תוצאות נוספות
                
                return (f"read=t-נמצא: {first_title}. להשמעה הקש 1. לשאר התוצאות הקש 2.=choice,1,1,1,7,st-javascript,y,no"
                        f"&first_id={first_id}&others={others}&target=/youtube?step=play_logic")
            except Exception:
                return "id_list_message=t-שגיאה בחיפוש. נסה שנית מאוחר יותר&goto_main=/"

    # --- 5. לוגיקת השמעה (ראשונה או רשימה) ---
    if step == "play_logic":
        choice = request.args.get("choice")
        if choice == "1":
            video_id = request.args.get("first_id")
            return f"target=/youtube?step=get_link&vid={video_id}"
        else:
            # כאן אפשר להוסיף לוגיקה שתקריא את שאר התוצאות. כרגע זה פשוט מפעיל את השנייה ברשימה לשם הפשטות.
            others = request.args.get("others", "").split(",")
            if others and others[0]:
                return f"target=/youtube?step=get_link&vid={others[0]}"
            return "id_list_message=t-אין תוצאות נוספות&goto_main=/"

    # --- 6. חילוץ לינק ישיר להשמעה ---
    if step == "get_link":
        video_id = request.args.get("vid")
        with yt_dlp.YoutubeDL(get_yt_options(is_search=False)) as ydl:
            try:
                info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
                url = info['url']
                return f"play_url={url}"
            except:
                return "id_list_message=t-שגיאה בניגון השיר&goto_main=/"

    return "goto_main=/"

if __name__ == '__main__':
    # התאמה אוטומטית לפורט של Render
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
