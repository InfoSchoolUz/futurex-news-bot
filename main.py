import feedparser
import google.generativeai as genai
import requests
import json
import os
import hashlib
import time
from datetime import datetime

# ============================================================
# SOZLAMALAR
# ============================================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "@futurex_1984")

RSS_SOURCES = [
    {"name": "Kun.uz",        "url": "https://kun.uz/news/rss"},
    {"name": "Gazeta.uz",     "url": "https://www.gazeta.uz/uz/rss/"}, # URL aniqlashtirildi
    {"name": "Daryo.uz",      "url": "https://daryo.uz/rss/"},         # URL aniqlashtirildi
    {"name": "Aniq.uz",       "url": "https://aniq.uz/rss"},
    {"name": "Darakchi.uz",   "url": "https://darakchi.uz/rss"},
    {"name": "Nuz.uz",        "url": "https://nuz.uz/feed"},
    {"name": "BBC O'zbek",    "url": "https://feeds.bbci.co.uk/uzbek/rss.xml"},
    {"name": "Ozodlik",       "url": "https://www.ozodlik.org/api/zfpjlvem"},
    {"name": "Uza.uz",        "url": "https://uza.uz/rss"},
    {"name": "Xs.uz",         "url": "https://xs.uz/rss"},
]

SENT_NEWS_FILE = "sent_news.json"

def load_sent_news():
    if os.path.exists(SENT_NEWS_FILE):
        with open(SENT_NEWS_FILE, "r") as f:
            try:
                return json.load(f)
            except:
                return []
    return []

def save_sent_news(sent_list):
    with open(SENT_NEWS_FILE, "w") as f:
        json.dump(sent_list[-500:], f)

def get_news_hash(title):
    return hashlib.md5(title.lower().strip().encode()).hexdigest()

# ============================================================
# RSS DAN YANGILIKLAR O'QISH (BLOKDAN AYLANIB O'TISH BILAN)
# ============================================================
def fetch_all_news():
    all_news = []
    # Haqiqiy brauzer sarlavhasi (User-Agent) Kun.uz va Daryo.uz blokini ochadi
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    
    for source in RSS_SOURCES:
        try:
            # feedparser o'rniga requests bilan kontent yuklanadi
            response = requests.get(source["url"], headers=headers, timeout=15)
            if response.status_code == 200:
                feed = feedparser.parse(response.content)
                count = 0
                for entry in feed.entries[:8]:  # Har manbadan max 8 ta
                    title = entry.get("title", "").strip()
                    link = entry.get("link", "").strip()
                    summary = entry.get("summary", entry.get("description", "")).strip()
                    
                    if title and link:
                        all_news.append({
                            "title": title,
                            "link": link,
                            "summary": summary[:400] if summary else "",
                            "source": source["name"],
                            "hash": get_news_hash(title)
                        })
                        count += 1
                print(f"✅ {source['name']}: {count} ta yangilik olindi")
            else:
                print(f"⚠️ {source['name']} yuklanmadi (Status: {response.status_code})")
        except Exception as e:
            print(f"❌ {source['name']} xatolik: {e}")
            
    return all_news

# ============================================================
# GEMINI AI BILAN KLASTERLASH VA XULOSA QILISH
# ============================================================
def process_news_with_gemini(new_news_list):
    """
    Barcha yangiliklarni Gemini AI ga yuboradi. 
    Gemini o'xshashlarini bitta qiladi va tayyor JSON formatda qaytaradi.
    """
    genai.configure(api_key=GEMINI_API_KEY)
    # Eng so'nggi va barqaror model
    model = genai.GenerativeModel("gemini-2.0-flash", generation_config={"response_mime_type": "application/json"})

    # AI ga yuborish uchun ixcham matn tayyorlash
    input_data = []
    for i, n in enumerate(new_news_list):
        input_data.append({
            "id": i,
            "title": n["title"],
            "summary": n["summary"],
            "source": n["source"],
            "link": n["link"]
        })

    prompt = f"""
Senga O'zbekiston OAVlaridan olingan yangiliklar ro'yxati berilmoqda.
Vazifang:
1. Yangiliklarni tahlil qil va bir xil voqea/hodisaga tegishli o'xshash yangiliklarni bitta guruhga birlashtir (Klasterlash).
2. Har bir guruh uchun o'zbek tilida qisqa, tushunarli, jozibali sarlavha va 2-3 jumlali umumiy neytral xulosa (summary) yoz.
3. Guruhga kirgan barcha manbalar nomi (sources) va havolalarini (links) ro'yxatga saqlang.
4. Agar biror yangilikka o'xshash boshqa xabar bo'lmasa, uni alohida guruh qilib chiqaring.

Natijani FAQAT mana shu JSON strukturada qaytar:
{{
  "news_groups": [
    {{
      "ai_title": "Birlashtirilgan jozibali sarlavha",
      "ai_summary": "Barcha manbalardan yig'ilgan voqeaning qisqa va aniq 2-3 jumlali xulosasi.",
      "sources": ["Kun.uz", "Daryo.uz"],
      "links": ["https://...", "https://..."],
      "matched_ids": [0, 3]
    }}
  ]
}}

Yangiliklar ro'yxati:
{json.dumps(input_data, ensure_ascii=False)}
"""

    try:
        response = model.generate_content(prompt)
        result = json.loads(response.text)
        return result.get("news_groups", [])
    except Exception as e:
        print(f"❌ Gemini tahlilida xatolik: {e}")
        return []

# ============================================================
# TELEGRAM GA XABAR YUBORISH
# ============================================================
def send_to_telegram(title, summary, sources, links):
    # Manbalarni teglarga o'girish, masalan: #Kun_uz #Daryo_uz
    formatted_sources = " ".join([f"#{s.replace('.', '_').replace(' ', '_')}" for s in sources])
    
    # Birinchi manbani asosiy havola qilib ko'rsatish
    main_link = links[0] if links else "#"

    message = f"""📌 <b>{title}</b>

{summary}

🔗 <b>Batafsil manbalarda:</b>
<a href="{main_link}">O'qish davom etishi →</a>

📰 {formatted_sources}
🤖 <i>FutureX AI News</i>"""

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }

    try:
        response = requests.post(url, json=payload)
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Telegram yuborishda xatolik: {e}")
        return False

# ============================================================
# ASOSIY FUNKSIYA
# ============================================================
def main():
    print(f"\n🚀 FutureX News Aggregator v2 (AI Clustering) ishga tushdi...")
    
    sent_news = load_sent_news()
    sent_hashes = set(sent_news)

    # 1. Yangiliklarni yig'ish
    all_news = fetch_all_news()
    if not all_news:
        print("ℹ️ Hech qanday yangilik topilmadi.")
        return

    # 2. Faqat yangilarini ajratib olish
    new_news = [n for n in all_news if n["hash"] not in sent_hashes]
    print(f"🆕 {len(new_news)} ta yangi xabarlar qayta ishlanmoqda...")

    if not new_news:
        print("ℹ️ Yangi xabarlar yo'q.")
        return

    # 3. Gemini orqali o'xshashlarini guruhlash va xulosalash
    print("🧠 Gemini AI o'xshash yangiliklarni klasterlamoqda...")
    news_groups = process_news_with_gemini(new_news)
    
    sent_count = 0
    processed_hashes = set()

    # 4. Telegramga chiqarish
    for group in news_groups[:10]: # Bitta ishlashda max 10 ta post
        title = group.get("ai_title")
        summary = group.get("ai_summary")
        sources = group.get("sources", [])
        links = group.get("links", [])
        matched_ids = group.get("matched_ids", [])

        if title and summary:
            if send_to_telegram(title, summary, sources, links):
                sent_count += 1
                # Guruh ichidagi barcha original yangiliklarni yuborilgan deb belgilash
                for idx in matched_ids:
                    if idx < len(new_news):
                        processed_hashes.add(new_news[idx]["hash"])
                time.sleep(3) # Telegram spam-filtrdan himoya

    # Yuborilganlarni saqlash
    new_sent_list = sent_news + list(processed_hashes)
    save_sent_news(new_sent_list)
    
    print(f"✅ Muvaffaqiyatli yakunlandi. {sent_count} ta unikal jamlangan post yuborildi!")

if __name__ == "__main__":
    main()
