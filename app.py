import os
import time
import logging
from flask import Flask, request, make_response
import yt_dlp

# הגדרת לוגים
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- הגדרות מערכת ---
ACCESS_MODE = "whitelist" 
TARGET_PHONE = "0534133753"
FORBIDDEN_WORDS = [] 

# ניהול סשנים
CALL_SESSIONS = {}

# --- תיקון: דף הבית למניעת 404 ---
@app.route('/')
def health_check():
    return "OK", 200

# --- פונקציות עזר ---

def get_yt_options(is_search=True):
    opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'bestaudio/best',
        'nocheckcertificate': True,
        'geo_bypass': True,
        'extract_flat': is_search,
        'force_ipv4': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    }
    if is_search:
        opts['playlist_items'] = '1-10'
    return opts

def is_filtered(text):
    if not text: return False
    return any(word.lower() in str(text).lower() for word in FORBIDDEN_WORDS)

def make_yemot_response(text):
    """יצירת תשובה נקייה ומדויקת לימות המשיח"""
    # ניקוי רווחים ולוודא שאין שורות ריקות מיותרות
    clean_text = text.strip()
    res = make_response(clean_text + "\n")
    res.headers['Content-Type'] = "text/plain; charset=utf-8"
    return res

# --- לוגיקה מרכזית ---

@app.route('/youtube', methods=['GET', 'POST'])
def youtube_main():
    phone = request.args.get("ApiPhone", "").strip()
    call_id = request.args.get("ApiCallId", "")
    
    # בדיקת הרשאות
    if ACCESS_MODE == "whitelist" and phone != TARGET_PHONE:
        return make_yemot_response("id_list_message=t-אין הרשאה&goto_main=/")

    # ניהול ניתוקים
    if request.args.get("hangup"):
        if call_id in CALL_SESSIONS: del CALL_SESSIONS[call_id]
        return make_response("")

    if call_id not in CALL_SESSIONS:
        CALL_SESSIONS[call_id] = {"step": "menu", "page": 0, "results": []}
    
    session = CALL_SESSIONS[call_id]

    def get_last(p):
        v = request.args.getlist(p)
        return v[-1] if v else None

    # משתנה הקלט (v במקום selection)
    user_input = get_last("v")

    # --- ניהול השלבים ---

    if session["step"] == "menu":
        if not user_input:
            # שימוש במבנה המפוצל - הכי בטוח למנוע ניתוקים
            msg = "t-לשירים חדשים הקש 1. לחיפוש שיר אחר נא אמרו את שם השיר"
            return make_yemot_response(f"id_list_message={msg}&read=v,no,1,1,7,v")

        # אם הקיש 1 או אמר משהו
        if user_input == "1":
            session["query"] = "שירים חדשים 2026"
        else:
            session["query"] = user_input
            
        return start_search(session)

    elif session["step"] == "playing":
        choice = get_last("v")
        if choice == "2": 
            session["page"] += 1
            return play_video(session)
        elif choice == "1":
            session["step"] = "menu"
            return make_yemot_response("goto_main=/")

    return make_yemot_response("goto_main=/")

def start_search(session):
    query = session.get("query", "")
    search_str = f"ytsearch10:{query}"
    
    try:
        with yt_dlp.YoutubeDL(get_yt_options(is_search=True)) as ydl:
            info = ydl.extract_info(search_str, download=False)
            entries = info.get("entries", [])
            session["results"] = [e for e in entries if e and not is_filtered(e.get("title"))]
            session["page"] = 0
            
            if not session["results"]:
                session["step"] = "menu"
                return make_yemot_response("id_list_message=t-לא נמצאו תוצאות&goto_main=/")
            
            return play_video(session)
    except Exception as e:
        logger.error(f"Search error: {e}")
        return make_yemot_response("id_list_message=t-שגיאה בחיפוש&goto_main=/")

def play_video(session):
    results = session.get("results", [])
    idx = session.get("page", 0)
    
    if idx >= len(results):
        session["step"] = "menu"
        return make_yemot_response("id_list_message=t-סוף התוצאות&goto_main=/")
    
    video = results[idx]
    
    try:
        with yt_dlp.YoutubeDL(get_yt_options(is_search=False)) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video['id']}", download=False)
            audio_url = info.get('url', '').replace("&", "%26")
            title = info.get('title', 'שיר').replace(",", " ") # מניעת בעיות פסיקים
            
            session["step"] = "playing"
            
            # מבנה פקודה מאוחד וקריא לימות המשיח
            return make_yemot_response(
                f"id_list_message=t-מנגן {title}&"
                f"play_url={audio_url}&"
                f"read=v,no,1,1,7"
            )
    except Exception as e:
        logger.error(f"Play error: {e}")
        session["page"] += 1
        return play_video(session)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
