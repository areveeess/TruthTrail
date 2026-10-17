import uuid
import random
from datetime import datetime, timedelta
from users import USERS

def create_root_event(article):
    return {
        "event_id": str(uuid.uuid4()),
        "platform": "news",
        "content_id": article["title"],
        "parent_event_id": None,
        "user_id": article["source"],
        "timestamp": article["publishedAt"],
        "user_influence": 90
    }

def simulate_spread(root, risk):
    events = [root]
    base = datetime.fromisoformat(root["timestamp"].replace("Z",""))

    spread = 6 if risk == "High" else 3

    for platform, users in USERS.items():
        parent = root
        for _ in range(spread):
            u = random.choice(users)
            event = {
                "event_id": str(uuid.uuid4()),
                "platform": platform,
                "content_id": root["content_id"],
                "parent_event_id": parent["event_id"],
                "user_id": u["id"],
                "timestamp": (base + timedelta(minutes=random.randint(5,60))).isoformat(),
                "user_influence": u["influence"]
            }
            events.append(event)
            parent = event

    return events
