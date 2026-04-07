"""
CricHeroes Data Fetcher — Dugout Devils
Fetches data from all available APIs:
  1. /stats.json        → team stats (W/L/Win%)
  2. /matches.json      → match history + upcoming
  3. /members.json      → squad roster with photos
  4. REST API           → match photos gallery

HOW TO GET YOUR COOKIES (one-time setup):
  1. Open https://cricheroes.com/team-profile/11061119/dugout-devils/matches in Chrome
  2. DevTools → Network → find any .json request
  3. Right-click → Copy → Copy as cURL
  4. Extract cookie values from -b '...' part

FOR GITHUB ACTIONS — set these repository secrets:
  CRICHEROES_UDID   → value of udid cookie  (stable)
  CRICHEROES_CF_BM  → value of __cf_bm      (update monthly)
"""

import os
import requests
import json
import re
import time
from datetime import datetime, timezone

# ─────────────────────────────────────────────
# CONFIG — reads env vars first, then fallback
# ─────────────────────────────────────────────
UDID   = os.environ.get("CRICHEROES_UDID",   "d366e93bfc229d57553a4cd0461e1656")
CF_BM  = os.environ.get("CRICHEROES_CF_BM",  "")   # leave blank → script tries without it

COOKIES = {"udid": UDID}
if CF_BM:
    COOKIES["__cf_bm"] = CF_BM

TEAM_ID   = "11061119"
TEAM_SLUG = "dugout-devils"
BASE      = "https://cricheroes.com"
API_BASE  = "https://api.cricheroes.in"
API_KEY   = "cr!CkH3r0s"   # public API key found in browser requests

NEXT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "en-GB,en;q=0.7",
    "X-Nextjs-Data": "1",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Sec-GPC": "1",
}

# Separate session for the REST API (api.cricheroes.in)
rest_session = requests.Session()
rest_session.headers.update({
    "User-Agent": NEXT_HEADERS["User-Agent"],
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-GB,en;q=0.7",
    "api-key": API_KEY,
    "udid": UDID,
    "device-type": "Chrome: 144.0.0.0",   # ← required by the REST API
    "Origin": "https://cricheroes.com",
    "Referer": "https://cricheroes.com/",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "cross-site",
    "Sec-GPC": "1",
})

next_session = requests.Session()
next_session.headers.update(NEXT_HEADERS)
next_session.cookies.update(COOKIES)


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def section(title):
    print(f"\n{'═' * 62}")
    print(f"  {title}")
    print(f"{'═' * 62}")


def fmt_date(iso: str) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%d %b %Y")
    except Exception:
        return str(iso)[:10]


# ─────────────────────────────────────────────
# Auto-detect buildId from page HTML (with fallback)
# ─────────────────────────────────────────────

OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dugout_devils_data.json")

def _cached_build_id() -> str:
    """Read the last successfully cached buildId from the local JSON."""
    try:
        with open(OUT_PATH) as f:
            return json.load(f).get("buildId", "")
    except Exception:
        return ""


def get_build_id() -> str:
    """Try to scrape buildId from the page. On 403/network error, use cached value."""
    url = f"{BASE}/team-profile/{TEAM_ID}/{TEAM_SLUG}/matches"
    try:
        r = next_session.get(url, timeout=15)
        r.raise_for_status()
        m = re.search(r'"buildId":"([^"]+)"', r.text)
        if m:
            return m.group(1)
        print("  ⚠️  Could not parse buildId from HTML — trying cached value")
    except Exception as e:
        print(f"  ⚠️  HTML fetch blocked ({e}) — trying cached buildId")

    cached = _cached_build_id()
    if cached:
        print(f"  🔄  Using cached buildId: {cached}")
        return cached

    raise ValueError("No buildId available — run locally first to populate cache")


# ─────────────────────────────────────────────
# _next/data tab fetcher
# ─────────────────────────────────────────────

def fetch_tab(build_id: str, tab: str) -> dict:
    url = (
        f"{BASE}/_next/data/{build_id}/team-profile/"
        f"{TEAM_ID}/{TEAM_SLUG}/{tab}.json"
        f"?teamId={TEAM_ID}&teamName={TEAM_SLUG}&tabName={tab}"
    )
    next_session.headers["Referer"] = f"{BASE}/team-profile/{TEAM_ID}/{TEAM_SLUG}/{tab}"
    r = next_session.get(url, timeout=15)
    r.raise_for_status()
    return r.json().get("pageProps", {})


# ─────────────────────────────────────────────
# Photos REST API  (api.cricheroes.in)
# ─────────────────────────────────────────────

def fetch_photos(page_size: int = 24) -> list:
    # Try both URL formats — browser DevTools sometimes omits the '?'
    urls = [
        f"{API_BASE}/api/v1/team/get-team-match-photo/{TEAM_ID}?pageSize={page_size}",
        f"{API_BASE}/api/v1/team/get-team-match-photo/{TEAM_ID}pageSize={page_size}",
    ]
    for url in urls:
        try:
            r = rest_session.get(url, timeout=15)
            r.raise_for_status()
            data = r.json()
            if data.get("status"):
                return data.get("data", [])
            print(f"  ⚠️  Photos status:false → {url}")
            print(f"       Response: {str(data)[:300]}")
        except Exception as e:
            print(f"  ⚠️  Photos failed ({url}): {e}")
    return []


# ─────────────────────────────────────────────
# PRINT HELPERS
# ─────────────────────────────────────────────

def print_profile(props: dict):
    section("🏏 TEAM PROFILE")
    team = props.get("teamDetails", {}).get("data", {})
    print(f"  {'Team':<20} : {team.get('team_name')}")
    print(f"  {'City':<20} : {team.get('city_name')}")
    print(f"  {'Founded':<20} : {fmt_date(team.get('created_date',''))}")
    print(f"  {'Total Players':<20} : {props.get('members',{}).get('data',{}).get('total_team_players','?')}")
    print(f"  {'URL':<20} : {BASE}/team-profile/{TEAM_ID}/{TEAM_SLUG}")


def print_stats(stats_tab: dict):
    section("📊 TEAM STATS (from stats tab)")
    data = stats_tab.get("teamStats", {})
    if not data.get("status"):
        print("  ⚠️  Stats not available")
        return
    items = data.get("data", [])
    for s in items:
        print(f"  {s.get('title','?'):<20} : {s.get('value','?')}")


def _skill_label(skill: str) -> str:
    mapping = {
        "ALL":    "All-Rounder",
        "BAT":    "Batsman",
        "BOWL":   "Bowler",
        "BAT,WK": "WK-Batsman",
        "WK":     "Wicket-Keeper",
    }
    return mapping.get(skill.strip(), skill or "Player")


def print_members(members_tab: dict):
    section("👥 SQUAD — 30 Players")
    data = members_tab.get("members", {})
    if not data.get("status"):
        print("  ⚠️  Members not available")
        return
    members = data.get("data", {}).get("members", [])
    print(f"\n  {'#':<4} {'Name':<28} {'Role':<16} {'Cap/Admin/PRO'}")
    print(f"  {'-'*4} {'-'*28} {'-'*16} {'-'*20}")
    for i, p in enumerate(members, 1):
        role = _skill_label(p.get("player_skill", ""))
        flags = []
        if p.get("is_captain"):  flags.append("🏏 Captain")
        if p.get("is_admin"):    flags.append("⚙️ Admin")
        if p.get("is_player_pro"): flags.append("⭐ PRO")
        print(f"  {i:<4} {p['name']:<28} {role:<16} {' '.join(flags)}")


def print_matches(matches_tab: dict):
    section("📅 MATCH HISTORY")
    matches = matches_tab.get("matches", {}).get("data", [])
    if not isinstance(matches, list) or not matches:
        print("  No match data.")
        return
    for i, m in enumerate(matches, 1):
        won = str(m.get("winning_team_id", "")) == TEAM_ID
        status = m.get("status", "")
        if status == "upcoming":
            icon = "🔜"
        elif won:
            icon = "✅ WON"
        else:
            icon = "❌ LOST"
        date = fmt_date(m.get("match_start_time", ""))
        opp  = m.get("team_b", "") if str(m.get("team_a_id","")) == TEAM_ID else m.get("team_a","")
        sa   = m.get("team_a_summary", "-")
        sb   = m.get("team_b_summary", "-")
        tourn = m.get("tournament_name","").strip()
        toss  = m.get("toss_details","")
        print(f"\n  [{i:02d}] {icon}  {date}  vs {opp}  ({tourn})")
        print(f"       Score : {sa} vs {sb}")
        if toss: print(f"       Toss  : {toss}")
        summary = m.get("match_summary", {}).get("summary", "")
        if summary: print(f"       Result: {summary}")


def print_photos(photos: list):
    section(f"📸 MATCH PHOTOS ({len(photos)} found)")
    for i, p in enumerate(photos, 1):
        print(f"  [{i:02d}] By {p.get('uploaded_by')} on {fmt_date(p.get('uploaded_date',''))}")
        print(f"       {p.get('media')}")


def print_derived(matches_tab: dict):
    section("📊 DERIVED STATS")
    matches = matches_tab.get("matches", {}).get("data", [])
    if not isinstance(matches, list): matches = []
    past = [m for m in matches if m.get("status") == "past"]
    if not past:
        print("  No past matches.")
        return
    wins   = sum(1 for m in past if str(m.get("winning_team_id","")) == TEAM_ID)
    losses = len(past) - wins
    dd_scores = []
    for m in past:
        innings = (m.get("team_a_innings",[]) if str(m.get("team_a_id","")) == TEAM_ID
                   else m.get("team_b_innings",[]))
        # Use only the first innings to avoid duplicates
        for inn in innings[:1]:
            dd_scores.append(inn.get("total_run", 0))
    print(f"  Played  : {len(past)}")
    print(f"  Won     : {wins}")
    print(f"  Lost    : {losses}")
    print(f"  Win %   : {wins/len(past)*100:.1f}%")
    if dd_scores:
        print(f"  Avg     : {sum(dd_scores)/len(dd_scores):.1f}")
        print(f"  High    : {max(dd_scores)}")
        print(f"  Low     : {min(dd_scores)}")


# ─────────────────────────────────────────────
# Build website-ready JSON
# ─────────────────────────────────────────────

def build_website_json(stats_tab: dict, matches_tab: dict,
                       members_tab: dict, photos: list) -> dict:

    team_data  = stats_tab.get("teamDetails",{}).get("data",{})
    raw_stats  = stats_tab.get("teamStats",{}).get("data",[])
    all_matches = matches_tab.get("matches",{}).get("data",[]) or []
    if not isinstance(all_matches, list): all_matches = []

    past     = [m for m in all_matches if m.get("status") == "past"]
    upcoming = [m for m in all_matches if m.get("status") == "upcoming"]

    # ── Derived stats ──
    wins   = sum(1 for m in past if str(m.get("winning_team_id","")) == TEAM_ID)
    losses = len(past) - wins

    dd_scores = []
    for m in past:
        if str(m.get("team_a_id","")) == TEAM_ID:
            innings = m.get("team_a_innings",[])
        else:
            innings = m.get("team_b_innings",[])
        if innings:   # first innings only (avoids duplicate rows for some matches)
            dd_scores.append(innings[0].get("total_run", 0))

    derived = {
        "played":    len(past),
        "wins":      wins,
        "losses":    losses,
        "winPct":    round(wins / len(past) * 100, 1) if past else 0,
        "avgScore":  round(sum(dd_scores) / len(dd_scores), 1) if dd_scores else 0,
        "highScore": max(dd_scores) if dd_scores else 0,
        "lowScore":  min(dd_scores) if dd_scores else 0,
        "upcoming":  len(upcoming),
    }

    # ── Format past matches ──
    def dd_score(m):
        if str(m.get("team_a_id","")) == TEAM_ID:
            return m.get("team_a_summary","-"), m.get("team_b_summary","-")
        return m.get("team_b_summary","-"), m.get("team_a_summary","-")

    def opp_name(m):
        return m.get("team_b","") if str(m.get("team_a_id","")) == TEAM_ID else m.get("team_a","")

    def parse_runs(score_str):
        try:
            return int(str(score_str).split("/")[0].replace(",","").strip())
        except Exception:
            return 0

    formatted_past = []
    for m in past:
        my_score, opp_score = dd_score(m)
        result = "W" if str(m.get("winning_team_id","")) == TEAM_ID else "L"
        summary = (m.get("match_summary") or {}).get("summary","")
        formatted_past.append({
            "matchId":    m.get("match_id"),
            "date":       (m.get("match_start_time","") or "")[:10],
            "opponent":   opp_name(m),
            "venue":      m.get("ground_name",""),
            "result":     result,
            "score":      str(my_score),
            "oppScore":   str(opp_score),
            "runs":       parse_runs(my_score),
            "wkts":       0,
            "tournament": m.get("tournament_name","").strip(),
            "overs":      m.get("overs"),
            "toss":       m.get("toss_details",""),
            "summary":    summary,
            "winBy":      m.get("win_by",""),
            "mom":        "—",
        })
    formatted_past.sort(key=lambda x: x["date"])

    # ── Format upcoming ──
    formatted_upcoming = []
    for m in upcoming:
        dt_str = (m.get("match_start_time","") or "")[:10]
        try:
            dt = datetime.strptime(dt_str, "%Y-%m-%d")
        except Exception:
            dt = None
        formatted_upcoming.append({
            "matchId":    m.get("match_id"),
            "date":       dt_str,
            "day":        dt.strftime("%d") if dt else "??",
            "month":      dt.strftime("%b") if dt else "???",
            "opponent":   opp_name(m),
            "opponentLogo": (m.get("team_b_logo","") if str(m.get("team_a_id","")) == TEAM_ID
                             else m.get("team_a_logo","")),
            "venue":      m.get("ground_name",""),
            "tournament": m.get("tournament_name","").strip(),
            "overs":      m.get("overs"),
            "time":       "07:30 AM",
        })

    # ── Tournaments breakdown ──
    tournaments = {}
    for m in past:
        t = m.get("tournament_name","").strip()
        if t:
            w = 1 if str(m.get("winning_team_id","")) == TEAM_ID else 0
            if t not in tournaments:
                tournaments[t] = {"played": 0, "won": 0}
            tournaments[t]["played"] += 1
            tournaments[t]["won"]    += w

    # ── Members ──
    raw_members = members_tab.get("members",{}).get("data",{}).get("members",[])
    formatted_members = []
    for p in raw_members:
        skill = p.get("player_skill","")
        formatted_members.append({
            "id":         p.get("player_id"),
            "name":       p.get("name",""),
            "photo":      p.get("profile_photo",""),
            "skill":      skill,
            "role":       _skill_label(skill),
            "isCaptain":  bool(p.get("is_captain")),
            "isAdmin":    bool(p.get("is_admin")),
            "isPro":      bool(p.get("is_player_pro")),
            "batterType": p.get("batter_category",""),
            "bowlerType": p.get("bowler_category",""),
            "profileUrl": f"{BASE}/player-profile/{p.get('player_id')}/{p.get('name','').replace(' ','-').lower()}",
        })

    # ── Photos ──
    formatted_photos = []
    for p in photos:
        formatted_photos.append({
            "id":         p.get("media_id"),
            "url":        p.get("media",""),
            "type":       p.get("media_type","image/jpeg"),
            "orientation": p.get("orientation","landscape"),
            "uploadedBy": p.get("uploaded_by",""),
            "uploadedById": p.get("uploaded_by_id"),
            "date":       (p.get("uploaded_date","") or "")[:10],
        })

    return {
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
        "team":        team_data,
        "stats":       raw_stats,
        "derived":     derived,
        "matches":     formatted_past,
        "upcoming":    formatted_upcoming,
        "tournaments": [
            {"name": t, **rec}
            for t, rec in sorted(tournaments.items(), key=lambda x: -x[1]["played"])
        ],
        "members":  formatted_members,
        "photos":   formatted_photos,
    }


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print(f"\n🏏 CricHeroes Data Fetcher — Dugout Devils")
    print(f"   {BASE}/team-profile/{TEAM_ID}/{TEAM_SLUG}")

    try:
        print("\n  🔍 Detecting buildId...")
        build_id = get_build_id()
        print(f"  ✅ buildId: {build_id}")

        print("  📡 Fetching stats tab...")
        stats_tab = fetch_tab(build_id, "stats")
        time.sleep(0.4)

        print("  📡 Fetching matches tab...")
        matches_tab = fetch_tab(build_id, "matches")
        time.sleep(0.4)

        print("  📡 Fetching members tab...")
        members_tab = fetch_tab(build_id, "members")
        time.sleep(0.4)

        print("  📸 Fetching match photos...")
        photos = fetch_photos(page_size=24)
        print(f"  ✅ {len(photos)} photo(s) found")

        # ── Print summaries ──
        print_profile(members_tab)
        print_stats(stats_tab)
        print_members(members_tab)
        print_matches(matches_tab)
        print_derived(matches_tab)
        print_photos(photos)

        # ── Build and save JSON ──
        website_json = build_website_json(stats_tab, matches_tab, members_tab, photos)
        website_json["buildId"] = build_id   # ← cache so CI can reuse it on next run

        # Preserve user-added static data (schedule, achievements)
        if os.path.exists(OUT_PATH):
            with open(OUT_PATH, "r") as f:
                try:
                    existing = json.load(f)
                    if "schedule" in existing:
                        website_json["schedule"] = existing["schedule"]
                    if "achievements" in existing:
                        website_json["achievements"] = existing["achievements"]
                except Exception as e:
                    print(f"  ⚠️  Could not read existing JSON for manual data: {e}")

        with open(OUT_PATH, "w") as f:
            json.dump(website_json, f, indent=2, default=str)

        print(f"\n  ✅ Saved → {OUT_PATH}")
        d = website_json["derived"]
        print(f"  📊 {d['played']} matches · {d['wins']}W / {d['losses']}L · {d['winPct']}% win rate")
        print(f"  👥 {len(website_json['members'])} squad members")
        print(f"  📸 {len(website_json['photos'])} photos")
        print(f"  🔜 {d['upcoming']} upcoming match(es)")
        print(f"  🕐 {website_json['lastUpdated']}")

    except requests.HTTPError as e:
        print(f"\n❌ HTTP Error: {e}")
        raise
    except Exception as e:
        import traceback
        print(f"\n❌ Error: {e}")
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()