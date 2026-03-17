import os
import time
import logging
from flask import Flask, request, make_response
import yt_dlp
from urllib.parse import quote

# הגדרת לוגים כדי שתוכל לראות בדיבג מה קורה
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- הגדרות מערכת ---
ACCESS_MODE = "whitelist"
TARGET_PHONE = "0534133753"
FORBIDDEN_WORDS = ["מילה_אסורה1", "תוכן_רע"]
TARGET_PHONE = "0534133753" # הטלפון המורשה
FORBIDDEN_WORDS = ["מילה_אסורה1", "תוכן_פוגעני"] # סינון בסיסי

# --- זיכרון זמני ---
SEARCH_CACHE = {}
CACHE_TIME = 300
# זיכרון לניהול שיחות (Sessions)
CALL_SESSIONS = {}

# --- בדיקת שרת ---
@app.route('/')
def home():
    return "SERVER_OK"
# --- פונקציות עזר ל-YouTube ---

# --- הגדרות yt-dlp מעודכנות לעקיפת חסימות ---
def get_yt_options(is_search=True):
    """הגדרות לעקיפת חסימות וקבלת לינקים ישירים"""
    opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'bestaudio/best',
        # שימוש ב-User Agent של מכשיר אנדרואיד כדי להפחית חסימות
        # שימוש בלקוח אנדרואיד - הכי אמין היום נגד חסימות
        'user_agent': 'Mozilla/5.0 (Android 14; Mobile; rv:128.0) Gecko/128.0 Firefox/128.0',
        'nocheckcertificate': True,
        'geo_bypass': True,
        'extract_flat': is_search,
        'force_ipv4': True,
        'retries': 10,
        # שימוש בלקוח אינטרנט של אנדרואיד לעקיפת בוטים
        'extractor_args': {'youtube': {'player_client': ['android'], 'skip': ['dash', 'hls']}},
        'extractor_args': {
            'youtube': {
                'player_client': ['android'],
                'skip': ['dash', 'hls']
            }
        },
    }
    return opts

@@ -44,120 +45,125 @@ def is_filtered(text):
    return any(word.lower() in str(text).lower() for word in FORBIDDEN_WORDS)

def make_yemot_response(text):
    """יצירת תשובה תקינה לימות המשיח"""
    logger.info(f"Sending Response: {text}")
    response = make_response(text + "\n")
    response.headers['Content-Type'] = "text/plain; charset=utf-8"
    return response

@app.route('/youtube', methods=['GET','POST'])
def main_logic():
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
        if call_id in CALL_SESSIONS: del CALL_SESSIONS[call_id]
        if call_id in CALL_SESSIONS:
            del CALL_SESSIONS[call_id]
        return make_response("")

    is_authorized = True
    if ACCESS_MODE == "whitelist" and phone != TARGET_PHONE:
        is_authorized = False
    
    if not is_authorized:
        return make_yemot_response("id_list_message=t-אין לך הרשאה&goto_main=/")

    # אתחול סשן למתקשר
    if call_id not in CALL_SESSIONS:
        CALL_SESSIONS[call_id] = {"step": "menu", "page": 0}
            
        CALL_SESSIONS[call_id] = {"step": "menu", "page": 0, "results": []}
    
    session = CALL_SESSIONS[call_id]

    def get_last_param(param):
    # פונקציה לקבלת הקלט האחרון מהמשתמש
    def get_input(param):
        vals = request.args.getlist(param)
        return vals[-1] if vals else None

    # תפריט ראשי
    # --- ניהול תפריטים ---
    
    # 1. תפריט ראשי
    if session["step"] == "menu":
        selection = get_last_param("selection")
        selection = get_input("selection")
        if not selection:
            return make_yemot_response("read=t-לשירים חדשים הקש 1 לחיפוש קולי הקש 2=selection,1,1,1,7,st-javascript,y,no")
            return make_yemot_response("read=t-לשירים חדשים הקש 1, לחיפוש קולי אמרו את שם השיר לאחר הצליל=selection,1,1,1,7,st-voice,y,no")

        if selection == "1":
            # חיפוש אוטומטי של שירים חדשים
            session["query"] = "שירים חדשים 2026"
            return process_search(session)
        elif selection == "2":
            session["step"] = "ask_query"
            # st-voice,y,no - הפקודה לזיהוי דיבור בימות המשיח
            return make_yemot_response("read=t-נא אמרו בקול רם את שם השיר=query,1,1,1,7,st-voice,y,no")

    # קבלת תוצאת חיפוש קולי
    elif session["step"] == "ask_query":
        query = get_last_param("query")
        if not query:
            return make_yemot_response("read=t-לא שמעתי, נא אמרו שוב את שם השיר=query,1,1,1,7,st-voice,y,no")
        session["query"] = query
        return process_search(session)

    # מעבר בין שירים (אם המשתמש ביקש שיר אחר)
    elif session["step"] == "wait_next":
        choice = get_last_param("choice")
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
            return process_play(session)
        else:
            return play_current_video(session)
        elif choice == "1": # חזרה לתפריט
            session["step"] = "menu"
            return make_yemot_response("goto_main=/")
        else:
            return play_current_video(session)

    return make_yemot_response("goto_main=/")

def process_search(session):
    query = session.get("query", "")
    # שימוש ב-ytsearchdate כדי להביא את התוצאות הכי חדשות
    search_query = f"ytsearchdate10:{query}" 
# --- פונקציות ביצוע ---

def start_search(session):
    query = session.get("query", "שירים")
    # ytsearchdate - מביא את התוצאות הכי חדשות לפי תאריך
    search_string = f"ytsearchdate10:{query}"

    try:
        with yt_dlp.YoutubeDL(get_yt_options(True)) as ydl:
            info = ydl.extract_info(search_query, download=False)
        with yt_dlp.YoutubeDL(get_yt_options(is_search=True)) as ydl:
            info = ydl.extract_info(search_string, download=False)
            entries = info.get("entries", [])
            valid_results = [e for e in entries if not is_filtered(e.get("title"))]
            
            if not valid_results:
                return "id_list_message=t-לא נמצאו תוצאות&goto_main=/"
            
            session["results"] = valid_results
            # סינון תוצאות לפי מילים אסורות
            session["results"] = [e for e in entries if not is_filtered(e.get("title"))]
            session["page"] = 0
            # מעבר ישיר לניגון השיר הראשון
            return process_play(session)

            if not session["results"]:
                session["step"] = "menu"
                return make_yemot_response("id_list_message=t-לא נמצאו תוצאות, נסה שנית&goto_main=/")
            
            # הצלחה - עוברים ישר לניגון השיר הראשון!
            return play_current_video(session)
    except Exception as e:
        print("SEARCH ERROR:", e)
        return "id_list_message=t-שגיאה בחיפוש&goto_main=/"
        logger.error(f"Search Error: {e}")
        return make_yemot_response("id_list_message=t-שגיאה בחיפוש, נסה שוב מאוחר יותר&goto_main=/")

def process_play(session):
def play_current_video(session):
    results = session.get("results", [])
    page = session.get("page", 0)

    if page >= len(results):
        return "id_list_message=t-אין יותר שירים&goto_main=/"

        session["step"] = "menu"
        return make_yemot_response("id_list_message=t-סיימנו את כל התוצאות&goto_main=/")
    
    video = results[page]
    video_id = video["id"]

    video_url = f"https://www.youtube.com/watch?v={video['id']}"
    
    try:
        with yt_dlp.YoutubeDL(get_yt_options(False)) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            url = info.get('url')
            title = info.get('title', 'שיר')
        with yt_dlp.YoutubeDL(get_yt_options(is_search=False)) as ydl:
            info = ydl.extract_info(video_url, download=False)
            audio_url = info.get('url')
            title = info.get('title', 'שיר ללא שם')

            # הודעה על השיר שמתנגן ואפשרות לעבור לשיר הבא בסיום/הקשה
            session["step"] = "wait_next"
            return f"id_list_message=t-מנגן כעת {title}&play_url={url}&read=t-לשיר הבא הקש 2=choice,1,1,1,7,st-javascript,y,no"
            session["step"] = "waiting_next"
            # פקודה משולבת: מודיע מה השם, מנגן, ומאפשר להקיש 2 כדי לעבור הלאה
            return (f"id_list_message=t-מנגן כעת {title}&"
                    f"play_url={audio_url}&"
                    f"read=t-לשיר הבא הקש 2, לתפריט הקש 1=choice,1,1,1,7,st-javascript,y,no")

    except Exception as e:
        print("PLAY ERROR:", e)
        # אם שיר אחד חסום, מנסה אוטומטית את הבא בתור
        logger.error(f"Playback Error: {e}")
        # אם שיר אחד נכשל (נחסם ע"י יוטיוב), ננסה אוטומטית את הבא
        session["page"] += 1
        return process_play(session)
        return play_current_video(session)

if __name__ == "__main__":
    # הרצה על הפורט של Render/Heroku
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
