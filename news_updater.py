import os
import re
import asyncio
import xml.etree.ElementTree as ET
from datetime import datetime
from anthropic import Anthropic
from github import Github
import httpx

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = "coreli777/crypto-site"
MAX_NEWS = 8

RSS_SOURCES = [
    {"url": "https://cointelegraph.com/rss", "category": "Крипто"},
    {"url": "https://coindesk.com/arc/outboundfeeds/rss/", "category": "Биткоин"},
    {"url": "https://decrypt.co/feed", "category": "Блокчейн"},
]

client = Anthropic(api_key=ANTHROPIC_KEY)

async def fetch_rss(url: str) -> list:
    try:
        async with httpx.AsyncClient(timeout=15, headers={"User-Agent": "Mozilla/5.0"}) as c:
            r = await c.get(url)
            root = ET.fromstring(r.text)
            items = []
            for item in root.findall(".//item")[:3]:
                title = item.find("title")
                link = item.find("link")
                pub_date = item.find("pubDate")
                if title is not None and link is not None:
                    items.append({
                        "title": title.text or "",
                        "link": link.text or "",
                        "date": pub_date.text if pub_date is not None else ""
                    })
            return items
    except Exception as e:
        print(f"RSS error {url}: {e}")
        return []

def translate_title(title: str) -> str:
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{
                "role": "user",
                "content": f"Переведи заголовок новости о криптовалютах на русский. Верни ТОЛЬКО перевод без пояснений.\n\n{title}"
            }]
        )
        return response.content[0].text.strip()
    except Exception as e:
        print(f"Translation error: {e}")
        return title

def format_date(date_str: str) -> str:
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(date_str)
        now = datetime.now(dt.tzinfo)
        diff = now - dt
        if diff.days == 0:
            hours = diff.seconds // 3600
            if hours == 0:
                return "только что"
            return f"{hours} час{'а' if 2 <= hours <= 4 else 'ов' if hours >= 5 else ''} назад"
        elif diff.days == 1:
            return "1 день назад"
        elif diff.days < 7:
            return f"{diff.days} дн{'я' if 2 <= diff.days <= 4 else 'ей'} назад"
        else:
            return dt.strftime("%d.%m.%Y")
    except:
        return "Недавно"

def build_news_html(news_items: list) -> str:
    """Строим HTML точно по структуре вашего сайта"""
    html = '<ul class="news-list">\n'
    for item in news_items[:MAX_NEWS]:
        html += f'''    <li>
  <span class="news-tag">{item["category"]}</span>
  <span class="news-date">{item["date_formatted"]}</span>
  <a href="{item["link"]}" target="_blank" class="news-title">{item["title_ru"]}</a>
</li>\n'''
    html += '  </ul>'
    return html

def update_html(html_content: str, new_news_html: str) -> str:
    """Заменяем весь блок <ul class="news-list">...</ul>"""
    pattern = r'<ul class="news-list">.*?</ul>'
    if re.search(pattern, html_content, re.DOTALL):
        updated = re.sub(pattern, new_news_html, html_content, flags=re.DOTALL)
        print("✅ Блок новостей обновлён!")
        return updated
    else:
        print("❌ Блок news-list не найден в index.html")
        return html_content

async def main():
    print(f"🚀 Старт обновления новостей — {datetime.now().strftime('%d.%m.%Y %H:%M')}")

    # 1. Собираем новости
    all_news = []
    for source in RSS_SOURCES:
        print(f"📡 Читаем: {source['url']}")
        items = await fetch_rss(source["url"])
        for item in items:
            item["category"] = source["category"]
            all_news.append(item)

    if not all_news:
        print("❌ Новости не найдены")
        return

    print(f"✅ Найдено {len(all_news)} новостей")

    # 2. Переводим
    for item in all_news[:MAX_NEWS]:
        print(f"🔄 Перевожу: {item['title'][:60]}...")
        item["title_ru"] = translate_title(item["title"])
        item["date_formatted"] = format_date(item.get("date", ""))

    # 3. Строим HTML
    new_html = build_news_html(all_news)

    # 4. Обновляем GitHub
    print("📤 Обновляем GitHub...")
    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(GITHUB_REPO)
    file = repo.get_contents("index.html")
    current = file.decoded_content.decode("utf-8")
    updated = update_html(current, new_html)

    if updated != current:
        repo.update_file(
            path="index.html",
            message=f"🤖 Новости обновлены {datetime.now().strftime('%d.%m.%Y %H:%M')}",
            content=updated,
            sha=file.sha
        )
        print("✅ Готово! Сайт обновится через 1-2 минуты.")
    else:
        print("ℹ️ Новостей для обновления нет")

if __name__ == "__main__":
    asyncio.run(main())
