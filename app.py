import os
import logging
from flask import Flask, request, make_response, Response, stream_with_context
import yt_dlp
import requests

# --- לוגים ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- הגדרות ---
TARGET_PHONE = "0534133753" # הטלפון המורשה
# כאן שנה לכתובת האמיתית של השרת שלך ב-Render
BASE_URL = "https://my-yt-phone.onrender.com" 

@app.route("/")
def home(): return "OK"

def make_yemot_response(text):
    response = make_response(text + "\n")
    response.headers['Content-Type'] = "text/plain; charset=utf-8"
    return response

# --- API מרכזי ---
@app.route('/youtube', methods=['GET', 'POST'])
def youtube_api():
    phone = request.args.get("ApiPhone", "").strip()
    # בדיקת הרשאה
    if phone != TARGET_PHONE:
        return make_yemot_response("id_list_message=t-אין לך הרשאה&goto_main=/")

    # קבלת פרמטרים מה-URL (הסטייט שלנו)
    step = request.args.get("step", "menu")
    query = request.args.get("query")
    page = int(request.args.get("page", 0))
    
    # קבלת קלט מהמשתמש
    selection = request.args.get("selection")
    choice = request.args.get("choice")
    voice_query = request.args.get("voice_query")

    # --- תפריט ראשי ---
    if step == "menu":
        if not selection:
            return make_yemot_response(
                "read=t-לשירים חדשים הקש 1 לחיפוש קולי הקש 2=selection,1,1,1,7,st-digits,y,no"
            )
        
        if selection == "1":
            return start_search("שירים חדשים 2026", 0)
        elif selection == "2":
            return make_yemot_response(
                f"read=t-נא אמרו את שם השיר=voice_query,1,1,1,7,st-voice,y,no&step=ask_voice"
            )

    # --- טיפול בחיפוש קולי ---
    if step == "ask_voice":
        if not voice_query:
            return make_yemot_response("id_list_message=t-לא שמעתי&goto_main=/")
        return start_search(voice_query, 0)

    # --- מעבר בין שירים ---
    if choice == "2": # שיר הבא
        return start_search(query, page + 1)
    elif choice == "1": # חזרה לתפריט
        return make_yemot_response("goto_main=/")

    return make_yemot_response("goto_main=/")

def start_search(query_text, page_index):
    search_string = f"ytsearch10:{query_text}"
    try:
        with yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': True}) as ydl:
            info = ydl.extract_info(search_string, download=False)
            results = info.get("entries", [])

        if not results or page_index >= len(results):
            return make_yemot_response("id_list_message=t-אין תוצאות נוספות&goto_main=/")

        video = results[page_index]
        v_id = video['id']
        title = video.get("title", "שיר")
        
        # בניית הקישורים עם הפרמטרים שיחזרו אלינו בבקשה הבאה
        stream_url = f"{BASE_URL}/stream?v={v_id}"
        next_params = f"&step=play&query={query_text}&page={page_index}"
        
        return make_yemot_response(
            f"id_list_message=t-מנגן כעת {title}&"
            f"play_url={stream_url}&"
            f"read=t-לשיר הבא הקש 2 לתפריט הקש 1=choice,1,1,1,7,st-digits,y,no{next_params}"
        )
    except Exception as e:
        logger.error(f"Search error: {e}")
        return make_yemot_response("id_list_message=t-שגיאה בחיפוש&goto_main=/")

# --- הזרמת השמע ---
@app.route('/stream')
def stream_audio():
    video_id = request.args.get('v')
    if not video_id: return "Missing ID", 400
    
    try:
        with yt_dlp.YoutubeDL({'format': 'bestaudio', 'quiet': True}) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            audio_url = next((f['url'] for f in info.get("formats", []) if f.get("acodec") != "none"), None)
            
        if not audio_url: return "Not found", 404

        req = requests.get(audio_url, stream=True)
        return Response(stream_with_context(req.iter_content(chunk_size=1024)), 
                        content_type=req.headers.get('content-type', 'audio/mp4'))
    except Exception as e:
        return str(e), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
