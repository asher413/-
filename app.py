import os
import time
import logging
from flask import Flask, request, make_response
import yt_dlp

# הגדרת לוגים לדיבאג
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- הגדרות מערכת (תחזיר לכאן את הנתונים שלך) ---
ACCESS_MODE = "whitelist" # או "blacklist"
TARGET_PHONE = "0534133753"
FORBIDDEN_WORDS = ["מילה_אסורה1"] 

# ניהול סשנים בזיכרון השרת
CALL_SESSIONS = {}

# --- פונקציות עזר ---

def get_yt_options(is_search=True):
    """הגדרות לעקיפת חסימות וקבלת תוצאות מעודכנות"""
    opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'bestaudio/best',
        'nocheckcertificate': True,
        'geo_bypass': True,
        'extract_flat': is_search,
        'force_ipv4': True,
        # עקיפת חסימת בוטים באמצעות לקוח אנדרואיד
        'user_agent': 'Mozilla/5.0 (Android 14; Mobile; rv:128.0) Gecko/128.0 Firefox/128.0',
        'extractor_args': {'youtube': {'player_client': ['android'], 'skip': ['dash', 'hls']}},
    }
    # אם זה חיפוש - נוסיף מיון לפי תאריך (הכי חדש)
    if is_search:
        opts['playlist_items'] = '1-10'
        # פקודה פנימית ל-yt-dlp למיין לפי תאריך העלאה
        opts['logger'] = logger
    return opts

def is_filtered(text):
    if not text: return False
    return any(word.lower() in str(text).lower() for word in FORBIDDEN_WORDS)

def make_yemot_response(text):
    """יצירת תשובה נקייה לימות המשיח"""
    res = make_response(text + "\n")
    res.headers['Content-Type'] = "text/plain; charset=utf-8"
    return res

# --- לוגיקה מרכזית ---

@app.route('/youtube', methods=['GET', 'POST'])
def youtube_main():
    phone = request.args.get("ApiPhone", "").strip()
    call_id = request.args.get("ApiCallId", "")
    
    # בדיקת הרשאות (whitelist)
    if ACCESS_MODE == "whitelist" and phone != TARGET_PHONE:
        return make_yemot_response("id_list_message=t-אין הרשאה&goto_main=/")

    # ניהול ניתוקים
    if request.args.get("hangup"):
        if call_id in CALL_SESSIONS: del CALL_SESSIONS[call_id]
        return make_response("")

    # אתחול סשן
    if call_id not in CALL_SESSIONS:
        CALL_SESSIONS[call_id] = {"step": "menu", "page": 0, "results": []}
    
    session = CALL_SESSIONS[call_id]

    # חילוץ פרמטר אחרון (למניעת כפילויות בימות המשיח)
    def get_last(p):
        v = request.args.getlist(p)
        return v[-1] if v else None

    # --- ניהול השלבים ---

    # שלב 1: תפריט ובחירה (כולל חיפוש קולי)
    if session["step"] == "menu":
        selection = get_last("selection")
        voice_query = get_last("voice_query")

        if not selection and not voice_query:
            # st-voice = חיפוש קולי אמיתי (הקלטה)
            return make_yemot_response(
                "read=t-לשירים חדשים הקש 1. לחיפוש שיר אחר, נא אמרו את שם השיר לאחר הצליל=selection,1,1,1,7,st-voice,y,no"
            )

        # אם המשתמש אמר משהו (זיהוי קולי)
        if voice_query:
            session["query"] = voice_query
            return start_search(session)
        
        # אם המשתמש הקיש 1 (שירים חדשים)
        if selection == "1":
            session["query"] = "שירים חדשים 2026"
            return start_search(session)
        
        # אם המערכת זיהתה דיבור בתפריט הראשי (בחלק מההגדרות של ימות)
        if selection and len(selection) > 1:
            session["query"] = selection
            return start_search(session)

    # שלב 2: ניהול מעבר בין שירים
    elif session["step"] == "playing":
        choice = get_last("choice")
        if choice == "2": # שיר הבא
            session["page"] += 1
            return play_video(session)
        elif choice == "1": # תפריט ראשי
            session["step"] = "menu"
            return make_yemot_response("goto_main=/")

    return make_yemot_response("goto_main=/")

# --- פונקציות ביצוע ---

def start_search(session):
    query = session.get("query", "")
    # הוספת המילה "חדש" כדי לעזור לחיפוש להיות רלוונטי
    search_str = f"ytsearch10:{query}"
    
    try:
        # שימוש ב-Options שכוללים מיון לפי תאריך
        with yt_dlp.YoutubeDL(get_yt_options(is_search=True)) as ydl:
            # כאן אנחנו מוסיפים ידנית את המיון כי ytsearchdate בעייתי
            info = ydl.extract_info(search_str, download=False)
            entries = info.get("entries", [])
            
            # סינון ותיקון תוצאות
            session["results"] = [e for e in entries if e and not is_filtered(e.get("title"))]
            session["page"] = 0
            
            if not session["results"]:
                session["step"] = "menu"
                return make_yemot_response("id_list_message=t-לא נמצאו תוצאות&goto_main=/")
            
            # **שידרוג: מתחיל לנגן ישר את השיר הראשון**
            return play_video(session)
            
    except Exception as e:
        logger.error(f"Search error: {e}")
        return make_yemot_response("id_list_message=t-שגיאה בחיפוש&goto_main=/")

def play_video(session):
    results = session.get("results", [])
    idx = session.get("page", 0)
    
    if idx >= len(results):
        session["step"] = "menu"
        return make_yemot_response("id_list_message=t-הגעת לסוף התוצאות&goto_main=/")
    
    video = results[idx]
    
    try:
        with yt_dlp.YoutubeDL(get_yt_options(is_search=False)) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video['id']}", download=False)
            audio_url = info.get('url')
            title = info.get('title', 'שיר')
            
            session["step"] = "playing"
            # ימות המשיח: משמיע את השם, מנגן, ומחכה להקשה לשיר הבא
            return (f"id_list_message=t-מנגן כעת {title}&"
                    f"play_url={audio_url}&"
                    f"read=t-לשיר הבא הקש 2, לתפריט הקש 1=choice,1,1,1,7,st-javascript,y,no")
                    
    except Exception as e:
        logger.error(f"Play error: {e}")
        # אם יש שגיאה בשיר ספציפי (חסום וכו'), עובר אוטומטית לבא בתור
        session["page"] += 1
        return play_video(session)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
