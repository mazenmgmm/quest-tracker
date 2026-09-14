import json
import os
import sys
from datetime import datetime, timezone
from functools import lru_cache

import requests

QUEST_URL = "https://raw.githubusercontent.com/xGustavvo/discord-api-tracker/refs/heads/main/quest.json"
REGION_URL = "https://api.discordquest.com/api/regions"

STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "known_quests.json")

TASK_MAP = {
    "WATCH_VIDEO": "Video",
    "WATCH_VIDEO_ON_MOBILE": "Mobile (Video)",
    "PLAY_ON_DESKTOP": "Desktop",
    "PLAY_ON_XBOX": "Xbox",
    "PLAY_ON_PLAYSTATION": "PlayStation",
    "PLAY_ACTIVITY": "Activity",
    "STREAM_ON_DESKTOP": "Desktop (Stream)",
    "win": "Win",
}

REWARD_TYPE_NAMES = {
    1: "Code",
    2: "In-Game",
    3: "Avatar Decoration",
    4: "Orbs",
    5: "Nitro",
}

FEATURE_NAMES = {
    3: "ACTIVITY_QUEST_AUTO_ENROLLMENT",
    9: "MOBILE_ACTIVITY_QUEST",
    14: "QUESTS_CDN",
    15: "PACING_CONTROLLER",
    16: "QUEST_HOME_FORCE_STATIC_IMAGE",
    17: "VIDEO_QUEST_FORCE_HLS_VIDEO",
    18: "VIDEO_QUEST_FORCE_END_CARD_CTA_SWAP",
    # dont think any more is needed (for now)
}


# Names match the country selectors in VPN apps; UK is normalized to GB.
COUNTRY_NAMES = {
    "AE": ("United Arab Emirates", "الإمارات"),
    "AR": ("Argentina", "الأرجنتين"),
    "AT": ("Austria", "النمسا"),
    "AU": ("Australia", "أستراليا"),
    "BE": ("Belgium", "بلجيكا"),
    "BR": ("Brazil", "البرازيل"),
    "CA": ("Canada", "كندا"),
    "CH": ("Switzerland", "سويسرا"),
    "CL": ("Chile", "تشيلي"),
    "CN": ("China", "الصين"),
    "CO": ("Colombia", "كولومبيا"),
    "CZ": ("Czechia", "التشيك"),
    "DE": ("Germany", "ألمانيا"),
    "DK": ("Denmark", "الدنمارك"),
    "EG": ("Egypt", "مصر"),
    "ES": ("Spain", "إسبانيا"),
    "FI": ("Finland", "فنلندا"),
    "FR": ("France", "فرنسا"),
    "GB": ("United Kingdom", "بريطانيا"),
    "GR": ("Greece", "اليونان"),
    "HK": ("Hong Kong", "هونغ كونغ"),
    "HU": ("Hungary", "المجر"),
    "ID": ("Indonesia", "إندونيسيا"),
    "IE": ("Ireland", "أيرلندا"),
    "IL": ("Israel", "إسرائيل"),
    "IN": ("India", "الهند"),
    "IT": ("Italy", "إيطاليا"),
    "JP": ("Japan", "اليابان"),
    "KR": ("South Korea", "كوريا الجنوبية"),
    "MX": ("Mexico", "المكسيك"),
    "MY": ("Malaysia", "ماليزيا"),
    "NL": ("Netherlands", "هولندا"),
    "NO": ("Norway", "النرويج"),
    "NZ": ("New Zealand", "نيوزيلندا"),
    "PE": ("Peru", "بيرو"),
    "PH": ("Philippines", "الفلبين"),
    "PK": ("Pakistan", "باكستان"),
    "PL": ("Poland", "بولندا"),
    "PT": ("Portugal", "البرتغال"),
    "RO": ("Romania", "رومانيا"),
    "RU": ("Russia", "روسيا"),
    "SA": ("Saudi Arabia", "السعودية"),
    "SE": ("Sweden", "السويد"),
    "SG": ("Singapore", "سنغافورة"),
    "TH": ("Thailand", "تايلاند"),
    "TR": ("Turkey", "تركيا"),
    "TW": ("Taiwan", "تايوان"),
    "UA": ("Ukraine", "أوكرانيا"),
    "US": ("United States", "أمريكا"),
    "VN": ("Vietnam", "فيتنام"),
    "ZA": ("South Africa", "جنوب أفريقيا"),
}


def build_region_index(data):
    rows = data.get("quests") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        raise ValueError("Invalid region data")
    index = {
        str(row["id"]): row
        for row in rows
        if isinstance(row, dict) and row.get("id")
    }
    # A replacement inherits the old record only when it has no own record.
    for row in list(index.values()):
        if row.get("replacement_id"):
            index.setdefault(str(row["replacement_id"]), row)
    return index


@lru_cache(maxsize=1)
def load_region_index():
    try:
        response = requests.get(REGION_URL, timeout=12)
        response.raise_for_status()
        return build_region_index(response.json())
    except (requests.RequestException, ValueError, TypeError):
        print("Region data unavailable; country labels will show Unknown.", file=sys.stderr)
        return {}


def normalize_country_codes(values):
    if not isinstance(values, list):
        return []
    codes = set()
    for value in values:
        if not isinstance(value, str):
            continue
        code = value.strip().upper()
        code = {"UK": "GB", "EL": "GR"}.get(code, code)
        if len(code) == 2 and code.isascii() and code.isalpha():
            codes.add(code)
    return sorted(codes)


def country_label(code, bilingual=False):
    flag = "".join(chr(127397 + ord(char)) for char in code)
    english, arabic = COUNTRY_NAMES.get(code, (code, code))
    if bilingual and arabic != english:
        return f"{flag} {arabic} ({english})"
    return f"{flag} {english}"


def country_details(quest_id, region_index=None):
    index = load_region_index() if region_index is None else region_index
    record = index.get(str(quest_id))
    unknown = ("❔ Unknown", "❔ غير معروف — بيانات الدولة غير متاحة حاليًا.")
    if not isinstance(record, dict):
        return unknown
    regions = record.get("regions")
    if isinstance(regions, list):
        included = normalize_country_codes(regions)
        excluded = []
    elif isinstance(regions, dict):
        included = normalize_country_codes(regions.get("include"))
        excluded = normalize_country_codes(regions.get("exclude"))
    else:
        included, excluded = [], []
    if included:
        allowed = [code for code in included if code not in excluded]
        if not allowed:
            return unknown
        short = " / ".join(country_label(code) for code in allowed[:3])
        if len(allowed) > 3:
            short += f" +{len(allowed) - 3}"
        detail = "\n".join(country_label(code, bilingual=True) for code in allowed)
        if len(allowed) > 1:
            detail = "متاحة في إحدى هذه الدول:\n" + detail
        return short, detail
    if excluded:
        detail = "\n".join(country_label(code, bilingual=True) for code in excluded)
        if record.get("is_global") is True:
            return "🌍 Global (exceptions)", "🌍 عالمية، باستثناء:\n" + detail
        return "🌍 Region restrictions", "الدول المستثناة:\n" + detail + "\nالدول المتاحة غير محددة."
    if record.get("is_global") is True:
        return "🌍 Global", "🌍 عالمية (Global)"
    return unknown


def fetch_json(url):
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.json()


def normalize_quest(q):
    if q.get("config"):
        return q
    messages = q.get("messages") or {}
    return {
        "id": q.get("id"),
        "config": {
            "starts_at": q.get("starts_at"),
            "expires_at": q.get("expires_at"),
            "messages": {
                "quest_name": messages.get("quest_name")
                or messages.get("game_title")
                or "Unknown Quest"
            },
            "task_config_v2": q.get("task_config_v2"),
            "rewards_config": q.get("rewards_config"),
        },
    }


def load_all_quests():
    data = fetch_json(QUEST_URL)
    if not isinstance(data, list):
        return {}

    data_map = {}
    for q in data:
        nq = normalize_quest(q)
        if nq.get("id"):
            data_map[nq["id"]] = nq
    return data_map


def get_rewards(q):
    cfg = q.get("config") or {}
    rc = cfg.get("rewards_config") or {}
    return rc.get("rewards") or cfg.get("rewards") or []


def get_tasks(cfg):
    return (
        (cfg.get("task_config_v2") or {}).get("tasks")
        or (cfg.get("task_config") or {}).get("tasks")
        or {}
    )


def task_name(t):
    ttype = t.get("type") or t.get("event_name")
    if ttype == "ACHIEVEMENT_IN_ACTIVITY":
        return "Achievement (Activity)"
    if ttype == "ACHIEVEMENT_IN_GAME":
        return "Achievement (Game)"
    return TASK_MAP.get(ttype, ttype or "None")


def to_discord_ts(iso, style="R"):
    if not iso:
        return "?"
    try:
        dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        return f"<t:{int(dt.timestamp())}:{style}>"
    except Exception:
        return "?"


def format_date_range(starts_at, expires_at):
    """Return absolute date range as 'DD/MM/YYYY - DD/MM/YYYY'."""
    if not starts_at or not expires_at:
        return "Unknown"
    try:
        start = datetime.fromisoformat(str(starts_at).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
        return f"{start.strftime('%d/%m/%Y')} - {end.strftime('%d/%m/%Y')}"
    except Exception:
        return "Unknown"


def build_embed(quest, region_index=None):
    qid = quest["id"]
    cfg = quest.get("config") or {}
    messages = cfg.get("messages") or {}
    app = cfg.get("application") or {}
    assets = cfg.get("assets") or {}

    # basic info about the quest
    name = messages.get("quest_name", "Unknown Quest")
    country_title, country_text = country_details(qid, region_index)
    if len(country_text) > 1024:
        country_text = country_text[:1021] + "..."
    title_suffix = f" | {country_title}"
    quest_title = f"🆕 New Quest: {name}"
    title = quest_title[:256 - len(title_suffix)] + title_suffix
    starts_at = cfg.get("starts_at")
    expires_at = cfg.get("expires_at")

    # game + app id
    game_title = messages.get("game_title") or app.get("name") or "Unknown Game"
    app_id = app.get("id")
    extra_desc = (
        messages.get("description")
        or (cfg.get("cta_config") or {}).get("description")
        or ""
    )

    # features listing
    features = cfg.get("features", [])
    feature_names = [FEATURE_NAMES.get(f, f"Unknown({f})") for f in features]
    feature_text = ", ".join(feature_names) if feature_names else "None"

    # rewards
    rewards = get_rewards(quest)
    reward_lines = []
    for r in rewards:
        rname = (r.get("messages") or {}).get("name") or r.get("name")
        rtype = REWARD_TYPE_NAMES.get(r.get("type"), "Reward")
        qty = r.get("orb_quantity")
        line = f"{rname} ({rtype})" if rname else rtype
        if qty:
            line += f" x{qty}"
        reward_lines.append(line)
    reward_text = "\n".join(reward_lines) if reward_lines else "No reward data"

    # tasks
    tasks = get_tasks(cfg)
    task_names = [task_name(t) for t in tasks.values()] if tasks else []
    task_text = " / ".join(task_names) if task_names else "None"

    duration = (
        f"{to_discord_ts(starts_at)} – {to_discord_ts(expires_at)}\n"
        f"(absolute: {format_date_range(starts_at, expires_at)})"
    )

    # embed fieldz
    fields = [
        {"name": "🌍 Country / الدولة", "value": country_text, "inline": False},
        {"name": "Duration", "value": duration, "inline": False},
        {"name": "Game", "value": game_title, "inline": True},
        {"name": "Application", "value": app_id or "N/A", "inline": True},
        {"name": "Features", "value": feature_text, "inline": False},
        {"name": "Reward(s)", "value": reward_text, "inline": False},
        {"name": "Task(s)", "value": task_text, "inline": False},
    ]

    # if the quest gives extra stuff
    if extra_desc:
        fields.insert(2, {"name": "Description", "value": extra_desc, "inline": False})

    embed = {
        "title": title,
        "url": f"https://discord.com/quests/{qid}",
        "color": 0x5865F2,
        "fields": fields,
        "footer": {"text": f"Quest ID: {qid}"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    # thumbnailing
    game_tile = assets.get("game_tile")
    if game_tile and isinstance(game_tile, str) and game_tile.startswith("http"):
        embed["thumbnail"] = {"url": game_tile}

    return embed


def embed_text_length(embed):
    total = len(embed.get("title", "")) + len(embed.get("description", ""))
    total += len((embed.get("footer") or {}).get("text", ""))
    total += len((embed.get("author") or {}).get("name", ""))
    return total + sum(len(field["name"]) + len(field["value"]) for field in embed.get("fields", []))


def webhook_batches(embeds):
    batch, size = [], 0
    for embed in embeds:
        length = embed_text_length(embed)
        if length > 6000:
            raise ValueError("A quest exceeds Discord's embed text limit")
        if batch and (len(batch) == 10 or size + length > 6000):
            yield batch
            batch, size = [], 0
        batch.append(embed)
        size += length
    if batch:
        yield batch


def send_webhook(webhook_url, embeds):
    # Country lists count toward Discord's per-message embed text limit.
    batches = list(webhook_batches(embeds))
    for chunk in batches:
        try:
            resp = requests.post(
                webhook_url,
                json={"embeds": chunk, "allowed_mentions": {"parse": []}},
                timeout=30,
            )
        except requests.RequestException as error:
            raise RuntimeError(f"Discord request failed ({type(error).__name__})") from None
        if not 200 <= resp.status_code < 300:
            # Keep the previous state so an unsuccessful delivery can be retried.
            raise RuntimeError(f"Discord webhook returned HTTP {resp.status_code}")


def load_state():
    if not os.path.exists(STATE_PATH):
        return None
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except Exception:
            return None


def save_state(ids):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(sorted(ids), f, indent=2)
        f.write("\n")


def main():
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL")
    if not webhook_url:
        print("DISCORD_WEBHOOK_URL not set", file=sys.stderr)
        sys.exit(1)

    quests = load_all_quests()
    current_ids = set(quests.keys())

    previous_ids = load_state()

    if previous_ids is None:
        # first run thingys
        save_state(current_ids)
        print(f"Baseline created with {len(current_ids)} quests. No notifications sent.")
        return

    previous_ids = set(previous_ids)
    new_ids = current_ids - previous_ids

    if new_ids:
        embeds = [build_embed(quests[qid]) for qid in new_ids if qid in quests]
        if embeds:
            send_webhook(webhook_url, embeds)
            print(f"Sent notifications for {len(embeds)} new quest(s): {', '.join(new_ids)}")
    else:
        print("No new quests.")

    save_state(current_ids)


if __name__ == "__main__":
    main()
