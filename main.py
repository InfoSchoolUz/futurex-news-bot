import feedparser
import google.generativeai as genai
import requests
import json
import os
import hashlib
import time
from datetime import datetime
from difflib import SequenceMatcher

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "@futurex_1984")

RSS_SOURCES = [
    {"name": "TechCrunch AI",        "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
    {"name": "MIT Technology Review", "url": "https://www.technologyreview.com/feed/"},
    {"name": "The Verge AI",          "url": "https://www.theverge.com/ai-artificial-intelligence/rss/index.xml"},
    {"name": "VentureBeat AI",        "url": "https://venturebeat.com/category/ai/feed/"},
    {"name": "Wired AI",              "url": "https://www.wired.com/feed/tag/ai/latest/rss"},
    {"name": "DeepMind Blog",         "url": "https://deepmind.google/blog/rss.xml"},
    {"name": "IEEE Spectrum AI",      "url": "https://spectrum.ieee.org/feeds/topic/artificial-intelligence.rss"},
    {"name": "The Robot Report",      "url": "https://www.therobotreport.com/feed/"},
]

SENT_NEWS_FILE = "sent_news.json"
SIMILARITY_THRESHOLD = 0.65

def load_sent_news():
    if os.path.exists(SENT_NEWS_FILE):
        try:
            with open(SENT_NEWS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_sent_news(sent_list):
    with open(SENT_NEWS_FILE, "w", encoding="utf-8") as f:
        json.dump(sent_list[-500:], f, ensure_ascii=False)

def get_news_hash(title):
    return hashlib.md5(title.lower().strip().encode("utf-8")).hexdigest()

def is_similar(title1, title2):
    return SequenceMatcher(None, title1.lower(), title2.lower()).ratio() > SIMILARITY_THRESHOLD

# FIX C: HTML maxsus belgilarini tozalash
def escape_html(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def fetch_all_news():
    all_news = []
    for source in RSS_SOURCES:
        try:
            # FIX B: feedparser uchun timeout
            feed = feedparser.parse(source["url"], request_headers={"User-Agent": "Mozilla/5.0"})
            count = 0
            for entry in feed.entries[:8]:
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                summary = entry.get("summary", entry.get("description", "")).strip()
                if title and link:
                    all_news.append({
                        "title": title,
                        "link": link,
                        "summary": summary[:600] if summary else "",
                        "source": source["name"],
                        "hash": get_news_hash(title)
                    })
                    count += 1
            print(f"OK {source['name']}: {count} ta")
        except Exception as e:
            print(f"XATO {source['name']}: {e}")
    return all_news

def group_similar_news(news_list):
    groups = []
    used = set()
    for i, news in enumerate(news_list):
        if i in used:
            continue
        group = [news]
        used.add(i)
        for j, other in enumerate(news_list):
            if j in used:
                continue
            if is_similar(news["title"], other["title"]):
                group.append(other)
                used.add(j)
        groups.append(group)
    return groups

def translate_with_gemini(title, summary):
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-1.5-flash")

    # FIX A: Markdown va HTML belgilarini chiqarmaslikni so'rash
    prompt = f"""Vazifa: Quyidagi inglizcha AI/texnologiya yangiligini O'zbek tiliga tarjima qil.

Sarlavha: {title}
Mazmun: {summary[:400] if summary else ''}

Qoidalar:
1. FAQAT o'zbek tilida yoz (lotin alifbosi)
2. Birinchi qatorda: emoji + qisqa sarlavha
3. Ikkinchi qatorda: 2 jumlali tushuntirish
4. Hech qanday markdown (**, *, ```) yoki HTML teglari ishlatma
5. Hech qanday kirish so'z yoki tushuntirish yozma
6. Faqat 2 qator yoz, boshqa hech narsa yo'q

Javob:"""

    try:
        response = model.generate_content(prompt)
        raw = response.text.strip()

        # Markdown va kod bloklarini tozalash
        raw = raw.replace("```", "").replace("**", "").replace("*", "").replace("#", "")
        raw = raw.strip()

        # FIX A: Bo'sh qatorlarni olib, faqat mazmunli qatorlarni olish
        lines = [line.strip() for line in raw.split("\n") if line.strip()]
        title_uz = lines[0] if lines else ""
        desc_uz = " ".join(lines[1:]) if len(lines) > 1 else ""

        result = f"{title_uz}\n{desc_uz}" if desc_uz else title_uz
        print(f"Gemini OK: {result[:80]}")
        return result

    except Exception as e:
        print(f"Gemini XATO: {type(e).__name__}: {e}")
        return None

def send_to_telegram(text, sources, links):
    # FIX A: Xavfsiz HTML parsing
    lines = [line.strip() for line in text.strip().split("\n") if line.strip()]
    title = escape_html(lines[0]) if lines else "Yangilik"
    description = escape_html(" ".join(lines[1:])) if len(lines) > 1 else ""

    sources_text = "\n".join([f"• {escape_html(s)}" for s in sources])
    main_link = links[0] if links else ""

    message = f"<b>{title}</b>"
    if description:
        message += f"\n\n{description}"
    message += f"\n\n🔗 <b>Manba:</b>\n{sources_text}"
    message += f"\n\n<a href=\"{main_link}\">Batafsil o'qish →</a>"
    message += f"\n\n─────────────────\n🚀 <i>FutureX AI News | @futurex_1984</i>"

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        resp = requests.post(url, json=payload, timeout=15)
        if resp.status_code == 200:
            print(f"Telegram OK: {title[:50]}")
            return True
        else:
            print(f"Telegram XATO {resp.status_code}: {resp.text[:200]}")
            return False
    except Exception as e:
        print(f"Telegram XATO: {e}")
        return False

def main():
    print(f"\n{'='*50}")
    print(f"FutureX AI News Aggregator")
    print(f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}\n")

    if not GEMINI_API_KEY:
        print("XATO: GEMINI_API_KEY yo'q!")
        return
    if not TELEGRAM_BOT_TOKEN:
        print("XATO: TELEGRAM_BOT_TOKEN yo'q!")
        return

    sent_news = load_sent_news()
    sent_hashes = set(sent_news)

    all_news = fetch_all_news()
    print(f"\nJami {len(all_news)} ta yangilik")

    new_news = [n for n in all_news if n["hash"] not in sent_hashes]
    print(f"Yangi: {len(new_news)} ta\n")

    if not new_news:
        print("Yangi yangilik yo'q")
        return

    groups = group_similar_news(new_news)
    print(f"Guruhlar: {len(groups)} ta\n")

    sent_count = 0
    new_hashes = []

    for group in groups[:8]:
        try:
            title = group[0]["title"]
            summary = group[0]["summary"]
            sources = list(set([n["source"] for n in group]))
            links = [n["link"] for n in group]

            translated = translate_with_gemini(title, summary)

            if not translated:
                print(f"O'tkazildi: {title[:50]}")
                continue

            if send_to_telegram(translated, sources, links):
                for n in group:
                    new_hashes.append(n["hash"])
                sent_count += 1
                time.sleep(4)

        except Exception as e:
            print(f"Xatolik: {e}")
            continue

    # FIX C: Ro'yxat hajmini nazorat qilish
    updated = (list(sent_hashes) + new_hashes)[-500:]
    save_sent_news(updated)

    print(f"\n{'='*50}")
    print(f"Natija: {sent_count} ta yangilik yuborildi!")
    print(f"{'='*50}\n")

if __name__ == "__main__":
    main()
