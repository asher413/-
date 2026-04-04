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
def home(): return "OK", 200

def make_yemot_response(text):
    response = make_response(text + "\n")
    response.headers['Content-Type'] = "text/plain; charset=utf-8"
    return response

@app.route('/youtube', methods=['GET', 'POST'])
def youtube_api():
    phone = request.args.get("ApiPhone", "").strip()
    if phone != TARGET_PHONE:
        return make_yemot_response("id_list_message=t-אין לך הרשאה&goto_main=/")

    selection = request.args.get("selection")
    choice = request.args.get("choice")
    page = int(request.args.get("page", 0))

    if not selection and not choice:
        return make_yemot_response("read=t-לשירים חדשים מהיום הקש 1 לחיפוש הקש 2=selection,1,1,1,7,st-digits,y,no")

    # חיפוש שירים חדשים לפי תאריך העלאה
    if selection == "1" or (choice == "2" and request.args.get("mode") == "new"):
        return start_search("שירים ישראלים חדשים 2026", page, is_new=True)

    return make_yemot_response("goto_main=/")

def start_search(query_text, page_index, is_new=False):
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'force_ipv4': True,
        'playlist_items': str(page_index + 1),
        'extractor_args': {'youtube': {'player_client': ['ios']}}
    }
    
    # אם ביקשת חדשים - נשתמש בחיפוש ממוקד תאריך
    search_query = f"ytsearch10:{query_text}"
    if is_new:
        # פקודה ליוטיוב להביא לפי תאריך העלאה
        ydl_opts['search_filters'] = 'upload_date' 
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(search_query, download=False)
            results = info.get("entries", [])
            
            if not results or page_index >= len(results):
                return make_yemot_response("id_list_message=t-אין תוצאות נוספות&goto_main=/")
            
            video = results[page_index]
            v_id = video['id']
            title = video.get("title", "שיר").replace("&", "ו").replace("|", "-")
            
            mode_str = "&mode=new" if is_new else ""
            return make_yemot_response(
                f"id_list_message=t-מנגן {title}&"
                f"play_url={BASE_URL}/stream?v={v_id}&"
                f"read=t-לשיר הבא הקש 2=choice,1,1,1,7,st-digits,y,no&page={page_index + 1}{mode_str}"
            )
    except Exception as e:
        logger.error(f"Error: {e}")
        return make_yemot_response("id_list_message=t-תקלה בחיפוש&goto_main=/")

@app.route('/stream')
def stream_audio():
    v_id = request.args.get('v')
    ydl_opts = {
        'format': 'ba/b',
        'quiet': True,
        'force_ipv4': True,
        'extractor_args': {'youtube': {'player_client': ['ios']}}
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(f"https://www.youtube.com/watch?v={v_id}", download=False)
            url = info.get('url')
        
        req = requests.get(url, stream=True, headers={'User-Agent': 'Mozilla/5.0'}, timeout=15)
        return Response(stream_with_context(req.iter_content(chunk_size=8192)), 
                        content_type=req.headers.get('content-type'))
    except Exception as e:
        logger.error(f"Stream error: {e}")
        return "Error", 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
