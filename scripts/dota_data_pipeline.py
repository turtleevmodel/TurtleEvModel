"""
Enhanced Dota 2 Data Pipeline
Improved error handling, rate limiting, and data validation
"""

import requests
import sqlite3
import time
from datetime import datetime, timedelta
import logging
import json

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/dota_pipeline.log'),
        logging.StreamHandler()
    ]
)

class DotaDataPipeline:
    def __init__(self, db_path='data/dota_data.db'):
        self.db_path = db_path
        self.opendota_base = "https://api.opendota.com/api"
        self.underdog_url = "https://api.underdogfantasy.com/v1/over_under_lines"
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0'})
        
    def get_underdog_players(self):
        """Get all unique Dota players from Underdog with retry logic"""
        logging.info("Fetching Underdog Dota props...")
        
        for attempt in range(3):
            try:
                response = self.session.get(
                    self.underdog_url,
                    params={'sport_id': 'esports'},
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    lines = data.get('over_under_lines', [])
                    
                    players = set()
                    for line in lines:
                        # Parse Dota 2 specific lines
                        if 'appearances' in data and 'players' in data:
                            appearance_id = line.get('appearance_id')
                            if appearance_id and str(appearance_id) in data['appearances']:
                                appearance = data['appearances'][str(appearance_id)]
                                player_id = appearance.get('player_id')
                                if player_id and str(player_id) in data['players']:
                                    player = data['players'][str(player_id)]
                                    # Check if it's Dota 2
                                    if 'dota' in str(appearance.get('match', {})).lower():
                                        player_name = f"{player.get('first_name', '')} {player.get('last_name', '')}".strip()
                                        if not player_name:
                                            player_name = player.get('display_name', '')
                                        if player_name:
                                            players.add(player_name)
                    
                    logging.info(f"Found {len(players)} unique Dota players")
                    return list(players)
                    
            except Exception as e:
                logging.error(f"Attempt {attempt + 1} failed: {e}")
                time.sleep(2)
        
        return []
    
    def setup_database(self):
        """Create all necessary tables with indexes"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Pro players table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pro_players (
                account_id INTEGER PRIMARY KEY,
                name TEXT,
                real_name TEXT,
                team_name TEXT,
                team_tag TEXT,
                country_code TEXT,
                last_match_time INTEGER,
                is_active INTEGER
            )
        """)
        
        # Player stats table with indexes
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS player_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER,
                player_name TEXT,
                match_id INTEGER UNIQUE,
                match_date TEXT,
                kills INTEGER,
                deaths INTEGER,
                assists INTEGER,
                gpm REAL,
                xpm REAL,
                last_hits INTEGER,
                denies INTEGER,
                hero_damage INTEGER,
                tower_damage INTEGER,
                hero_healing INTEGER,
                fantasy_points REAL,
                win INTEGER,
                duration INTEGER,
                FOREIGN KEY (player_id) REFERENCES pro_players(account_id)
            )
        """)
        
        # Create indexes for faster queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_player_name ON player_stats(player_name)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_match_date ON player_stats(match_date)")
        
        # Player averages table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS player_averages (
                player_name TEXT PRIMARY KEY,
                player_id INTEGER,
                games_played INTEGER,
                avg_kills REAL,
                avg_deaths REAL,
                avg_assists REAL,
                avg_fantasy_points REAL,
                last_5_kills REAL,
                last_10_kills REAL,
                last_5_fantasy REAL,
                last_10_fantasy REAL,
                kills_variance REAL,
                fantasy_variance REAL,
                recent_form TEXT,
                updated_at TEXT
            )
        """)
        
        conn.commit()
        conn.close()
        logging.info("Database setup complete")
    
    def fetch_pro_players(self):
        """Fetch and store all pro players"""
        logging.info("Fetching pro player database...")
        
        try:
            response = self.session.get(f"{self.opendota_base}/proPlayers", timeout=30)
            if response.status_code == 200:
                players = response.json()
                
                conn = sqlite3.connect(self.db_path)
                cursor = conn.cursor()
                
                for player in players:
                    cursor.execute("""
                        INSERT OR REPLACE INTO pro_players 
                        (account_id, name, real_name, team_name, team_tag, country_code, last_match_time, is_active)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        player.get('account_id'),
                        player.get('name', ''),
                        player.get('personaname', ''),
                        player.get('team_name', ''),
                        player.get('team_tag', ''),
                        player.get('loccountrycode', ''),
                        int(player.get('last_match_time', 0)) if player.get('last_match_time') else 0,
                        1 if player.get('is_locked', False) else 0
                    ))
                
                conn.commit()
                conn.close()
                logging.info(f"Stored {len(players)} pro players")
                return True
                
        except Exception as e:
            logging.error(f"Failed to fetch pro players: {e}")
            return False
    
    def fetch_player_matches(self, account_id, limit=30):
        """Fetch recent matches with enhanced stats"""
        try:
            response = self.session.get(
                f"{self.opendota_base}/players/{account_id}/recentMatches",
                timeout=15
            )
            if response.status_code == 200:
                matches = response.json()
                return matches[:limit] if matches else []
        except Exception as e:
            logging.error(f"Error fetching matches for {account_id}: {e}")
        
        return []
    
    def calculate_fantasy_points(self, match):
        """Calculate fantasy points with Underdog scoring"""
        kills = match.get('kills', 0)
        deaths = match.get('deaths', 0)
        assists = match.get('assists', 0)
        last_hits = match.get('last_hits', 0)
        denies = match.get('denies', 0)
        gpm = match.get('gold_per_min', 0)
        tower_damage = match.get('tower_damage', 0)
        
        # Enhanced fantasy scoring
        fantasy = (
            kills * 3.0 +
            assists * 1.5 -
            deaths * 0.3 +
            last_hits * 0.003 +
            denies * 0.003 +
            gpm * 0.002 +
            tower_damage * 0.0001
        )
        
        return round(fantasy, 2)
    
    def process_all_players(self):
        """Main processing pipeline"""
        logging.info("="*70)
        logging.info("STARTING DOTA 2 DATA PIPELINE")
        logging.info("="*70)
        
        # Setup
        self.setup_database()
        
        # Fetch pro players if needed
        self.fetch_pro_players()
        
        # Get Underdog players
        underdog_players = self.get_underdog_players()
        
        if not underdog_players:
            logging.warning("No Underdog players found")
            return
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        processed = 0
        for player_name in underdog_players:
            # Match to pro database
            clean_name = player_name.split('(')[0].strip()
            
            cursor.execute("""
                SELECT account_id, name, team_name
                FROM pro_players
                WHERE LOWER(name) = LOWER(?) OR LOWER(real_name) = LOWER(?)
                LIMIT 1
            """, (clean_name, clean_name))
            
            result = cursor.fetchone()
            
            if not result:
                logging.warning(f"No match for {player_name}")
                continue
            
            account_id, db_name, team = result
            logging.info(f"Processing {player_name} -> {db_name} (ID: {account_id})")
            
            # Fetch matches
            matches = self.fetch_player_matches(account_id, limit=30)
            
            if not matches:
                continue
            
            # Save match data
            for match in matches:
                fantasy = self.calculate_fantasy_points(match)
                
                try:
                    cursor.execute("""
                        INSERT OR IGNORE INTO player_stats (
                            player_id, player_name, match_id, match_date,
                            kills, deaths, assists, gpm, xpm, last_hits, denies,
                            hero_damage, tower_damage, hero_healing,
                            fantasy_points, win, duration
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        account_id,
                        player_name,
                        match.get('match_id'),
                        datetime.fromtimestamp(match.get('start_time', 0)).isoformat(),
                        match.get('kills', 0),
                        match.get('deaths', 0),
                        match.get('assists', 0),
                        match.get('gold_per_min', 0),
                        match.get('xp_per_min', 0),
                        match.get('last_hits', 0),
                        match.get('denies', 0),
                        match.get('hero_damage', 0),
                        match.get('tower_damage', 0),
                        match.get('hero_healing', 0),
                        fantasy,
                        1 if (match.get('player_slot', 0) < 128) == match.get('radiant_win', False) else 0,
                        match.get('duration', 0)
                    ))
                except sqlite3.IntegrityError:
                    pass  # Match already exists
            
            processed += 1
            conn.commit()
            time.sleep(1)  # Rate limiting
        
        # Calculate averages
        self.calculate_all_averages(cursor)
        
        conn.commit()
        conn.close()
        
        logging.info("="*70)
        logging.info(f"PIPELINE COMPLETE - Processed {processed} players")
        logging.info("="*70)
    
    def calculate_all_averages(self, cursor):
        """Calculate comprehensive averages with variance"""
        logging.info("Calculating player averages...")
        
        cursor.execute("SELECT DISTINCT player_name, player_id FROM player_stats")
        players = cursor.fetchall()
        
        for player_name, player_id in players:
            cursor.execute("""
                SELECT kills, deaths, assists, fantasy_points
                FROM player_stats
                WHERE player_name = ?
                ORDER BY match_date DESC
                LIMIT 30
            """, (player_name,))
            
            stats = cursor.fetchall()
            
            if len(stats) < 3:
                continue
            
            # Calculate various averages
            games = len(stats)
            avg_kills = sum(s[0] for s in stats) / games
            avg_deaths = sum(s[1] for s in stats) / games
            avg_assists = sum(s[2] for s in stats) / games
            avg_fantasy = sum(s[3] for s in stats) / games
            
            # Recent form
            last_5_kills = sum(s[0] for s in stats[:5]) / min(5, games)
            last_10_kills = sum(s[0] for s in stats[:10]) / min(10, games)
            last_5_fantasy = sum(s[3] for s in stats[:5]) / min(5, games)
            last_10_fantasy = sum(s[3] for s in stats[:10]) / min(10, games)
            
            # Calculate variance (consistency)
            import statistics
            kills_variance = statistics.stdev([s[0] for s in stats[:10]]) if len(stats) >= 10 else 0
            fantasy_variance = statistics.stdev([s[3] for s in stats[:10]]) if len(stats) >= 10 else 0
            
            # Determine form (improving/declining)
            if last_5_fantasy > avg_fantasy * 1.1:
                form = "HOT"
            elif last_5_fantasy < avg_fantasy * 0.9:
                form = "COLD"
            else:
                form = "STABLE"
            
            cursor.execute("""
                INSERT OR REPLACE INTO player_averages (
                    player_name, player_id, games_played,
                    avg_kills, avg_deaths, avg_assists, avg_fantasy_points,
                    last_5_kills, last_10_kills, last_5_fantasy, last_10_fantasy,
                    kills_variance, fantasy_variance, recent_form, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                player_name, player_id, games,
                avg_kills, avg_deaths, avg_assists, avg_fantasy,
                last_5_kills, last_10_kills, last_5_fantasy, last_10_fantasy,
                kills_variance, fantasy_variance, form,
                datetime.now().isoformat()
            ))

if __name__ == '__main__':
    pipeline = DotaDataPipeline()
    pipeline.process_all_players()
