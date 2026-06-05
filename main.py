import feedparser
import google.generativeai as genai
import requests
import json
import os
import hashlib
import time
import sqlite3
import html
from concurrent.futures import ThreadPoolExecutor, as_completed
from rapidfuzz import fuzz

# ============================================================
# KONFIGURATSIYA VA GLOBAL OBYEKTLAR
# ============================================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "@futurex_1984")

SOURCES_FILE = "sources.json"
DB_FILE = "futurex.db"
SIMILARITY_THRESHOLD = 65.0  # RapidFuzz uchun optimal foiz foizi

# Global ulanishlar va Gemini konfiguratsiyasi
session = requests.Session()
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-2.0-flash")

# ============================================================
# SQLITE INTERFEYSI (KESH TIZIMI)
# ============================================================
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sent_news (
            link_hash TEXT PRIMARY KEY,
            title TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # Eskirgan yozuvlarni tozalashni osonlashtirish uchun indeks
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON sent_news (timestamp)')
    conn.commit()
    conn.close()

def is_news_sent(link_hash):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM sent_news WHERE link_hash = ?', (link_hash,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

def save_sent_news(link_hash, title):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT OR IGNORE INTO sent_news (link_hash, title) VALUES (?, ?)', (link_hash, title))
        conn.commit()
    except Exception as e:
        print(f"Baza yozish xatoligi: {e}")
    finally:
        conn.close()

def get_news_hash(link):
    return hashlib.md5(link.strip().encode('utf-8')).hexdigest()

# ============================================================
# PARALLEL SKANER VA ADVANCED CLUSTERING
# ============================================================
def fetch_sources():
    if os.path.exists(SOURCES_FILE):
        with open(SOURCES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def fetch_single_source(source):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    news_items = []
    try:
        response = session.get(source["url"], headers=headers, timeout=5) # Optimallashgan timeout va session
        if response.status_code == 200:
            feed = feedparser.parse(response.content)
            for entry in feed.entries[:8]:
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                summary = entry.get("summary", entry.get("description", "")).strip()
                if title and link:
                    news_items.append({
                        "title": title,
                        "link": link,
                        "summary": summary[:600] if summary else "",
                        "source": source["name"],
                        "hash": get_news_hash(link) # Hash endi havola (link) bo'yicha
                    })
    except Exception:
        pass
    return news_items

def fetch_all_sources_parallel(sources):
    all_news = []
    with ThreadPoolExecutor(max_workers=25) as executor:
        futures = {executor.submit(fetch_single_source, src): src for src in sources}
        for future in as_completed(futures):
            all_news.extend(future.result())
    return all_news

def group_similar_news_rapidfuzz(news_list):
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
            # RapidFuzz token_set_ratio orqali aqlli taqqoslash
            if fuzz.token_set_ratio(news["title"], other["title"]) > SIMILARITY_THRESHOLD:
                group.append(other)
                used.add(j)
        groups.append(group)
    return groups

# ============================================================
# GEMINI AI - PROFESSIONAL INTAKE (Mavzular kengaytirildi)
# ============================================================
def generate_summary_with_gemini(news_group):
    titles = [n["title"] for n in news_group]
    summaries = [n["summary"] for n in news_group if n["summary"]]
    sources = list(set([n["source"] for n in news_group]))

    # Prompt kengaytirildi: Yarimo'tkazgichlar, Fond modellari, AI agentlar kiritildi
    prompt = f"""You are a deep-tech data scientist analyzing streams for the science and technology platform 'FutureX'.
Analyze the following titles and snippets to find core technological updates.

Input Data:
Titles:
{chr(10).join(f'- {t}' for t in titles)}

Summaries:
{chr(10).join(f'- {s}' for s in summaries[:2])}

Strict Protocols:
1. Topic Validation: The news MUST directly fall under these domains: Humanoid robotics, Autonomous Cyber-Physical Systems, AI Agents/Foundation Models for robotics, Edge AI, Semiconductor manufacturing & Custom Silicon, Microelectronics (Arduino, Pi, chip controllers), Space AI & Autonomous Rover navigation.
2. Filter out: General consumer electronics (smartphones, standard PCs), generic web apps, corporate financial politics, crypto, and general economy. If it doesn't match, reply with exactly: SKIP
3. Generation Style: Write an objective, concise, and highly data-driven summary in pure UZBEK language (2-3 sentences max).
4. ABSOLUTE ANTI-HYPE CONSTRAINT: Do not use clickbait or emotional wrappers. Absolutely avoid marketing hype words like "hayratlanarli", "inqilobiy", "dunyoni zabt etadi", "dahshatli yangilik". Present only scientific facts, architectural specifications, or metrics.

Uzbek Summary (or SKIP):"""

    try:
        response = gemini_model.generate_content(prompt)
        return response.text.strip(), sources
    except Exception:
        return "SKIP", sources

# ============================================================
# XAVFSIZ TELEGRAM DISPATCHER (RETRY TIZIMI VA ESCAPE BILAN)
# ============================================================
def send_to_telegram(summary, sources, links):
    sources_text = ", ".join(sources)
    main_link = links[0] if links else ""

    # HTML parslash xatolarini oldini olish uchun escape qilinadi
    safe_summary = html.escape(summary)
    safe_sources = html.escape(sources_text)

    message = f"""⚡️ <b>FUTUREX | Robotics & Deep Tech Intelligence</b>

🦾 {safe_summary}

🌐 <b>Global Intel:</b> {safe_sources}
🔗 <a href="{main_link}">Tafsilotlar (Manba) →</a>

🤖 <code>[FutureX Engine v4.0 // Production-Ready Operational]</code>"""

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHANNEL_ID, "text": message, "parse_mode": "HTML", "disable_web_page_preview": False}
    
    # 3 marta qayta urinish mexanizmi (Retries)
    for attempt in range(3):
        try:
            res = session.post(url, json=payload, timeout=5)
            if res.status_code == 200:
                return True
            if res.status_code == 429: # Telegram Rate Limit ga uchraganda kutish
                retry_after = res.json().get("parameters", {}).get("retry_after", 5)
                time.sleep(retry_after)
        except Exception:
            time.sleep(2)
    return False

# ============================================================
# KORPUS CORE EXECUTIVE
# ============================================================
def main():
    print("⚡️ FutureX Core v4.0: Production Aggregator Engine starting...")
    init_db()
    
    sources = fetch_sources()
    if not sources:
        print("❌ Xatolik: sources.json topilmadi!")
        return

    all_news = fetch_all_sources_parallel(sources)
    
    # Bazadan tekshirish (Kesh optimizatsiyasi)
    new_news = [n for n in all_news if not is_news_sent(n["hash"])]
    print(f"Skaner: {len(sources)} ta manba. Jami xabar: {len(all_news)}. Yangi oqim: {len(new_news)} ta.")

    if not new_news:
        print("Yangi tizimli yangilanish datchiklari aniqlanmadi.")
        return

    # RapidFuzz Clustering jarayoni
    groups = group_similar_news_rapidfuzz(new_news)
    sent_count = 0

    for group in groups[:10]:
        summary, sources_used = generate_summary_with_gemini(group)
        
        if summary.upper() == "SKIP" or len(summary) < 15:
            for n in group:
                save_sent_news(n["hash"], n["title"])
            continue

        links = [n["link"] for n in group]
        if send_to_telegram(summary, sources_used, links):
            for n in group:
                save_sent_news(n["hash"], n["title"])
            sent_count += 1
            print(f"🚀 FutureX kanaliga uzatildi: {sources_used}")
            time.sleep(4) # Sikllar aro xavfsiz pauza

    print(f"🤖 Sikl yakunlandi. Kanalingizga {sent_count} ta yuqori texnologik xabar joylandi.")

if __name__ == "__main__":
    main()
