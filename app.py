# -*- coding: utf-8 -*-
import os
from flask import Flask, request, make_response
import yt_dlp
from urllib.parse import quote

app = Flask(__name__)

# --- הגדרות מערכת (ערוך כאן) ---
ACCESS_MODE = "whitelist"  # אפשרויות: "whitelist" או "blacklist"
TARGET_PHONE = "0534133753" # המספר שעליו תתבצע הבדיקה
FORBIDDEN_WORDS = ["מילה_אסורה1", "זמר_לא_מתאים", "תוכן_רע"] # מילים לסינון

# --- פונקציות עזר למניעת חסימות ---
def get_yt_options(is_search=True):
    opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'bestaudio/best',
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
        'nocheckcertificate': True,
        'geo_bypass': True,
        'extract_flat': is_search,
    }
    
    if os.path.exists('cookies.txt'):
        opts['cookiefile'] = 'cookies.txt'

    # תוספת לשיפור יציבות
    opts['force_ipv4'] = True
    
    return opts


def is_filtered(text):
    if not text: return False
    return any(word.lower() in text.lower() for word in FORBIDDEN_WORDS)


# פונקציה חדשה – מוסיפה פרמטרים ל target כדי שלא יאבדו
def build_target(base, params: dict):
    query = "&".join([f"{k}={quote(str(v))}" for k,v in params.items()])
    return f"{base}&{query}" if "?" in base else f"{base}?{query}"


@app.route('/youtube', methods=['GET', 'POST'])
def main_logic():

    # ניקוי מספר הטלפון מרווחים מיותרים
    phone = request.args.get("ApiPhone", "").strip()
    step = request.args.get("step", "menu")
    res = ""

    print(f"DEBUG: Phone received: '{phone}' | Target expected: '{TARGET_PHONE}'")
    print(f"DEBUG: Step: {step}")
    print("DEBUG args:", dict(request.args))

    # --- 1. אבטחת גישה משופרת ---
    if ACCESS_MODE == "whitelist" and phone and phone != TARGET_PHONE.strip():
        res = "id_list_message=t-אין לך הרשאה&goto_main=/"
    
    elif ACCESS_MODE == "blacklist" and phone == TARGET_PHONE.strip():
        res = "id_list_message=t-הגישה למספרך נחסמה&goto_main=/"
        
    # --- 2. תפריט ראשי ---
    elif step == "menu":
        res = "read=t-לשירים חדשים הקש 1. לחיפוש קולי מתקדם הקש 2.=selection,1,1,1,7,st-javascript,y,no&target=/youtube?step=handle_choice"
        
    # --- 3. טיפול בבחירה ---
    elif step == "handle_choice":

        selection = request.args.get("selection")

        print("DEBUG selection:", selection)

        if selection == "1":
            res = f"target=/youtube?step=search&query={quote('שירים חדשים 2024')}"

        elif selection == "2":
            res = "read=t-נא אמרו את שם השיר או הזמר=query,1,1,1,7,st-voice,y,no&target=/youtube?step=search"

        else:
            res = "goto_main=/"

    # --- 4. ביצוע חיפוש וסינון תוצאות ---
    elif step == "search":

        query = request.args.get("query", "")

        print("DEBUG search query:", query)

        with yt_dlp.YoutubeDL(get_yt_options(is_search=True)) as ydl:
            try:

                info = ydl.extract_info(f"ytsearch20:{query}", download=False)

                entries = info.get('entries', [])

                valid_results = [
                    e for e in entries
                    if not is_filtered(e.get('title')) and not is_filtered(e.get('uploader'))
                ]

                if not valid_results:

                    res = "id_list_message=t-לא נמצאו תוצאות מתאימות לחיפוש זה&goto_main=/"

                else:

                    first_video = valid_results[0]

                    first_id = first_video['id']
                    first_title = first_video['title']

                    others = ",".join([v['id'] for v in valid_results[1:10]])

                    print("DEBUG first video:", first_id)

                    target = build_target(
                        "/youtube?step=play_logic",
                        {
                            "first_id": first_id,
                            "others": others
                        }
                    )

                    res = (
                        f"read=t-נמצא: {first_title}. להשמעה הקש 1. לשאר התוצאות הקש 2.=choice,1,1,1,7,st-javascript,y,no"
                        f"&target={target}"
                    )

            except Exception as e:

                print("YOUTUBE SEARCH ERROR:", e)

                res = "id_list_message=t-שגיאה בחיפוש. נסה שנית מאוחר יותר&goto_main=/"

    # --- 5. לוגיקת השמעה ---
    elif step == "play_logic":

        choice = request.args.get("choice")

        first_id = request.args.get("first_id")
        others = request.args.get("others", "")

        print("DEBUG play_logic:", choice, first_id, others)

        if choice == "1":

            video_id = request.args.get("first_id")

            res = f"target=/youtube?step=get_link&vid={video_id}"

        else:

            others = request.args.get("others", "").split(",")

            if others and others[0]:

                res = f"target=/youtube?step=get_link&vid={others[0]}"

            else:

                res = "id_list_message=t-אין תוצאות נוספות&goto_main=/"

    # --- 6. חילוץ לינק ישיר להשמעה ---
    elif step == "get_link":

        video_id = request.args.get("vid")

        print("DEBUG play video:", video_id)

        with yt_dlp.YoutubeDL(get_yt_options(is_search=False)) as ydl:
            try:

                info = ydl.extract_info(
                    f"https://www.youtube.com/watch?v={video_id}",
                    download=False
                )

                url = info['url']

                res = f"play_url={url}"

            except Exception as e:

                print("PLAY ERROR:", e)

                res = "id_list_message=t-שגיאה בניגון השיר&goto_main=/"

    else:

        res = "goto_main=/"

    # --- התיקון הקריטי למניעת הניתוק בימות המשיח ---
    response = make_response(res)
    response.headers['Content-Type'] = 'text/plain; charset=utf-8'

    return response


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
