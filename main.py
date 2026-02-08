import requests
import xml.etree.ElementTree as ET
import os
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

WEBHOOKS = {
    "hep-th": os.environ["WEBHOOK_HEP_TH"],
    "quant-ph": os.environ["WEBHOOK_QUANT_PH"],
}

PRIORITY = ["hep-th", "quant-ph"]

def load_keywords():
    with open("keywords.txt", "r", encoding="utf-8") as f:
        return [k.strip().lower() for k in f.readlines()]

def get_arxiv():
    url = (
        "http://export.arxiv.org/api/query?"
        "search_query=cat:hep-th+OR+cat:quant-ph"
        "&sortBy=submittedDate&max_results=10"
    )
    r = requests.get(url)
    root = ET.fromstring(r.text)
    return root.findall("{http://www.w3.org/2005/Atom}entry")

def get_categories(entry):
    cats = []
    for c in entry.findall("{http://www.w3.org/2005/Atom}category"):
        cats.append(c.attrib["term"])
    return cats

def choose_category(categories):
    for p in PRIORITY:
        if p in categories:
            return p
    return None

def summarize(text):
    prompt = f"以下の論文要旨を日本語で5行以内に要約してください:\n{text}"

    response = client.chat.completions.create(
        model="gpt-5-mini",
        messages=[{"role": "user", "content": prompt}]
    )

    return response.choices[0].message.content

def send_to_discord(webhook, category, title, summary, link, authors, published):
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
            {"name": "Published", "value": published, "inline": True},
        ],
        "footer": {
            "text": "arXiv notification bot"
        }
    }

    requests.post(webhook, json={"embeds": [embed]})

def main():
    keywords = load_keywords()
    entries = get_arxiv()

    for e in entries:
        title = e.find("{http://www.w3.org/2005/Atom}title").text
        summary = e.find("{http://www.w3.org/2005/Atom}summary").text
        link = e.find("{http://www.w3.org/2005/Atom}id").text
        
        # 著者取得（最大3人＋他）
        authors = [
            a.find("{http://www.w3.org/2005/Atom}name").text
            for a in e.findall("{http://www.w3.org/2005/Atom}author")
        ]

        if len(authors) > 3:
            author_text = ", ".join(authors[:3]) + " et al."
        else:
            author_text = ", ".join(authors)

        # 投稿日時
        published = e.find("{http://www.w3.org/2005/Atom}published").text[:10]

        categories = get_categories(e)
        target = choose_category(categories)

        if not target:
            continue

        text = (title + " " + summary).lower()

        if any(k in text for k in keywords):
            short = summarize(summary)

            message = (
                f"📘 **[{target}] {title}**\n"
                f"{short}\n{link}"
            )

            send_to_discord(
                WEBHOOKS[target],
                target,
                title,
                short,
                link,
                author_text,
                published
            )


if __name__ == "__main__":
    main()
