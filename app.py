"""
Turtle EV - Dota 2 Predictions Only
No pandas dependency, optimized for Render
"""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import requests
import json
import random
from datetime import datetime
import asyncio
import os

app = FastAPI(title="Turtle +EV Dota 2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATE = {
    "props": [],
    "predictions": [],
    "last_update": None,
    "stats": {"total_props": 0, "ev_bets": 0, "best_edge": 0}
}

class DotaPredictionEngine:
    def __init__(self):
        self.underdog_url = "https://api.underdogfantasy.com/v1/over_under_lines"
        # Simplified player stats (no database needed)
        self.player_stats = {
            "Crystallis": {"avg_kills": 5.2, "avg_fantasy": 28.5, "variance": 2.1},
            "Yuma": {"avg_kills": 4.8, "avg_fantasy": 26.3, "variance": 1.8},
            "Ame": {"avg_kills": 6.1, "avg_fantasy": 31.2, "variance": 2.3},
            "skiter": {"avg_kills": 5.5, "avg_fantasy": 29.7, "variance": 1.9},
            "Pure": {"avg_kills": 5.9, "avg_fantasy": 30.1, "variance": 2.0},
            "Watson": {"avg_kills": 4.2, "avg_fantasy": 24.8, "variance": 1.7},
            "flyfly": {"avg_kills": 4.6, "avg_fantasy": 25.9, "variance": 2.2},
            "33": {"avg_kills": 4.4, "avg_fantasy": 27.1, "variance": 1.6},
            "Topson": {"avg_kills": 5.7, "avg_fantasy": 29.3, "variance": 2.4}
        }
    
    def scrape_props(self):
        """Scrape Dota 2 props from Underdog"""
        try:
            params = {"sport_id": "esports"}
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json",
                "Referer": "https://app.underdogfantasy.com/"
            }
            
            response = requests.get(self.underdog_url, params=params, headers=headers, timeout=10)
            
            if response.status_code != 200:
                print(f"API returned {response.status_code}")
                return self.get_sample_props()
            
            data = response.json()
            props = []
            
            # Parse Underdog's structure
            lines = data.get('over_under_lines', [])
            appearances = data.get('appearances', {})
            players = data.get('players', {})
            
            for line in lines:
                appearance_id = line.get('appearance_id')
                if not appearance_id or str(appearance_id) not in appearances:
                    continue
                
                appearance = appearances[str(appearance_id)]
                match_info = appearance.get('match', {})
                
                # Check if it's Dota 2
                if 'dota' not in str(match_info).lower() and 'esports' not in str(match_info).lower():
                    continue
                
                player_id = appearance.get('player_id')
                if not player_id or str(player_id) not in players:
                    continue
                
                player_data = players[str(player_id)]
                player_name = f"{player_data.get('first_name', '')} {player_data.get('last_name', '')}".strip()
                if not player_name:
                    player_name = player_data.get('display_name', '')
                
                stat_value = line.get('stat_value', 0)
                stat_type = line.get('over_under', {}).get('appearance_stat', {}).get('display_stat', 'Unknown')
                
                if player_name and stat_value > 0:
                    props.append({
                        'player': player_name,
                        'stat_type': stat_type,
                        'line': float(stat_value),
                        'game_info': f"{match_info.get('name', 'Match')}"
                    })
            
            # If no props found, use sample data
            if not props:
                return self.get_sample_props()
            
            return props
            
        except Exception as e:
            print(f"Error scraping: {e}")
            return self.get_sample_props()
    
    def get_sample_props(self):
        """Sample props for demonstration"""
        return [
            {"player": "Crystallis", "stat_type": "Kills", "line": 5.5, "game_info": "Team Spirit vs OG"},
            {"player": "Yuma", "stat_type": "Kills", "line": 4.5, "game_info": "PSG.LGD vs Team Liquid"},
            {"player": "Ame", "stat_type": "Fantasy Points", "line": 30.5, "game_info": "PSG.LGD vs Team Secret"},
            {"player": "33", "stat_type": "Kills", "line": 4.5, "game_info": "Tundra vs Entity"},
            {"player": "Pure", "stat_type": "Fantasy Points", "line": 28.5, "game_info": "VP vs BetBoom"}
        ]
    
    def predict(self, player_name, stat_type, line):
        """Generate prediction for a prop"""
        # Get player stats or use defaults
        player_data = self.player_stats.get(player_name, {
            "avg_kills": 5.0,
            "avg_fantasy": 28.0,
            "variance": 2.0
        })
        
        # Base prediction on stat type
        if 'Kill' in stat_type:
            base = player_data.get('avg_kills', 5.0)
            variance = player_data.get('variance', 2.0)
        elif 'Fantasy' in stat_type:
            base = player_data.get('avg_fantasy', 28.0)
            variance = player_data.get('variance', 2.0) * 2
        else:
            base = line
            variance = 2.5
        
        # Add some randomness for variance
        random.seed(hash(player_name + stat_type + str(datetime.now().date())))
        adjustment = random.gauss(0, variance * 0.3)
        
        prediction = base + adjustment
        edge = ((prediction - line) / line * 100) if line > 0 else 0
        
        # Determine pick
        if abs(edge) < 3:
            pick = 'PASS'
            confidence = 50
            ev = 0
        elif edge > 0:
            pick = 'OVER'
            confidence = min(75, 55 + abs(edge))
            ev = (confidence - 52.38) / 52.38 * 100
        else:
            pick = 'UNDER'
            confidence = min(75, 55 + abs(edge))
            ev = (confidence - 52.38) / 52.38 * 100
        
        return {
            'prediction': round(prediction, 1),
            'edge': round(edge, 1),
            'pick': pick,
            'confidence': round(confidence),
            'ev': round(ev, 1)
        }

async def update_predictions():
    """Update predictions"""
    global STATE
    
    engine = DotaPredictionEngine()
    props = engine.scrape_props()
    
    predictions = []
    for prop in props:
        pred = engine.predict(prop['player'], prop['stat_type'], prop['line'])
        predictions.append({
            **prop,
            **pred
        })
    
    # Sort by EV
    predictions.sort(key=lambda x: abs(x['ev']), reverse=True)
    
    STATE['props'] = props
    STATE['predictions'] = predictions
    STATE['last_update'] = datetime.now()
    
    # Calculate stats
    STATE['stats'] = {
        'total_props': len(props),
        'ev_bets': len([p for p in predictions if p['ev'] > 0]),
        'best_edge': max([abs(p['edge']) for p in predictions], default=0)
    }
    
    print(f"Updated: {len(props)} props, {STATE['stats']['ev_bets']} +EV bets")

@app.on_event("startup")
async def startup():
    await update_predictions()
    async def update_loop():
        while True:
            await asyncio.sleep(300)  # Update every 5 minutes
            await update_predictions()
    asyncio.create_task(update_loop())

@app.get("/")
async def home():
    """Main dashboard"""
    return HTMLResponse("""
<!DOCTYPE html>
<html>
<head>
    <title>🎮 Turtle +EV - Dota 2</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        
        body {
            background: #0a0a0a;
            color: #fff;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
        }
        
        .header {
            background: linear-gradient(135deg, #1a1a1a, #0f0f0f);
            padding: 30px;
            border-bottom: 3px solid #C9A961;
            text-align: center;
        }
        
        h1 {
            color: #C9A961;
            font-size: 36px;
            margin-bottom: 10px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }
        
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .stat-card {
            background: rgba(201, 169, 97, 0.05);
            border: 1px solid rgba(201, 169, 97, 0.2);
            padding: 25px;
            text-align: center;
            border-radius: 10px;
            transition: all 0.3s;
        }
        
        .stat-card:hover {
            transform: translateY(-2px);
            background: rgba(201, 169, 97, 0.08);
        }
        
        .stat-value {
            font-size: 36px;
            color: #C9A961;
            font-weight: bold;
            margin-bottom: 5px;
        }
        
        .stat-label {
            color: #888;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        
        th {
            background: #1a1a1a;
            color: #C9A961;
            padding: 15px;
            text-align: left;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        td {
            padding: 12px 15px;
            border-bottom: 1px solid rgba(51, 51, 51, 0.5);
        }
        
        tr:hover {
            background: rgba(201, 169, 97, 0.03);
        }
        
        .player-name { color: #C9A961; font-weight: 600; }
        .over { color: #10b981; font-weight: bold; }
        .under { color: #ef4444; font-weight: bold; }
        .pass { color: #666; }
        .positive { color: #10b981; }
        .negative { color: #ef4444; }
        
        .refresh-btn {
            background: #C9A961;
            color: #000;
            border: none;
            padding: 12px 24px;
            border-radius: 5px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s;
            margin-bottom: 20px;
        }
        
        .refresh-btn:hover {
            background: #b89650;
            transform: translateY(-2px);
        }
        
        .subtitle {
            color: #888;
            font-size: 14px;
            margin-top: 5px;
        }
        
        @media (max-width: 768px) {
            h1 { font-size: 24px; }
            .stats-grid { grid-template-columns: repeat(2, 1fr); }
            td, th { padding: 8px; font-size: 14px; }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🎮 TURTLE +EV - DOTA 2</h1>
        <p class="subtitle">Esports Betting Predictions | Live Props | +EV Analysis</p>
    </div>
    
    <div class="container">
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value" id="total-props">-</div>
                <div class="stat-label">Total Props</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="ev-bets">-</div>
                <div class="stat-label">+EV Bets</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="best-edge">-</div>
                <div class="stat-label">Best Edge</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="last-update">-</div>
                <div class="stat-label">Last Update</div>
            </div>
        </div>
        
        <button class="refresh-btn" onclick="location.reload()">🔄 Refresh Predictions</button>
        
        <table>
            <thead>
                <tr>
                    <th>Player</th>
                    <th>Match</th>
                    <th>Stat</th>
                    <th>Line</th>
                    <th>Prediction</th>
                    <th>Edge</th>
                    <th>Pick</th>
                    <th>Confidence</th>
                    <th>EV</th>
                </tr>
            </thead>
            <tbody id="predictions-body">
                <tr><td colspan="9" style="text-align: center; padding: 40px;">Loading predictions...</td></tr>
            </tbody>
        </table>
    </div>
    
    <script>
        async function loadData() {
            try {
                const response = await fetch('/api/predictions');
                const data = await response.json();
                
                // Update stats
                document.getElementById('total-props').textContent = data.stats.total_props;
                document.getElementById('ev-bets').textContent = data.stats.ev_bets;
                document.getElementById('best-edge').textContent = data.stats.best_edge.toFixed(1) + '%';
                
                const lastUpdate = new Date(data.last_update);
                document.getElementById('last-update').textContent = lastUpdate.toLocaleTimeString();
                
                // Update table
                const tbody = document.getElementById('predictions-body');
                if (data.predictions.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="9" style="text-align: center; padding: 40px;">No props available</td></tr>';
                } else {
                    tbody.innerHTML = data.predictions.map(p => {
                        const pickClass = p.pick === 'OVER' ? 'over' : p.pick === 'UNDER' ? 'under' : 'pass';
                        const edgeClass = p.edge > 0 ? 'positive' : p.edge < 0 ? 'negative' : '';
                        const evClass = p.ev > 0 ? 'positive' : '';
                        
                        return `
                            <tr>
                                <td class="player-name">${p.player}</td>
                                <td style="color: #888; font-size: 12px;">${p.game_info}</td>
                                <td>${p.stat_type}</td>
                                <td>${p.line.toFixed(1)}</td>
                                <td style="color: #C9A961; font-weight: bold;">${p.prediction.toFixed(1)}</td>
                                <td class="${edgeClass}">${p.edge > 0 ? '+' : ''}${p.edge.toFixed(1)}%</td>
                                <td class="${pickClass}">${p.pick}</td>
                                <td>${p.confidence}%</td>
                                <td class="${evClass}">${p.ev > 0 ? '+' : ''}${p.ev.toFixed(1)}%</td>
                            </tr>
                        `;
                    }).join('');
                }
            } catch (error) {
                console.error('Error loading data:', error);
            }
        }
        
        loadData();
        setInterval(loadData, 30000);
    </script>
</body>
</html>
    """)

@app.get("/api/predictions")
async def get_predictions():
    """API endpoint"""
    return {
        "predictions": STATE['predictions'],
        "stats": STATE['stats'],
        "last_update": STATE['last_update'].isoformat() if STATE['last_update'] else None
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
