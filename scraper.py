#!/usr/bin/env python3
import requests, os
from datetime import datetime, timedelta, timezone

BASE   = "https://statsapi.mlb.com/api/v1"
OUTDIR = "docs/mlbscores"

def game_date():
    et = timezone(timedelta(hours=-4))
    yesterday = datetime.now(et) - timedelta(days=1)
    return yesterday.strftime("%Y-%m-%d")

def get_schedule(date):
    r = requests.get(f"{BASE}/schedule?sportId=1&date={date}", timeout=10)
    r.raise_for_status()
    data = r.json()
    if not data.get("dates"): return []
    return [g for g in data["dates"][0]["games"] if g["status"]["abstractGameCode"] == "F"]

def get_boxscore(game_pk):
    r = requests.get(f"{BASE}/game/{game_pk}/boxscore", timeout=10)
    r.raise_for_status()
    return r.json()

def get_linescore(game_pk):
    r = requests.get(f"{BASE}/game/{game_pk}/linescore", timeout=10)
    r.raise_for_status()
    return r.json()

def get_standings(date):
    url = (f"{BASE}/standings?leagueId=103,104&season={date[:4]}"
           f"&date={date}&standingsTypes=regularSeason&hydrate=team(division)")
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    return r.json()

ABBR = {
    "Los Angeles Angels":"LAA","Cleveland Guardians":"CLE","New York Yankees":"NYY",
    "Baltimore Orioles":"BAL","Washington Nationals":"WSH","Cincinnati Reds":"CIN",
    "Colorado Rockies":"COL","Pittsburgh Pirates":"PIT","Philadelphia Phillies":"PHI",
    "Boston Red Sox":"BOS","Tampa Bay Rays":"TB","Toronto Blue Jays":"TOR",
    "Detroit Tigers":"DET","New York Mets":"NYM","Chicago Cubs":"CHC",
    "Atlanta Braves":"ATL","Kansas City Royals":"KC","Chicago White Sox":"CWS",
    "Miami Marlins":"MIA","Minnesota Twins":"MIN","San Diego Padres":"SD",
    "Milwaukee Brewers":"MIL","Arizona Diamondbacks":"AZ","Texas Rangers":"TEX",
    "Seattle Mariners":"SEA","Houston Astros":"HOU","St. Louis Cardinals":"STL",
    "Athletics":"ATH","San Francisco Giants":"SF","Los Angeles Dodgers":"LAD",
}

def extract_batters(team_data):
    rows = []
    for pid in team_data["batters"]:
        p = team_data["players"].get(f"ID{pid}")
        if not p: continue
        bs = p["stats"].get("batting", {})
        pos = p["position"]["abbreviation"]
        label = f"{p['person']['fullName']} {pos}"
        rows.append({
            "name": label, "ab": bs.get("atBats",0), "r": bs.get("runs",0),
            "h": bs.get("hits",0), "rbi": bs.get("rbi",0),
            "bb": bs.get("baseOnBalls",0), "k": bs.get("strikeOuts",0),
            "avg": p["seasonStats"]["batting"].get("avg","---"),
        })
    ts = team_data["teamStats"]["batting"]
    rows.append({"name":"Totals","ab":ts.get("atBats",0),"r":ts.get("runs",0),
        "h":ts.get("hits",0),"rbi":ts.get("rbi",0),"bb":ts.get("baseOnBalls",0),
        "k":ts.get("strikeOuts",0),"avg":""})
    return rows

def extract_pitchers(team_data):
    rows = []
    for pid in team_data["pitchers"]:
        p = team_data["players"].get(f"ID{pid}")
        if not p: continue
        ps = p["stats"].get("pitching", {})
        note = ps.get("note","")
        era  = p["seasonStats"]["pitching"].get("era","-.--")
        label = f"{p['person']['fullName']} {note}".strip()
        rows.append({
            "name": label, "ip": ps.get("inningsPitched","0.0"),
            "h": ps.get("hits",0), "r": ps.get("runs",0),
            "er": ps.get("earnedRuns",0), "bb": ps.get("baseOnBalls",0),
            "k": ps.get("strikeOuts",0), "hr": ps.get("homeRuns",0), "era": era,
        })
    ts = team_data["teamStats"]["pitching"]
    rows.append({"name":"Totals","ip":ts.get("inningsPitched","0.0"),"h":ts.get("hits",0),
        "r":ts.get("runs",0),"er":ts.get("earnedRuns",0),"bb":ts.get("baseOnBalls",0),
        "k":ts.get("strikeOuts",0),"hr":ts.get("homeRuns",0),"era":""})
    return rows

def extract_decisions(game_pk):
    win = loss = save = ""
    try:
        r = requests.get(f"https://statsapi.mlb.com/api/v1.1/game/{game_pk}/feed/live", timeout=10)
        r.raise_for_status()
        dec = r.json().get("liveData", {}).get("decisions", {}) or {}
        win = (dec.get("winner") or {}).get("fullName", "")
        loss = (dec.get("loser") or {}).get("fullName", "")
        save = (dec.get("save") or {}).get("fullName", "")
    except Exception:
        pass
    return win, loss, save

def build_game(game_meta, box, ls):
    away_data = box["teams"]["away"]; home_data = box["teams"]["home"]
    away_name = away_data["team"]["name"]; home_name = home_data["team"]["name"]
    away_abr = ABBR.get(away_name, away_name[:3].upper())
    home_abr = ABBR.get(home_name, home_name[:3].upper())
    away_score = game_meta["teams"]["away"]["score"]
    home_score = game_meta["teams"]["home"]["score"]
    away_rec = game_meta["teams"]["away"]["leagueRecord"]
    home_rec = game_meta["teams"]["home"]["leagueRecord"]
    away_rec_s = f"{away_rec['wins']}-{away_rec['losses']}"
    home_rec_s = f"{home_rec['wins']}-{home_rec['losses']}"
    innings = ls.get("innings",[])
    num_inn = ls.get("currentInning", 9)
    inn_away = [str(i["away"].get("runs","")) for i in innings]
    inn_home = [str(i["home"].get("runs","")) for i in innings]
    if home_score > away_score and innings:
        last = innings[-1]["home"].get("runs", None)
        if last is None: inn_home[-1] = "X"
    away_rhe = [ls["teams"]["away"].get("runs",0), ls["teams"]["away"].get("hits",0), ls["teams"]["away"].get("errors",0)]
    home_rhe = [ls["teams"]["home"].get("runs",0), ls["teams"]["home"].get("hits",0), ls["teams"]["home"].get("errors",0)]
    note = "Final"
    sched = ls.get("scheduledInnings", 9)
    if num_inn != sched: note = f"Final/{num_inn}"
    info_map = {item.get("label",""): item.get("value","") for item in box.get("info",[])}
    win, loss, save = extract_decisions(game_meta.get("gamePk"))
    return {
        "away": away_name, "awayAbr": away_abr, "awayRec": away_rec_s, "awayScore": away_score,
        "home": home_name, "homeAbr": home_abr, "homeRec": home_rec_s, "homeScore": home_score,
        "note": note, "innAway": inn_away, "innHome": inn_home, "numInn": num_inn,
        "awayRHE": away_rhe, "homeRHE": home_rhe,
        "awayBatters": extract_batters(away_data), "homeBatters": extract_batters(home_data),
        "awayPitchers": extract_pitchers(away_data), "homePitchers": extract_pitchers(home_data),
        "win": win, "loss": loss, "save": save,
        "venue": game_meta.get("venue",{}).get("name",""),
        "weather": info_map.get("Weather",""), "wind": info_map.get("Wind",""),
        "att": info_map.get("Att",""), "time": info_map.get("T",""),
    }

def extract_standings(standings_data):
    DIV_ORDER = [
        "American League East","American League Central","American League West",
        "National League East","National League Central","National League West",
    ]
    divs = {}
    for record in standings_data.get("records",[]):
        div_name = record["division"]["name"]
        teams = []
        for tr in record["teamRecords"]:
            lr = tr["leagueRecord"]
            l10 = next((s for s in tr["records"]["splitRecords"] if s["type"]=="lastTen"),{})
            l10_s = f"{l10.get('wins',0)}-{l10.get('losses',0)}"
            diff_val = int(tr.get("runsScored",0)) - int(tr.get("runsAllowed",0))
            diff_s = (f"+{diff_val}" if diff_val > 0 else str(diff_val)) if diff_val != 0 else "E"
            teams.append({
                "name": tr["team"]["name"], "w": lr["wins"], "l": lr["losses"],
                "pct": lr["pct"], "gb": tr["gamesBack"], "l10": l10_s,
                "strk": tr["streak"]["streakCode"], "diff": diff_s,
            })
        divs[div_name] = teams
    return {k: divs[k] for k in DIV_ORDER if k in divs}

CSS = """
*{box-sizing:border-box;margin:0;padding:0}
body{background:#f5f0e8;font-family:"Georgia","Times New Roman",serif;color:#1a1a1a;font-size:14px}
.masthead{background:#1a1a1a;color:#f5f0e8;text-align:center;padding:18px 20px 14px;border-bottom:4px solid #c8a84b}
.masthead h1{font-size:2.4em;letter-spacing:0.12em;font-weight:900;text-transform:uppercase}
.masthead .tagline{font-size:0.82em;letter-spacing:0.25em;text-transform:uppercase;color:#c8a84b;margin-top:4px}
.masthead .dateline{font-size:0.75em;color:#aaa;margin-top:6px;letter-spacing:0.08em}
.section-divider{background:#1a1a1a;color:#c8a84b;text-align:center;font-size:0.68em;letter-spacing:0.35em;text-transform:uppercase;padding:5px 0}
.main-content{max-width:1400px;margin:0 auto;padding:20px 16px}
.page-header{display:flex;align-items:baseline;gap:12px;margin-bottom:18px;border-bottom:2px solid #1a1a1a;padding-bottom:8px}
.page-header h2{font-size:1.5em;letter-spacing:0.05em;text-transform:uppercase}
.page-header .subtitle{font-size:0.78em;color:#666;letter-spacing:0.12em;text-transform:uppercase}
.games-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(660px,1fr));gap:20px;margin-bottom:40px}
.game-card{background:#fff;border:1px solid #d4cfc4;border-top:3px solid #1a1a1a;overflow:hidden}
.game-header{display:flex;align-items:center;justify-content:space-between;padding:10px 14px 8px;border-bottom:1px solid #eee;background:#fdfdfc}
.team-block{display:flex;flex-direction:column;align-items:center;min-width:72px}
.team-abr{font-size:1.4em;font-weight:900;letter-spacing:0.08em;text-transform:uppercase;line-height:1}
.team-rec{font-size:0.65em;color:#888;letter-spacing:0.04em;margin-top:1px}
.team-score{font-size:2em;font-weight:900;color:#888;line-height:1;margin-top:2px}
.team-score.big-score{color:#1a1a1a}
.game-meta{text-align:center;flex:1}
.game-meta>div{font-size:0.8em;color:#555;margin-bottom:3px}
.status{font-size:0.68em;letter-spacing:0.12em;text-transform:uppercase;color:#888;border:1px solid #ddd;padding:3px 8px;display:inline-block}
.linescore-wrap{overflow-x:auto;padding:4px 10px;border-bottom:1px solid #eee;background:#faf8f4}
.linescore{width:100%;border-collapse:collapse;font-size:0.72em}
.linescore th,.linescore td{text-align:center;padding:2px 4px;min-width:16px}
.linescore th{color:#888;font-weight:normal;font-style:italic;border-bottom:1px solid #eee}
.linescore .team-col{text-align:left;font-weight:700;min-width:34px;padding-left:4px}
.linescore .rhe{border-left:1px solid #ddd;font-weight:700;color:#555;font-style:italic}
.linescore .rhe-val{border-left:1px solid #eee;font-weight:700}
.box-section{display:grid;grid-template-columns:1fr 1fr;gap:0;border-bottom:1px solid #eee}
.box-team{padding:8px 10px}
.box-team:first-child{border-right:1px solid #eee}
.box-team-label{font-size:0.68em;font-weight:700;letter-spacing:0.2em;text-transform:uppercase;color:#c8a84b;margin-bottom:4px;padding-bottom:3px;border-bottom:1px solid #f0ece3}
.box-table{width:100%;border-collapse:collapse;font-size:0.7em}
.box-table th{background:#f5f0e8;color:#666;font-weight:normal;font-style:italic;padding:2px 4px;text-align:center;border-bottom:1px solid #e8e4dc;white-space:nowrap}
.box-table th:first-child{text-align:left}
.box-table td{padding:2px 4px;text-align:center;border-bottom:1px solid #f5f2ee}
.box-table td:first-child{text-align:left;white-space:nowrap}
.box-table tr:last-child td{font-weight:700;background:#f5f0e8;border-top:1px solid #ddd}
.decisions{padding:7px 12px 8px;font-size:0.74em;display:flex;gap:20px;flex-wrap:wrap;border-bottom:1px solid #eee}
.dec-item{display:flex;gap:4px}
.pip{font-weight:900;color:#c8a84b;font-size:0.88em}
.dec-name{color:#333}
.game-footer{font-size:0.64em;color:#999;padding:4px 12px 6px}
.standings-section{margin-bottom:40px}
.standings-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(420px,1fr));gap:16px}
.standings-div{background:#fff;border:1px solid #d4cfc4;border-top:3px solid #1a1a1a;overflow:hidden}
.div-name{background:#1a1a1a;color:#c8a84b;font-size:0.7em;letter-spacing:0.25em;text-transform:uppercase;padding:6px 12px;font-style:italic}
.standings-table{width:100%;border-collapse:collapse;font-size:0.76em}
.standings-table thead th{background:#f5f0e8;color:#555;font-weight:normal;font-style:italic;padding:4px 8px;border-bottom:1px solid #ddd;text-align:center}
.standings-table thead th.s-team{text-align:left}
.standings-table tbody tr:nth-child(odd){background:#fff}
.standings-table tbody tr:nth-child(even){background:#faf8f4}
.standings-table tbody tr:first-child td{font-weight:700}
.standings-table tbody td{padding:4px 8px;text-align:center;border-bottom:1px solid #f0ece3}
.standings-table tbody td.s-team{text-align:left}
.win-strk{color:#1a7a1a;font-weight:700}
.loss-strk{color:#b71c1c;font-weight:700}
.pos-diff{color:#1a7a1a}.neg-diff{color:#b71c1c}
.footer{background:#1a1a1a;color:#666;text-align:center;padding:14px;font-size:0.7em;letter-spacing:0.12em;text-transform:uppercase;border-top:3px solid #c8a84b}
@media(max-width:700px){.games-grid{grid-template-columns:1fr}.box-section{grid-template-columns:1fr}.standings-grid{grid-template-columns:1fr}.box-team:first-child{border-right:none;border-bottom:1px solid #eee}}
"""

def render_batter_rows(batters):
    html = ""
    for b in batters:
        cls = ' style="font-weight:700;background:#f5f0e8;border-top:1px solid #ddd"' if b["name"] == "Totals" else ""
        html += f'<tr{cls}><td>{b["name"]}</td><td>{b["ab"]}</td><td>{b["r"]}</td><td>{b["h"]}</td><td>{b["rbi"]}</td><td>{b["bb"]}</td><td>{b["k"]}</td><td>{b["avg"]}</td></tr>'
    return html

def render_pitcher_rows(pitchers):
    html = ""
    for p in pitchers:
        cls = ' style="font-weight:700;background:#f5f0e8;border-top:1px solid #ddd"' if p["name"] == "Totals" else ""
        html += f'<tr{cls}><td>{p["name"]}</td><td>{p["ip"]}</td><td>{p["h"]}</td><td>{p["r"]}</td><td>{p["er"]}</td><td>{p["bb"]}</td><td>{p["k"]}</td><td>{p["hr"]}</td><td>{p["era"]}</td></tr>'
    return html

def render_game_card(g):
    aw = g["awayScore"] > g["homeScore"]
    hw = g["homeScore"] > g["awayScore"]
    inn_headers = "".join(f"<th>{i+1}</th>" for i in range(g["numInn"]))
    away_cells  = "".join(f"<td>{v}</td>" for v in g["innAway"])
    home_cells  = "".join(f"<td>{v}</td>" for v in g["innHome"])
    save_html = f'<div class="dec-item"><span class="pip">S:</span><span class="dec-name">{g["save"]}</span></div>' if g["save"] else ""
    footer_parts = []
    if g["venue"]:   footer_parts.append(g["venue"])
    if g["weather"]: footer_parts.append(g["weather"])
    if g["wind"]:    footer_parts.append(f"Wind: {g['wind']}")
    if g["att"]:     footer_parts.append(f"Att: {g['att']}")
    if g["time"]:    footer_parts.append(f"T: {g['time']}")
    footer = " &bull; ".join(footer_parts)
    bhead = "<tr><th>Batter</th><th>AB</th><th>R</th><th>H</th><th>RBI</th><th>BB</th><th>K</th><th>AVG</th></tr>"
    phead = "<tr><th>Pitcher</th><th>IP</th><th>H</th><th>R</th><th>ER</th><th>BB</th><th>K</th><th>HR</th><th>ERA</th></tr>"
    return f"""<div class="game-card">
  <div class="game-header">
    <div class="team-block"><span class="team-abr">{g["awayAbr"]}</span><span class="team-rec">{g["awayRec"]}</span><span class="team-score{' big-score' if aw else ''}">{g["awayScore"]}</span></div>
    <div class="game-meta"><div>{g["away"]} @ {g["home"]}</div><span class="status">{g["note"]}</span></div>
    <div class="team-block"><span class="team-abr">{g["homeAbr"]}</span><span class="team-rec">{g["homeRec"]}</span><span class="team-score{' big-score' if hw else ''}">{g["homeScore"]}</span></div>
  </div>
  <div class="linescore-wrap"><table class="linescore">
    <thead><tr><th class="team-col"></th>{inn_headers}<th class="rhe">R</th><th class="rhe">H</th><th class="rhe">E</th></tr></thead>
    <tbody>
      <tr><td class="team-col">{g["awayAbr"]}</td>{away_cells}<td class="rhe-val">{g["awayRHE"][0]}</td><td class="rhe-val">{g["awayRHE"][1]}</td><td class="rhe-val">{g["awayRHE"][2]}</td></tr>
      <tr><td class="team-col">{g["homeAbr"]}</td>{home_cells}<td class="rhe-val">{g["homeRHE"][0]}</td><td class="rhe-val">{g["homeRHE"][1]}</td><td class="rhe-val">{g["homeRHE"][2]}</td></tr>
    </tbody>
  </table></div>
  <div class="box-section">
    <div class="box-team"><div class="box-team-label">{g["away"]} Batting</div>
      <table class="box-table"><thead>{bhead}</thead><tbody>{render_batter_rows(g["awayBatters"])}</tbody></table></div>
    <div class="box-team"><div class="box-team-label">{g["home"]} Batting</div>
      <table class="box-table"><thead>{bhead}</thead><tbody>{render_batter_rows(g["homeBatters"])}</tbody></table></div>
  </div>
  <div class="box-section">
    <div class="box-team"><div class="box-team-label">{g["away"]} Pitching</div>
      <table class="box-table"><thead>{phead}</thead><tbody>{render_pitcher_rows(g["awayPitchers"])}</tbody></table></div>
    <div class="box-team"><div class="box-team-label">{g["home"]} Pitching</div>
      <table class="box-table"><thead>{phead}</thead><tbody>{render_pitcher_rows(g["homePitchers"])}</tbody></table></div>
  </div>
  <div class="decisions">
    <div class="dec-item"><span class="pip">W:</span><span class="dec-name">{g["win"]}</span></div>
    <div class="dec-item"><span class="pip">L:</span><span class="dec-name">{g["loss"]}</span></div>
    {save_html}
  </div>
  <div class="game-footer">{footer}</div>
</div>"""

def render_standings_div(div_name, teams):
    rows = ""
    for i, t in enumerate(teams):
        sc = "win-strk" if t["strk"].startswith("W") else "loss-strk"
        dc = "pos-diff" if t["diff"].startswith("+") else ("neg-diff" if t["diff"].startswith("-") else "")
        bold = ' style="font-weight:700"' if i == 0 else ""
        rows += f'<tr{bold}><td class="s-team">{t["name"]}</td><td>{t["w"]}</td><td>{t["l"]}</td><td>{t["pct"]}</td><td>{t["gb"]}</td><td>{t["l10"]}</td><td><span class="{sc}">{t["strk"]}</span></td><td class="{dc}">{t["diff"]}</td></tr>'
    return f"""<div class="standings-div"><div class="div-name">{div_name}</div>
  <table class="standings-table"><thead><tr><th class="s-team">Team</th><th>W</th><th>L</th><th>PCT</th><th>GB</th><th>L10</th><th>Strk</th><th>Diff</th></tr></thead>
  <tbody>{rows}</tbody></table></div>"""

def build_html(date_str, games_html, standings_html, num_games):
    from datetime import datetime
    try: dt = datetime.strptime(date_str, "%Y-%m-%d"); pretty_date = dt.strftime("%A, %B %-d, %Y")
    except: pretty_date = date_str
    no_games = '<p style="text-align:center;padding:60px;color:#666">No completed games found.</p>' if num_games == 0 else ""
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>The Morning Lineup — {pretty_date}</title><style>{CSS}</style></head><body>
<div class="masthead"><h1>&#9749; The Morning Lineup</h1>
<div class="tagline">MLB Box Scores &amp; Standings</div>
<div class="dateline">{pretty_date} &mdash; No takes. No discourse. Just baseball.</div></div>
<div class="section-divider">&#9679;&nbsp; Scores from Last Night &nbsp;&#9679;</div>
<div class="main-content">{no_games}
<div class="page-header"><h2>Box Scores</h2><span class="subtitle">{pretty_date} &mdash; {num_games} Game{"s" if num_games!=1 else ""}</span></div>
<div class="games-grid">{games_html}</div>
<div class="standings-section"><div class="page-header"><h2>Standings</h2><span class="subtitle">Through {pretty_date}</span></div>
<div class="standings-grid">{standings_html}</div></div></div>
<div class="footer">Data via MLB Stats API &bull; The Morning Lineup &bull; {pretty_date} &bull; Updated daily at 6am ET</div>
</body></html>"""

def main():
    date = game_date()
    print(f"Building Morning Lineup for {date}...")
    games_meta = get_schedule(date)
    print(f"  Found {len(games_meta)} completed games")
    games_html = ""
    for gm in games_meta:
        pk = gm["gamePk"]
        try:
            box = get_boxscore(pk); ls = get_linescore(pk)
            g = build_game(gm, box, ls); games_html += render_game_card(g)
            print(f"  ✓ {g['away']} @ {g['home']} ({g['awayScore']}-{g['homeScore']})")
        except Exception as e:
            print(f"  ✗ Game {pk} failed: {e}")
    try:
        raw_standings = get_standings(date); divs = extract_standings(raw_standings)
        standings_html = "".join(render_standings_div(k,v) for k,v in divs.items())
    except Exception as e:
        print(f"  ✗ Standings failed: {e}"); standings_html = ""
    os.makedirs(OUTDIR, exist_ok=True)
    html = build_html(date, games_html, standings_html, len(games_meta))
    out = os.path.join(OUTDIR, "index.html")
    with open(out, "w", encoding="utf-8") as f: f.write(html)
    print(f"  ✓ Written to {out}")

if __name__ == "__main__":
    main()
