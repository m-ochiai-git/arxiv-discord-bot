import time
import requests
import xml.etree.ElementTree as ET
import os
from datetime import datetime
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

WEBHOOKS = {
    "hep-th": os.environ["WEBHOOK_HEP_TH"],
    "hep-ph": os.environ["WEBHOOK_HEP_PH"],
    "quant-ph": os.environ["WEBHOOK_QUANT_PH"]
}

CATEGORIES = list(WEBHOOKS.keys())

MAX_RESULTS = {
    "hep-th": 100,
    "hep-ph": 100,
    "quant-ph": 200
}

ATOM = "{http://www.w3.org/2005/Atom}"


# -----------------------------
# Keywords
# -----------------------------
def load_keywords():
    with open("keywords.txt", "r", encoding="utf-8") as f:
        return [
            line.strip().lower()
            for line in f
            if line.strip()
        ]


def find_matching_keywords(text, keywords):
    text = text.lower()
    return [k for k in keywords if k in text]


# -----------------------------
# arXiv API
# -----------------------------
def get_arxiv(category):

    max_results = MAX_RESULTS.get(category, 30)

    url = (
        "https://export.arxiv.org/api/query?"
        f"search_query=cat:{category}"
        "&sortBy=submittedDate"
        "&sortOrder=descending"
        f"&max_results={max_results}"
    )

    headers = {"User-Agent": "arxiv-discord-bot/1.0"}

    for attempt in range(3):
        try:
            print(f"[{category}] arXiv request attempt {attempt+1}")

            r = requests.get(url, headers=headers, timeout=60)

            if r.status_code != 200:
                print("Bad status:", r.status_code)
                time.sleep(5)
                continue

            root = ET.fromstring(r.text)
            return root.findall(f"{ATOM}entry")

        except requests.exceptions.RequestException as e:
            print("Request error:", e)
            time.sleep(5)

        except ET.ParseError as e:
            print("XML parse error:", e)
            time.sleep(5)

    print(f"[{category}] arXiv request failed after retries.")
    return []


# -----------------------------
# GPT summary
# -----------------------------
def summarize(text):
    try:
        prompt = f"以下の論文要旨を日本語で3行以内に要約してください:\n{text}"

        response = client.chat.completions.create(
            model="gpt-5-mini",
            messages=[{"role": "user", "content": prompt}]
        )

        return response.choices[0].message.content

    except Exception as e:
        print("GPT error:", e)
        return "（要約の取得に失敗しました）"


# -----------------------------
# Discord
# -----------------------------
def send_to_discord(webhook, category, title, summary,
                    link, authors,
                    published, matched_keywords):

    colors = {
        "hep-th": 0x3498db,
        "hep-ph": 0x948bdb,
        "quant-ph": 0x2ecc71,
        "cond-matt": 0xe67e22,
    }

    embed = {
        "title": f"[{category}] {title}",
        "description": summary,
        "url": link,
        "color": colors.get(category, 0xffffff),
        "fields": [
            {"name": "Authors", "value": authors, "inline": False},
            {"name": "Submitted", "value": published, "inline": True},
            {
                "name": "Matched keywords",
                "value": ", ".join(matched_keywords),
                "inline": False
            },
        ],
        "footer": {"text": "arXiv notification bot"}
    }

    requests.post(webhook, json={"embeds": [embed]})


def send_zero_message(category, count):
    if count == 0:
        today = datetime.now().strftime("%Y-%m-%d")
        msg = f"📭 {today}：該当論文は0件でした"
        requests.post(WEBHOOKS[category], json={"content": msg})


# -----------------------------
# Main
# -----------------------------
def main():
    keywords = load_keywords()

    for category in CATEGORIES:

        entries = get_arxiv(category)
        posted_count = 0

        for e in entries:

            title = e.find(f"{ATOM}title").text.strip()
            summary = e.find(f"{ATOM}summary").text.strip()
            link = e.find(f"{ATOM}id").text.strip()

            authors = [
                a.find(f"{ATOM}name").text
                for a in e.findall(f"{ATOM}author")
            ]

            author_text = (
                ", ".join(authors[:3]) + " et al."
                if len(authors) > 3
                else ", ".join(authors)
            )

            published = e.find(f"{ATOM}published").text[:10]

            text = (title + " " + summary).lower()
            matched = find_matching_keywords(text, keywords)

            if not matched:
                continue

            short = summarize(summary)

            send_to_discord(
                WEBHOOKS[category],
                category,
                title,
                short,
                link,
                author_text,
                published,
                matched
            )

            posted_count += 1

        # カテゴリ別 0件通知
        send_zero_message(category, posted_count)


if __name__ == "__main__":
    main()
