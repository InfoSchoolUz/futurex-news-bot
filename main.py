import feedparser
import google.generativeai as genai
import requests
import json
import os
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher

# ============================================================
# KONFIGURATSIYA
# ============================================================
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHANNEL_ID = os.environ.get("TELEGRAM_CHANNEL_ID", "@futurex_1984")

SOURCES_FILE = "sources.json"
SENT_NEWS_FILE = "sent_news.json"
SIMILARITY_THRESHOLD = 0.55

# ============================================================
# KESH VA MANBALARNI YUKLASH
# ============================================================
def load_sources():
    if os.path.exists(SOURCES_FILE):
        with open(SOURCES_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []

def load_sent_news():
    if os.path.exists(SENT_NEWS_FILE):
        with open(SENT_NEWS_FILE, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                return data if isinstance(data, list) else []
            except Exception:
                return []
    return []

def save_sent_news(sent_list):
    unique_list = list(set(sent_list))
    with open(SENT_NEWS_FILE, "w", encoding="utf-8") as f:
        json.dump(unique_list[-1000:], f, ensure_ascii=False, indent=2)

def get_news_hash(title):
    return hashlib.md5(title.lower().strip().encode('utf-8')).hexdigest()

def is_similar(title1, title2):
    return SequenceMatcher(None, title1.lower(), title2.lower()).ratio() > SIMILARITY_THRESHOLD

# ============================================================
# PARALLEL SKANER TIZIMI (KATTA STRUKTURA UCHUN)
# ============================================================
def fetch_single_source(source):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
    news_items = []
    try:
        response = requests.get(source["url"], headers=headers, timeout=10)
        if response.status_code == 200:
            feed = feedparser.parse(response.content)
            for entry in feed.entries[:8]:  # Har bir saytdan eng yangi 8 tasi
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                summary = entry.get("summary", entry.get("description", "")).strip()
                if title and link:
                    news_items.append({
                        "title": title,
                        "link": link,
                        "summary": summary[:600] if summary else "",
                        "source": source["name"],
                        "hash": get_news_hash(title)
                    })
    except Exception:
        pass  # Nosoz saytlar butun tizimni to'xtatib qo'ymaydi
    return news_items

def fetch_all_sources_parallel(sources):
    all_news = []
    # 20 ta parallel potokda ishlash (100+ saytni bir necha soniyada yig'adi)
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(fetch_single_source, src): src for src in sources}
        for future in as_completed(futures):
            all_news.extend(future.result())
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

# ============================================================
# GEMINI AI - SOF MUHANDISLIK SŪZGICHI (BO'RTTIRISHLARSIZ)
# ============================================================
def generate_summary_with_gemini(news_group):
    genai.configure(api_key=GEMINI_API_KEY)
    model = genai.GenerativeModel("gemini-2.0-flash")

    titles = [n["title"] for n in news_group]
    summaries = [n["summary"] for n in news_group if n["summary"]]
    sources = list(set([n["source"] for n in news_group]))

    prompt = f"""You are an advanced AI data aggregation engine for the high-tech science channel 'FutureX'.
Analyze the following multi-language titles and snippets to find deep tech, robotics, or space AI content.

Input Stream:
Titles:
{chr(10).join(f'- {t}' for t in titles)}

Summaries:
{chr(10).join(f'- {s}' for s in summaries[:2])}

Strict Processing Protocols:
1. Topic Validation: The news MUST be about either: microelectronics/hardware components (like Arduino, custom silicon, sensory controllers), advanced bipedal or physical robotics (like NEO, Optimus, Boston Dynamics), industrial automated physical networks, or space science utilizing Artificial Intelligence / autonomous navigation systems.
2. If it does NOT strictly match, or if it is general gadget hype, software apps, or economic news, reply with EXACTLY: SKIP
3. Language and Tone: Write a professional, data-driven analytical summary in pure UZBEK language (2-3 sentences max).
4. ANTI-HYPE RULE: Avoid emotional exaggeration or clickbait. Do not use phrases like "hayratlanarli", "inqilobiy", "dunyoni ag'darib tashlaydi". State only factual achievements, specs, or empirical metrics.

Uzbek Summary (or SKIP):"""

    try:
        response = model.generate_content(prompt)
        return response.text.strip(), sources
    except Exception:
        return "SKIP", sources

# ============================================================
# TELEGRAM DISPATCHER
# ============================================================
def send_to_telegram(summary, sources, links):
    sources_text = ", ".join(sources)
    main_link = links[0] if links else ""

    message = f"""⚡️ <b>FUTUREX | Robotics & Deep Tech Intelligence</b>

🦾 {summary}

🌐 <b>Global Intel:</b> {sources_text}
🔗 <a href="{main_link}">Tafsilotlar (Manba) →</a>

🤖 <code>[FutureX Engine v3.0 // Autonomous Mass-Aggregation]</code>"""

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHANNEL_ID, "text": message, "parse_mode": "HTML", "disable_web_page_preview": False}
    try:
        res = requests.post(url, json=payload)
        return res.status_code == 200
    except Exception:
        return False

# ============================================================
# MAIN CORE
# ============================================================
def main():
    print("⚡️ FutureX Core v3.0: Mass-Aggregation Engine initiated...")
    
    sources = load_sources()
    if not sources:
        print("❌ Error: sources.json fayli bo'sh yoki topilmadi!")
        return

    sent_news = load_sent_news()
    print(f"Skanerlanayotgan manbalar soni: {len(sources)}")
    
    all_news = fetch_all_sources_parallel(sources)
    new_news = [n for n in all_news if n["hash"] not in sent_news]
    print(f"Jami ma'lumotlar oqimi: {len(all_news)} ta xabar. Yangi oqimlar: {len(new_news)} ta.")

    if not new_news:
        print("Yangi axborot datchiklari aniqlanmadi.")
        return

    groups = group_similar_news(new_news)
    sent_count = 0

    for group in groups[:10]:  # Har bir aylanishda maksimal 10 ta eng muhim guruhlangan xabar
        summary, sources_used = generate_summary_with_gemini(group)
        
        if summary.upper() == "SKIP" or len(summary) < 15:
            for n in group:
                sent_news.append(n["hash"])
            continue

        links = [n["link"] for n in group]
        if send_to_telegram(summary, sources_used, links):
            for n in group:
                sent_news.append(n["hash"])
            sent_count += 1
            print(f"🚀 Kanalga joylandi: {sources_used}")
            time.sleep(4)

    save_sent_news(sent_news)
    print(f"🤖 Sikl yakunlandi. FutureX kanaliga {sent_count} ta yangilik uzatildi.")

if __name__ == "__main__":
    main()
