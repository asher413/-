import os
import logging
from flask import Flask, request, make_response, Response, stream_with_context
import yt_dlp
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

TARGET_PHONE = "0534133753" 
BASE_URL = "https://my-yt-phone.onrender.com" 

@app.route("/")
def home():
    return "SERVER_ONLINE", 200

def make_yemot_response(text):
    response = make_response(text + "\n")
    response.headers['Content-Type'] = "text/plain; charset=utf-8"
    return response

@app.route('/youtube', methods=['GET', 'POST'])
def youtube_api():
    phone = request.args.get("ApiPhone", "").strip()
    if phone != TARGET_PHONE:
        return make_yemot_response("id_list_message=t-אין לך הרשאה&goto_main=/")

    step = request.args.get("step", "menu")
    query = request.args.get("query", "שירים חדשים")
    page = int(request.args.get("page", 0))
    selection = request.args.get("selection")
    choice = request.args.get("choice")

    if step == "menu" and not selection:
        return make_yemot_response("read=t-לשירים חדשים הקש 1 לחיפוש קולי הקש 2=selection,1,1,1,7,st-digits,y,no")

    # חיפוש שירים - כאן הגדרנו שירים חדשים
    if selection == "1":
        return start_search("שירים ישראלים חדשים 2026", 0, sort_by_date=True)

    if choice == "2":
        return start_search(query, page + 1, sort_by_date=(step == "play_new"))

    return make_yemot_response("goto_main=/")

def start_search(query_text, page_index, sort_by_date=False):
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'force_ipv4': True,
        'socket_timeout': 10,
        'extractor_args': {'youtube': {'player_client': ['ios']}}
    }
    
    # הוספת סינון לפי תאריך אם מדובר בשירים חדשים
    if sort_by_date:
        ydl_opts['playlist_items'] = '1,2,3,4,5' # לוקח את ה-5 הראשונים
        # בחיפוש שטוח (flat) יוטיוב מחזיר לפי הרלוונטיות, 
        # כדי לקבל תאריך מדויק נשתמש במילת חיפוש ממוקדת יותר
        query_text = f"{query_text} upload_date"

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"ytsearch5:{query_text}", download=False)
            results = info.get("entries", [])

        if not results or page_index >= len(results):
            return make_yemot_response("id_list_message=t-אין עוד תוצאות&goto_main=/")

        video = results[page_index]
        v_id = video['id']
        title = video.get("title", "שיר").replace("&", "ו").replace("|", "-")
        
        stream_url = f"{BASE_URL}/stream?v={v_id}"
        # שומרים את הסטייט כדי לדעת אם להמשיך לחפש "חדשים" בשיר הבא
        step_name = "play_new" if sort_by_date else "play"
        
        return make_yemot_response(
            f"id_list_message=t-מנגן {title}&"
            f"play_url={stream_url}&"
            f"read=t-לשיר הבא הקש 2=choice,1,1,1,7,st-digits,y,no&step={step_name}&query={query_text}&page={page_index}"
        )
    except Exception as e:
        logger.error(f"Search error: {e}")
        return make_yemot_response("id_list_message=t-שגיאה בחיפוש&goto_main=/")

@app.route('/stream')
def stream_audio():
    video_id = request.args.get('v')
    if not video_id: return "No ID", 400
        
    ydl_opts = {
        'format': 'ba/b', # איכות בסיסית ומהירה
        'quiet': True,
        'force_ipv4': True,
        'extractor_args': {'youtube': {'player_client': ['ios']}}
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            url = info.get('url')
            
        req = requests.get(url, stream=True, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        return Response(stream_with_context(req.iter_content(chunk_size=1024*16)), 
                        content_type=req.headers.get('content-type'))
    except Exception as e:
        logger.error(f"Stream error: {e}")
        return "Stream Error", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
