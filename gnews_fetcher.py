import requests

GNEWS_API_KEY = "1e33d9b872423f303ae8689e1da8fc39"

def fetch_news(query):
    if not "1e33d9b872423f303ae8689e1da8fc39" or "PUT_" in "1e33d9b872423f303ae8689e1da8fc39":
        return []

    url = "https://gnews.io/api/v4/search"
    params = {
        "q": query,
        "lang": "en",
        "max": 1,
        "apikey": GNEWS_API_KEY
    }

    r = requests.get(url, params=params)
    data = r.json()

    articles = []
    for a in data.get("articles", []):
        articles.append({
            "title": a["title"],
            "source": a["source"]["name"],
            "publishedAt": a["publishedAt"]
        })

    return articles
