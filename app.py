import os
import time
import logging
from flask import Flask, request, make_response
import yt_dlp

# הגדרת לוגים כדי שתוכל לראות בדיבג מה קורה
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- הגדרות מערכת ---
TARGET_PHONE = "0534133753" # הטלפון המורשה
FORBIDDEN_WORDS = ["מילה_אסורה1", "תוכן_פוגעני"] # סינון בסיסי

# זיכרון לניהול שיחות (Sessions)
CALL_SESSIONS = {}

# --- פונקציות עזר ל-YouTube ---

def get_yt_options(is_search=True):
    """הגדרות לעקיפת חסימות וקבלת לינקים ישירים"""
    opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'bestaudio/best',
        # שימוש בלקוח אנדרואיד - הכי אמין היום נגד חסימות
        'user_agent': 'Mozilla/5.0 (Android 14; Mobile; rv:128.0) Gecko/128.0 Firefox/128.0',
        'nocheckcertificate': True,
        'geo_bypass': True,
        'extract_flat': is_search,
        'force_ipv4': True,
        'extractor_args': {
            'youtube': {
                'player_client': ['android'],
                'skip': ['dash', 'hls']
            }
        },
    }
    return opts

def is_filtered(text):
    if not text: return False
    return any(word.lower() in str(text).lower() for word in FORBIDDEN_WORDS)

def make_yemot_response(text):
    """יצירת תשובה תקינה לימות המשיח"""
    logger.info(f"Sending Response: {text}")
    response = make_response(text + "\n")
    response.headers['Content-Type'] = "text/plain; charset=utf-8"
    return response

# --- לוגיקה מרכזית ---

@app.route('/youtube', methods=['GET', 'POST'])
def youtube_api():
    phone = request.args.get("ApiPhone", "").strip()
    call_id = request.args.get("ApiCallId", "")
    
    # בדיקת הרשאה
    if phone != TARGET_PHONE:
        return make_yemot_response("id_list_message=t-אין לך הרשאה למערכת זו&goto_main=/")

    # ניהול ניתוק שיחה
    if request.args.get("hangup"):
        if call_id in CALL_SESSIONS:
            del CALL_SESSIONS[call_id]
        return make_response("")

    # אתחול סשן למתקשר
    if call_id not in CALL_SESSIONS:
        CALL_SESSIONS[call_id] = {"step": "menu", "page": 0, "results": []}
    
    session = CALL_SESSIONS[call_id]
    
    # פונקציה לקבלת הקלט האחרון מהמשתמש
    def get_input(param):
        vals = request.args.getlist(param)
        return vals[-1] if vals else None

    # --- ניהול תפריטים ---
    
    # 1. תפריט ראשי
    if session["step"] == "menu":
        selection = get_input("selection")
        if not selection:
            return make_yemot_response("read=t-לשירים חדשים הקש 1, לחיפוש קולי אמרו את שם השיר לאחר הצליל=selection,1,1,1,7,st-voice,y,no")
        
        if selection == "1":
            session["query"] = "שירים חדשים 2026" # חיפוש אוטומטי של הכי חדש
            return start_search(session)
        else:
            # אם הקישו משהו אחר או שהזיהוי הקולי החזיר טקסט (כי הגדרנו st-voice)
            session["query"] = selection
            return start_search(session)

    # 2. שלב ההמתנה לבחירת שיר הבא
    elif session["step"] == "waiting_next":
        choice = get_input("choice")
        if choice == "2": # המשתמש רוצה שיר אחר
            session["page"] += 1
            return play_current_video(session)
        elif choice == "1": # חזרה לתפריט
            session["step"] = "menu"
            return make_yemot_response("goto_main=/")
        else:
            return play_current_video(session)

    return make_yemot_response("goto_main=/")

# --- פונקציות ביצוע ---

def start_search(session):
    query = session.get("query", "שירים")
    # ytsearchdate - מביא את התוצאות הכי חדשות לפי תאריך
    search_string = f"ytsearchdate10:{query}"
    
    try:
        with yt_dlp.YoutubeDL(get_yt_options(is_search=True)) as ydl:
            info = ydl.extract_info(search_string, download=False)
            entries = info.get("entries", [])
            # סינון תוצאות לפי מילים אסורות
            session["results"] = [e for e in entries if not is_filtered(e.get("title"))]
            session["page"] = 0
            
            if not session["results"]:
                session["step"] = "menu"
                return make_yemot_response("id_list_message=t-לא נמצאו תוצאות, נסה שנית&goto_main=/")
            
            # הצלחה - עוברים ישר לניגון השיר הראשון!
            return play_current_video(session)
    except Exception as e:
        logger.error(f"Search Error: {e}")
        return make_yemot_response("id_list_message=t-שגיאה בחיפוש, נסה שוב מאוחר יותר&goto_main=/")

def play_current_video(session):
    results = session.get("results", [])
    page = session.get("page", 0)
    
    if page >= len(results):
        session["step"] = "menu"
        return make_yemot_response("id_list_message=t-סיימנו את כל התוצאות&goto_main=/")
    
    video = results[page]
    video_url = f"https://www.youtube.com/watch?v={video['id']}"
    
    try:
        with yt_dlp.YoutubeDL(get_yt_options(is_search=False)) as ydl:
            info = ydl.extract_info(video_url, download=False)
            audio_url = info.get('url')
            title = info.get('title', 'שיר ללא שם')
            
            session["step"] = "waiting_next"
            # פקודה משולבת: מודיע מה השם, מנגן, ומאפשר להקיש 2 כדי לעבור הלאה
            return (f"id_list_message=t-מנגן כעת {title}&"
                    f"play_url={audio_url}&"
                    f"read=t-לשיר הבא הקש 2, לתפריט הקש 1=choice,1,1,1,7,st-javascript,y,no")
            
    except Exception as e:
        logger.error(f"Playback Error: {e}")
        # אם שיר אחד נכשל (נחסם ע"י יוטיוב), ננסה אוטומטית את הבא
        session["page"] += 1
        return play_current_video(session)

if __name__ == "__main__":
    # הרצה על הפורט של Render/Heroku
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
