import time
import requests
import xml.etree.ElementTree as ET
import os
from datetime import datetime
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

WEBHOOKS = {
    "hep-th": os.environ["WEBHOOK_HEP_TH"],
    "quant-ph": os.environ["WEBHOOK_QUANT_PH"],
}

PRIORITY = ["hep-th", "quant-ph"]

ATOM = "{http://www.w3.org/2005/Atom}"


# -----------------------------
# Keywords
# -----------------------------
def load_keywords():
    with open("keywords.txt", "r", encoding="utf-8") as f:
        return [
            line.strip().lower()
            for line in f
            if line.strip()  # ← 空行を無視
        ]


def find_matching_keywords(text, keywords):
    text = text.lower()
    return [k for k in keywords if k in text]


# -----------------------------
# arXiv API
# -----------------------------
def get_arxiv():
    url = "https://export.arxiv.org/api/query?search_query=cat:hep-th+OR+cat:quant-ph&sortBy=submittedDate&sortOrder=descending&max_results=30"

    headers = {"User-Agent": "arxiv-discord-bot/1.0"}

    for attempt in range(3):
        try:
            print(f"arXiv request attempt {attempt+1}")

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

    print("arXiv request failed after retries.")
    return []


def get_categories(entry):
    return [
        c.attrib["term"]
        for c in entry.findall(f"{ATOM}category")
    ]


def choose_category(categories):
    for p in PRIORITY:
        if p in categories:
            return p
    return None


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
        "quant-ph": 0x2ecc71,
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


def send_zero_message(counts):
    today = datetime.now().strftime("%Y-%m-%d")

    for cat, webhook in WEBHOOKS.items():
        if counts[cat] == 0:
            msg = f"📭 {today}：該当論文は0件でした"
            requests.post(webhook, json={"content": msg})


# -----------------------------
# Main
# -----------------------------
def main():
    keywords = load_keywords()
    entries = get_arxiv()

    posted_counts = {k: 0 for k in WEBHOOKS}

    for e in entries:

        title = e.find(f"{ATOM}title").text.strip()
        summary = e.find(f"{ATOM}summary").text.strip()
        link = e.find(f"{ATOM}id").text.strip()

        # 著者
        authors = [
            a.find(f"{ATOM}name").text
            for a in e.findall(f"{ATOM}author")
        ]

        author_text = (
            ", ".join(authors[:3]) + " et al."
            if len(authors) > 3
            else ", ".join(authors)
        )

        # 投稿日
        published = e.find(f"{ATOM}published").text[:10]

        categories = get_categories(e)
        target = choose_category(categories)

        if not target:
            continue

        text = (title + " " + summary).lower()

        matched = find_matching_keywords(text, keywords)

        if not matched:
            continue

        short = summarize(summary)

        send_to_discord(
            WEBHOOKS[target],
            target,
            title,
            short,
            link,
            author_text,
            published,
            matched
        )

        posted_counts[target] += 1

    # 0件通知
    send_zero_message(posted_counts)


if __name__ == "__main__":
    main()
