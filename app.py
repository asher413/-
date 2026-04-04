import os
import yt_dlp
from flask import Flask, request, make_response

app = Flask(__name__)

TARGET_PHONE = "0534133753"

def make_yemot_res(text):
    res = make_response(text + "\n")
    res.headers['Content-Type'] = "text/plain; charset=utf-8"
    return res

@app.route("/")
def home(): return "READY", 200

@app.route('/youtube', methods=['GET', 'POST'])
def youtube_api():
    phone = request.args.get("ApiPhone", "").strip()
    if phone != TARGET_PHONE:
        return make_yemot_res("id_list_message=t-אין הרשאה&goto_main=/")

    selection = request.args.get("selection")
    page = int(request.args.get("page", 0))

    # תפריט ראשי
    if not selection:
        return make_yemot_res("read=t-לשירים חדשים הקש 1=selection,1,1,1,7,st-digits,y,no")

    # חיפוש שירים (שימוש ב-IOS כדי למנוע חסימה)
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'force_ipv4': True,
        'extractor_args': {'youtube': {'player_client': ['ios']}}
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # חיפוש ממוקד תאריך
            search = ydl.extract_info(f"ytsearch10:שירים ישראלים חדשים 2026", download=False)
            results = search.get("entries", [])

        if not results or page >= len(results):
            return make_yemot_res("id_list_message=t-אין תוצאות&goto_main=/")

        video = results[page]
        v_id = video['id']
        title = video.get("title", "שיר").replace("&", "ו").replace("|", "-")

        # קבלת הקישור הישיר מהר כדי שימות המשיח ינגנו אותו בעצמם
        with yt_dlp.YoutubeDL({'format': 'ba/b', 'quiet': True}) as ydl_stream:
            info = ydl_stream.extract_info(f"https://www.youtube.com/watch?v={v_id}", download=False)
            direct_url = info.get('url')

        # שליחת פקודת הנגינה ישירות לימות המשיח
        # הוספתי id_list_message כדי שיהיה צליל בזמן הטעינה
        return make_yemot_res(
            f"id_list_message=t-מנגן {title}&"
            f"play_url={direct_url}&"
            f"read=t-לבא הקש 2=selection,1,1,1,7,st-digits,y,no&page={page + 1}"
        )
    except Exception as e:
        return make_yemot_res(f"id_list_message=t-שגיאה בחיפוש&goto_main=/")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
