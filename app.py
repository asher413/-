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

    # חיפוש שירים (רק 3 תוצאות לחיסכון בזיכרון)
    if selection == "1":
        return start_search("שירים חדשים 2026", 0)

    if choice == "2":
        return start_search(query, page + 1)

    return make_yemot_response("goto_main=/")

def start_search(query_text, page_index):
    # הגדרות רזות מאוד כדי לא להפיל את השרת
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'force_ipv4': True,
        'socket_timeout': 10,
        'extractor_args': {'youtube': {'player_client': ['ios']}}
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # מחפשים רק 3 תוצאות במקום 5 או 10
            info = ydl.extract_info(f"ytsearch3:{query_text}", download=False)
            results = info.get("entries", [])

        if not results or page_index >= len(results):
            return make_yemot_response("id_list_message=t-אין עוד תוצאות&goto_main=/")

        video = results[page_index]
        v_id = video['id']
        title = video.get("title", "שיר").replace("&", "ו") # ניקוי תווים בעייתיים
        
        stream_url = f"{BASE_URL}/stream?v={v_id}"
        return make_yemot_response(
            f"id_list_message=t-מנגן {title}&"
            f"play_url={stream_url}&"
            f"read=t-לבא הקש 2=choice,1,1,1,7,st-digits,y,no&step=play&query={query_text}&page={page_index}"
        )
    except Exception as e:
        logger.error(f"Search error: {e}")
        return make_yemot_response("id_list_message=t-שגיאה, נסה שוב&goto_main=/")

@app.route('/stream')
def stream_audio():
    video_id = request.args.get('v')
    if not video_id: return "No ID", 400
        
    ydl_opts = {
        'format': 'wa*[vcodec=none]/ba', # בוחר את פורמט השמע הכי קל
        'quiet': True,
        'force_ipv4': True,
        'extractor_args': {'youtube': {'player_client': ['ios']}}
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
            url = info.get('url')
            
        req = requests.get(url, stream=True, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        return Response(stream_with_context(req.iter_content(chunk_size=8192)), 
                        content_type=req.headers.get('content-type'))
    except Exception as e:
        logger.error(f"Stream error: {e}")
        return "Stream Error", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
