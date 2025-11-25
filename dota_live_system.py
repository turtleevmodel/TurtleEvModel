"""
DOTA 2 Live Props System - Complete Version
"""

import requests
import sqlite3
import pickle
import pandas as pd
import numpy as np
from datetime import datetime
import time
import hashlib
import json
import argparse
import sys
import os
import re

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass

DB_PATH = 'dota_props.db'
DATA_DB = 'dota_data.db'
HISTORY_DB = 'dota_line_history.db'

DISCORD_WEBHOOK = "https://discord.com/api/webhooks/1439016599830138891/yY-IgykJ2DFA3eXJ-buAW5xN7EAkIYAjiuT10tU-YlMt9B917PdXkPpVqCxu8eorHFiB"

API_URLS = [
    "https://api.underdogfantasy.com/beta/v5/over_under_lines",
    "https://api.underdogfantasy.com/v1/over_under_lines",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://underdogfantasy.com/",
    "Accept": "application/json"
}

MIN_EDGE = 3.0
DEFAULT_INTERVAL = 120

DOTA_STAT_MAP = {
    'kills': 'Kills',
    'kills_in_game_1': 'Kills',
    'kills_in_game_2': 'Kills',
    'fantasy_points': 'Fantasy Points',
    'fantasy_points_in_game_1': 'Fantasy Points',
    'fantasy_points_in_game_2': 'Fantasy Points',
    'assists': 'Assists',
    'assists_in_game_1': 'Assists',
    'deaths': 'Deaths',
    'deaths_in_game_1': 'Deaths',
}

DOTA_TEAMS = [
    'team spirit', 'og', 'tundra', 'liquid', 'team liquid', 'secret', 'team secret',
    'entity', 'betboom', 'psg.lgd', 'lgd', 'xtreme', 'quest', 'falcons', 'nouns',
    'gaimin', 'talon', 'aurora', 'beastcoast', 'eg', 'evil geniuses', 'nigma',
    'alliance', 'vp', 'virtus.pro', 'navi', 'natus vincere', 'aster', 'rng'
]

KNOWN_PLAYERS = [
    'Crystallis', 'Yuma', 'Ame', 'skiter', 'Pure', 'Watson', 'flyfly', '33',
    'Collapse', 'Mira', 'Larl', 'Miposhka', 'Yatoro', 'TorontoTokyo',
    'Nisha', 'zai', 'Puppey', 'gpk', 'Quinn', 'Arteezy', 'Cr1t',
    'SumaiL', 'Topson', 'ana', 'Ceb', 'JerAx', 'N0tail', 'Fly',
    'RAMZES666', 'Solo', 'w33', 'Miracle', 'GH', 'Mind_Control', 'KuroKy',
    'MidOne', 'SoNNeikO', 'TORONTOTOKYO', 'DM', 'Faith_bian',
    'NothingToSay', 'XinQ', 'Erika', 'gotthejuice', 'Crystallize'
]


def setup_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS dota_props (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player TEXT,
            team TEXT,
            opponent TEXT,
            match_title TEXT,
            stat_type TEXT,
            line REAL,
            over_odds TEXT DEFAULT '-110',
            under_odds TEXT DEFAULT '-110',
            game_time TEXT,
            scraped_at TEXT,
            UNIQUE(player, stat_type, line)
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player TEXT,
            stat_type TEXT,
            line REAL,
            prediction REAL,
            edge REAL,
            pick_direction TEXT,
            confidence REAL,
            ev REAL DEFAULT 0,
            created_at TEXT,
            UNIQUE(player, stat_type, line)
        )
    """)
    
    conn.commit()
    conn.close()
    
    conn = sqlite3.connect(HISTORY_DB)
    cursor = conn.cursor()
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS prop_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player TEXT,
            stat_type TEXT,
            line REAL,
            timestamp TEXT,
            prop_hash TEXT UNIQUE
        )
    """)
    
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS posted_slips (
            slip_hash TEXT PRIMARY KEY,
            posted_at TEXT
        )
    """)
    
    conn.commit()
    conn.close()


def fetch_underdog_data():
    for url in API_URLS:
        try:
            print(f"   Trying: {url.split('/')[-2]}/{url.split('/')[-1]}")
            response = requests.get(url, headers=HEADERS, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                lines = data.get('over_under_lines', [])
                print(f"   Got {len(lines)} total lines")
                return data
                
        except requests.exceptions.RequestException as e:
            print(f"   Error: {str(e)[:50]}")
            continue
    
    return None


def is_dota_prop(title, over_under):
    title_lower = title.lower()
    
    if 'dota' in title_lower:
        return True
    
    sport_id = str(over_under.get('sport_id', '')).lower()
    if 'esport' in sport_id:
        for team in DOTA_TEAMS:
            if team in title_lower:
                return True
        for player in KNOWN_PLAYERS:
            if player.lower() in title_lower:
                return True
    
    for team in DOTA_TEAMS:
        if team in title_lower:
            return True
    
    return False


def extract_player_name(title, appearance_stat, appearances, players):
    if title.startswith('Dota:'):
        parts = title.split(':', 1)
        if len(parts) > 1:
            player_part = parts[1].strip()
            for stat in ['Kills', 'Fantasy Points', 'Assists', 'Deaths', 'Last Hits', 'GPM', 'XPM']:
                if stat in player_part:
                    name = player_part.replace(stat, '').strip()
                    if name:
                        return name
    
    appearance_id = appearance_stat.get('appearance_id')
    if appearance_id and appearance_id in appearances:
        player_id = appearances[appearance_id].get('player_id')
        if player_id and player_id in players:
            player = players[player_id]
            first = player.get('first_name', '').strip()
            last = player.get('last_name', '').strip()
            
            if first and not last:
                return first
            elif last and not first:
                return last
            elif first:
                return f"{first} {last}".strip()
    
    for player in KNOWN_PLAYERS:
        if player.lower() in title.lower():
            return player
    
    return None


def extract_match_info(title):
    info = {'team': '', 'opponent': '', 'match_title': title}
    
    patterns = [
        r'([A-Za-z0-9.\s]+)\s+vs\.?\s+([A-Za-z0-9.\s]+)',
        r'([A-Za-z0-9.\s]+)\s+@\s+([A-Za-z0-9.\s]+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            info['team'] = match.group(1).strip()
            info['opponent'] = match.group(2).strip()
            info['match_title'] = f"{info['team']} vs {info['opponent']}"
            break
    
    return info


def parse_dota_props(data):
    props = []
    
    if not data:
        return props
    
    lines = data.get('over_under_lines', [])
    appearances = {a['id']: a for a in data.get('appearances', [])}
    players = {p['id']: p for p in data.get('players', [])}
    
    for line in lines:
        try:
            over_under = line.get('over_under', {})
            title = over_under.get('title', '')
            
            if not is_dota_prop(title, over_under):
                continue
            
            appearance_stat = over_under.get('appearance_stat', {})
            stat_raw = appearance_stat.get('stat', '').lower()
            
            stat_type = None
            for key, value in DOTA_STAT_MAP.items():
                if key in stat_raw:
                    stat_type = value
                    break
            
            if not stat_type:
                continue
            
            line_value = float(line.get('stat_value', 0) or over_under.get('stat_value', 0))
            if line_value <= 0:
                continue
            
            player_name = extract_player_name(title, appearance_stat, appearances, players)
            if not player_name:
                continue
            
            match_info = extract_match_info(title)
            
            over_odds = '-110'
            under_odds = '-110'
            
            for opt in line.get('options', []):
                choice = opt.get('choice', '').lower()
                american = opt.get('american_price')
                payout = opt.get('payout_multiplier', 1.0)
                
                if payout and abs(float(payout) - 1.0) > 0.1:
                    continue
                
                if choice in ['higher', 'over']:
                    over_odds = str(american) if american else '-110'
                elif choice in ['lower', 'under']:
                    under_odds = str(american) if american else '-110'
            
            props.append({
                'player': player_name,
                'team': match_info.get('team', ''),
                'opponent': match_info.get('opponent', ''),
                'match_title': match_info.get('match_title', title),
                'stat_type': stat_type,
                'line': line_value,
                'over_odds': over_odds,
                'under_odds': under_odds
            })
            
        except Exception:
            continue
    
    return props


def load_models():
    try:
        with open('dota_kills_model.pkl', 'rb') as f:
            kills_model = pickle.load(f)
        with open('dota_fantasy_model.pkl', 'rb') as f:
            fantasy_model = pickle.load(f)
        with open('dota_features.pkl', 'rb') as f:
            feature_cols = pickle.load(f)
        
        return kills_model, fantasy_model, feature_cols, True
        
    except FileNotFoundError:
        return None, None, None, False


def get_player_averages():
    player_avgs = {}
    
    try:
        conn = sqlite3.connect(DATA_DB)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT player_name, avg_kills, last_5_kills, last_10_kills,
                   avg_fantasy_points, last_5_fantasy, last_10_fantasy
            FROM player_averages
        """)
        
        for row in cursor.fetchall():
            player_avgs[row[0]] = {
                'avg_kills': row[1],
                'last_5_kills': row[2],
                'last_10_kills': row[3],
                'avg_fantasy': row[4],
                'last_5_fantasy': row[5],
                'last_10_fantasy': row[6]
            }
        
        conn.close()
    except:
        pass
    
    return player_avgs


def generate_prediction(player, stat_type, line, player_avgs, models_data):
    kills_model, fantasy_model, feature_cols, models_loaded = models_data
    
    avgs = player_avgs.get(player)
    
    if avgs:
        if 'Kills' in stat_type:
            prediction = avgs.get('last_5_kills', avgs.get('avg_kills', line))
        elif 'Fantasy' in stat_type:
            prediction = avgs.get('last_5_fantasy', avgs.get('avg_fantasy', line))
        elif 'Assists' in stat_type:
            prediction = avgs.get('avg_kills', line) * 1.2
        else:
            prediction = line
    else:
        prediction = line
    
    diff = prediction - line
    edge = (diff / line * 100) if line > 0 else 0
    
    if abs(edge) < MIN_EDGE:
        pick = 'PASS'
        confidence = 50
        ev = 0
    elif edge > 0:
        pick = 'OVER'
        confidence = min(50 + abs(edge) * 2, 95)
        ev = abs(edge) * 2.5
    else:
        pick = 'UNDER'
        confidence = min(50 + abs(edge) * 2, 95)
        ev = abs(edge) * 2.5
    
    return {
        'prediction': round(prediction, 1),
        'edge': round(edge, 1),
        'pick': pick,
        'confidence': round(confidence, 0),
        'ev': round(ev, 1)
    }


def run_predictions(props):
    models_data = load_models()
    player_avgs = get_player_averages()
    
    predictions = []
    
    for prop in props:
        pred = generate_prediction(
            prop['player'], 
            prop['stat_type'], 
            prop['line'],
            player_avgs,
            models_data
        )
        
        predictions.append({
            **prop,
            **pred
        })
    
    return predictions


def save_props_and_predictions(props, predictions):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("DELETE FROM dota_props")
    cursor.execute("DELETE FROM predictions")
    
    timestamp = datetime.now().isoformat()
    
    for prop in props:
        cursor.execute("""
            INSERT OR REPLACE INTO dota_props 
            (player, team, opponent, match_title, stat_type, line, over_odds, under_odds, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            prop['player'], prop['team'], prop['opponent'], prop['match_title'],
            prop['stat_type'], prop['line'], prop['over_odds'], prop['under_odds'], timestamp
        ))
    
    for pred in predictions:
        cursor.execute("""
            INSERT OR REPLACE INTO predictions 
            (player, stat_type, line, prediction, edge, pick_direction, confidence, ev, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            pred['player'], pred['stat_type'], float(pred['line']),
            float(pred['prediction']), float(pred['edge']),
            pred['pick'], float(pred['confidence']), float(pred['ev']), timestamp
        ))
    
    conn.commit()
    conn.close()


def detect_changes(props):
    conn = sqlite3.connect(HISTORY_DB)
    cursor = conn.cursor()
    
    new_props = []
    changed_props = []
    
    for prop in props:
        prop_hash = hashlib.md5(
            f"{prop['player']}_{prop['stat_type']}_{prop['line']}".encode()
        ).hexdigest()
        
        cursor.execute("SELECT id FROM prop_history WHERE prop_hash = ?", (prop_hash,))
        
        if not cursor.fetchone():
            cursor.execute("""
                SELECT line FROM prop_history 
                WHERE player = ? AND stat_type = ?
                ORDER BY timestamp DESC LIMIT 1
            """, (prop['player'], prop['stat_type']))
            
            result = cursor.fetchone()
            if result and result[0] != prop['line']:
                changed_props.append({**prop, 'old_line': result[0]})
            else:
                new_props.append(prop)
            
            cursor.execute("""
                INSERT OR IGNORE INTO prop_history (player, stat_type, line, timestamp, prop_hash)
                VALUES (?, ?, ?, ?, ?)
            """, (prop['player'], prop['stat_type'], prop['line'], 
                  datetime.now().isoformat(), prop_hash))
    
    conn.commit()
    conn.close()
    
    return new_props, changed_props


def post_to_discord(predictions):
    good_picks = [p for p in predictions if p['pick'] != 'PASS' and abs(p['edge']) >= MIN_EDGE]
    
    if not good_picks:
        print("   No picks to post")
        return False
    
    good_picks.sort(key=lambda x: abs(x['edge']), reverse=True)
    
    description = f"**{len(good_picks)} +EV DOTA 2 Props** - Min {MIN_EDGE}% edge\n\n"
    
    for i, pick in enumerate(good_picks[:10], 1):
        emoji = "🟢" if pick['pick'] == 'OVER' else "🔴"
        
        description += f"**{i}. {pick['player']}**\n"
        if pick.get('match_title'):
            description += f"_{pick['match_title']}_\n"
        description += f"{pick['stat_type']} {pick['line']}\n"
        description += f"{emoji} {pick['pick']} | Pred: {pick['prediction']:.1f} | Edge: {pick['edge']:+.1f}% | EV: +{pick['ev']:.1f}%\n\n"
    
    if len(good_picks) > 10:
        description += f"_...and {len(good_picks) - 10} more picks_\n"
    
    embed = {
        "title": "🎮 DOTA 2 +EV Props",
        "description": description,
        "color": 0xC9A961,
        "timestamp": datetime.now().isoformat(),
        "footer": {"text": "Turtle +EV • DOTA 2 Live Predictions"}
    }
    
    payload = {
        "embeds": [embed],
        "username": "Turtle +EV Bot",
        "avatar_url": "https://img.icons8.com/fluency/96/turtle.png"
    }
    
    try:
        response = requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
        response.raise_for_status()
        print("   Posted to Discord!")
        return True
    except Exception as e:
        print(f"   Discord error: {e}")
        return False


def run_once():
    print("\n" + "=" * 70)
    print("🎮 DOTA 2 LIVE PROPS SYSTEM")
    print("=" * 70)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %I:%M:%S %p')}")
    
    setup_database()
    
    print("\nFetching Underdog API...")
    data = fetch_underdog_data()
    
    if not data:
        print("   Failed to fetch data!")
        return [], []
    
    print("\nParsing DOTA 2 props...")
    props = parse_dota_props(data)
    print(f"   Found {len(props)} DOTA props")
    
    if not props:
        print("\n   No DOTA props available")
        print("   (Normal when no matches scheduled)")
        return [], []
    
    stat_counts = {}
    for p in props:
        stat_counts[p['stat_type']] = stat_counts.get(p['stat_type'], 0) + 1
    
    print("\n   Props by type:")
    for stat, count in sorted(stat_counts.items()):
        print(f"      {stat}: {count}")
    
    print("\nGenerating predictions...")
    predictions = run_predictions(props)
    
    save_props_and_predictions(props, predictions)
    print(f"   Saved {len(predictions)} predictions to database")
    
    good_picks = [p for p in predictions if p['pick'] != 'PASS' and abs(p['edge']) >= MIN_EDGE]
    good_picks.sort(key=lambda x: abs(x['edge']), reverse=True)
    
    print(f"\n   +EV picks (>={MIN_EDGE}% edge): {len(good_picks)}")
    
    if good_picks:
        print(f"\n   {'Player':20} {'Stat':18} {'Line':>6} {'Pred':>6} {'Edge':>7} {'Pick':>6} {'EV':>6}")
        print("   " + "-" * 80)
        
        for pick in good_picks[:15]:
            print(f"   {pick['player']:20} {pick['stat_type']:18} {pick['line']:6.1f} "
                  f"{pick['prediction']:6.1f} {pick['edge']:+6.1f}% {pick['pick']:>6} +{pick['ev']:5.1f}%")
    
    print("\nPosting to Discord...")
    post_to_discord(predictions)
    
    print("\n" + "=" * 70)
    print("✅ COMPLETE")
    print(f"Database: {DB_PATH}")
    print("=" * 70 + "\n")
    
    return props, predictions


def monitor_loop(check_interval):
    print("\n" + "=" * 70)
    print("🎮 DOTA 2 LIVE PROPS MONITOR")
    print("=" * 70)
    print(f"Check interval: {check_interval} seconds")
    print(f"Database: {DB_PATH}")
    print("\nMonitoring for:")
    print("   - New DOTA 2 props")
    print("   - Line movements")
    print("\nPress Ctrl+C to stop")
    print("=" * 70)
    
    setup_database()
    check_count = 0
    
    try:
        while True:
            check_count += 1
            timestamp = datetime.now().strftime('%I:%M:%S %p')
            print(f"\n{'='*70}")
            print(f"[Check #{check_count}] {timestamp}")
            print(f"{'='*70}")
            
            data = fetch_underdog_data()
            
            if not data:
                print("   API fetch failed")
                time.sleep(check_interval)
                continue
            
            props = parse_dota_props(data)
            print(f"   Found {len(props)} DOTA props")
            
            if not props:
                print("   No DOTA props (normal when no matches)")
                print(f"\n   Next check in {check_interval // 60} minutes...")
                time.sleep(check_interval)
                continue
            
            new_props, changed_props = detect_changes(props)
            
            if new_props:
                print(f"   🆕 {len(new_props)} new props:")
                for p in new_props[:3]:
                    print(f"      + {p['player']}: {p['stat_type']} {p['line']}")
            
            if changed_props:
                print(f"   📈 {len(changed_props)} line movements:")
                for p in changed_props[:3]:
                    print(f"      ~ {p['player']}: {p['old_line']} → {p['line']}")
            
            predictions = run_predictions(props)
            save_props_and_predictions(props, predictions)
            
            good_picks = [p for p in predictions if p['pick'] != 'PASS' and abs(p['edge']) >= MIN_EDGE]
            print(f"\n   Predictions: {len(predictions)} total, {len(good_picks)} +EV")
            
            if new_props or changed_props:
                print("\n   Changes detected - posting to Discord...")
                post_to_discord(predictions)
            
            print(f"\n   Next check in {check_interval // 60} minutes...")
            time.sleep(check_interval)
            
    except KeyboardInterrupt:
        print("\n\n" + "=" * 70)
        print("Monitor stopped")
        print(f"Ran {check_count} checks")
        print("=" * 70)


def main():
    parser = argparse.ArgumentParser(description='DOTA 2 Live Props System')
    parser.add_argument('--monitor', '-m', action='store_true', 
                        help='Continuous monitoring mode')
    parser.add_argument('--interval', '-i', type=int, default=DEFAULT_INTERVAL,
                        help='Check interval in seconds (default: 120)')
    args = parser.parse_args()
    
    if args.monitor:
        monitor_loop(args.interval)
    else:
        run_once()


if __name__ == '__main__':
    main()
