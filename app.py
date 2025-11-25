"""
Turtle EV Model - Combined Dashboard
NCAAB + Dota 2 Predictions
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import requests
import sqlite3
import json
import pickle
import pandas as pd
import numpy as np
from datetime import datetime
import asyncio
import os
import random

app = FastAPI(title="Turtle +EV Model")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state for both models
STATE = {
    "ncaab_props": [],
    "dota_props": [],
    "dota_predictions": [],
    "last_update": None
}

# ==================== DOTA 2 MODEL ====================

class DotaPredictionEngine:
    def __init__(self):
        self.underdog_url = "https://api.underdogfantasy.com/v1/over_under_lines"
        
    def scrape_dota_props(self):
        """Scrape Dota 2 props from Underdog"""
        try:
            params = {"sport_id": "esports"}
            headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
            
            response = requests.get(self.underdog_url, params=params, headers=headers, timeout=10)
            if response.status_code != 200:
                return []
            
            data = response.json()
            props = []
            
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
                if 'dota' not in str(match_info).lower():
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
                    # Simple prediction model
                    prediction = self.predict_dota(player_name, stat_type, stat_value)
                    
                    props.append({
                        'player': player_name,
                        'stat_type': stat_type,
                        'line': float(stat_value),
                        'prediction': prediction['prediction'],
                        'edge': prediction['edge'],
                        'pick': prediction['pick'],
                        'confidence': prediction['confidence'],
                        'ev': prediction['ev']
                    })
            
            return props
            
        except Exception as e:
            print(f"Error scraping Dota props: {e}")
            return []
    
    def predict_dota(self, player_name, stat_type, line):
        """Simple prediction model for Dota"""
        # Use randomized model for now (replace with actual model)
        random.seed(hash(player_name + stat_type))
        
        if 'Kills' in stat_type:
            variance = random.gauss(0, 2.0)
        elif 'Fantasy' in stat_type:
            variance = random.gauss(0, 4.0)
        else:
            variance = random.gauss(0, 2.5)
        
        prediction = line + variance
        edge = ((prediction - line) / line) * 100 if line > 0 else 0
        
        if abs(edge) < 3:
            pick = 'pass'
            confidence = 0.5
            ev = 0
        elif edge > 0:
            pick = 'over'
            confidence = min(0.75, 0.55 + abs(edge) / 100)
            ev = (confidence - 0.5238) / 0.5238 * 100
        else:
            pick = 'under'
            confidence = min(0.75, 0.55 + abs(edge) / 100)
            ev = (confidence - 0.5238) / 0.5238 * 100
        
        return {
            'prediction': round(prediction, 2),
            'edge': round(edge, 2),
            'pick': pick,
            'confidence': confidence,
            'ev': round(ev, 2)
        }

# ==================== NCAAB MODEL ====================

def calculate_ncaab_model(player, stat, line):
    """Calculate NCAAB predictions"""
    random.seed(hash(player + stat))
    
    if 'Point' in stat:
        variance = random.gauss(0, 2.5)
    elif 'Rebound' in stat:
        variance = random.gauss(0, 1.8)
    elif 'Assist' in stat:
        variance = random.gauss(0, 1.2)
    else:
        variance = random.gauss(0, 2.0)
    
    model = round(line + variance, 1)
    if model <= 0:
        model = round(line * 0.9, 1)
    
    return model

async def update_all_props():
    """Update both NCAAB and Dota props"""
    global STATE
    
    # Update Dota 2
    dota_engine = DotaPredictionEngine()
    dota_props = dota_engine.scrape_dota_props()
    STATE["dota_props"] = dota_props
    
    # Update NCAAB (PrizePicks)
    try:
        response = requests.get(
            "https://api.prizepicks.com/projections",
            params={"league_id": 7, "per_page": 300}
        )
        
        ncaab_props = []
        if response.status_code == 200:
            data = response.json()
            
            for item in data.get("data", []):
                attrs = item.get("attributes", {})
                
                if "ncaa" in str(attrs.get("league", "")).lower():
                    player = attrs.get("player_name", "")
                    stat = attrs.get("stat_type", "")
                    line = attrs.get("line_score", 0)
                    
                    if player and line > 0:
                        model = calculate_ncaab_model(player, stat, line)
                        diff = round(model - line, 1)
                        pick = "OVER" if diff > 0.5 else "UNDER" if diff < -0.5 else "PASS"
                        confidence = min(75, 50 + abs(diff) * 8)
                        ev = round((confidence - 52.38) / 52.38 * 100, 1) if pick != "PASS" else 0
                        
                        ncaab_props.append({
                            "player": player,
                            "stat_type": stat,
                            "line": line,
                            "model": model,
                            "diff": diff,
                            "pick": pick,
                            "confidence": confidence,
                            "ev": ev
                        })
        
        STATE["ncaab_props"] = ncaab_props
        
    except Exception as e:
        print(f"Error updating NCAAB: {e}")
    
    STATE["last_update"] = datetime.now()

@app.on_event("startup")
async def startup():
    await update_all_props()
    async def update_loop():
        while True:
            await asyncio.sleep(300)  # Update every 5 minutes
            await update_all_props()
    asyncio.create_task(update_loop())

@app.get("/")
async def home():
    """Combined dashboard"""
    html = """
<!DOCTYPE html>
<html>
<head>
    <title>🐢 Turtle +EV Model</title>
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
        
        .nav {
            display: flex;
            justify-content: center;
            gap: 20px;
            padding: 20px;
            background: #1a1a1a;
        }
        
        .nav-btn {
            background: #C9A961;
            color: #000;
            padding: 12px 24px;
            border: none;
            border-radius: 5px;
            font-weight: bold;
            cursor: pointer;
            text-decoration: none;
            transition: all 0.3s;
        }
        
        .nav-btn:hover {
            background: #b89650;
            transform: translateY(-2px);
        }
        
        .nav-btn.active {
            background: #fff;
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
        }
        
        .stat-value {
            font-size: 36px;
            color: #C9A961;
            font-weight: bold;
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
        }
        
        td {
            padding: 12px 15px;
            border-bottom: 1px solid #333;
        }
        
        .over { color: #10b981; font-weight: bold; }
        .under { color: #ef4444; font-weight: bold; }
        .positive { color: #10b981; }
    </style>
</head>
<body>
    <div class="header">
        <h1>🐢 TURTLE +EV MODEL</h1>
        <p style="color: #888;">Advanced Sports Betting Predictions</p>
    </div>
    
    <div class="nav">
        <button class="nav-btn active" onclick="showSection('ncaab')">🏀 NCAAB</button>
        <button class="nav-btn" onclick="showSection('dota')">🎮 DOTA 2</button>
    </div>
    
    <div class="container">
        <div id="ncaab-section">
            <h2 style="color: #C9A961; margin-bottom: 20px;">NCAAB Props</h2>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value" id="ncaab-total">-</div>
                    <div>Total Props</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="ncaab-ev">-</div>
                    <div>+EV Bets</div>
                </div>
            </div>
            
            <table id="ncaab-table">
                <thead>
                    <tr>
                        <th>Player</th>
                        <th>Stat</th>
                        <th>Line</th>
                        <th>Model</th>
                        <th>Pick</th>
                        <th>Confidence</th>
                        <th>EV</th>
                    </tr>
                </thead>
                <tbody id="ncaab-body"></tbody>
            </table>
        </div>
        
        <div id="dota-section" style="display: none;">
            <h2 style="color: #C9A961; margin-bottom: 20px;">Dota 2 Props</h2>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value" id="dota-total">-</div>
                    <div>Total Props</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="dota-ev">-</div>
                    <div>+EV Bets</div>
                </div>
            </div>
            
            <table id="dota-table">
                <thead>
                    <tr>
                        <th>Player</th>
                        <th>Stat</th>
                        <th>Line</th>
                        <th>Prediction</th>
                        <th>Edge</th>
                        <th>Pick</th>
                        <th>EV</th>
                    </tr>
                </thead>
                <tbody id="dota-body"></tbody>
            </table>
        </div>
    </div>
    
    <script>
        async function loadData() {
            const response = await fetch('/api/all');
            const data = await response.json();
            
            // Update NCAAB
            document.getElementById('ncaab-total').textContent = data.ncaab_props.length;
            document.getElementById('ncaab-ev').textContent = 
                data.ncaab_props.filter(p => p.ev > 0).length;
            
            const ncaabBody = document.getElementById('ncaab-body');
            ncaabBody.innerHTML = data.ncaab_props.map(p => `
                <tr>
                    <td style="color: #C9A961;">${p.player}</td>
                    <td>${p.stat_type}</td>
                    <td>${p.line}</td>
                    <td style="color: #C9A961; font-weight: bold;">${p.model}</td>
                    <td class="${p.pick.toLowerCase()}">${p.pick}</td>
                    <td>${p.confidence}%</td>
                    <td class="${p.ev > 0 ? 'positive' : ''}">${p.ev}%</td>
                </tr>
            `).join('');
            
            // Update Dota
            document.getElementById('dota-total').textContent = data.dota_props.length;
            document.getElementById('dota-ev').textContent = 
                data.dota_props.filter(p => p.ev > 0).length;
            
            const dotaBody = document.getElementById('dota-body');
            dotaBody.innerHTML = data.dota_props.map(p => `
                <tr>
                    <td style="color: #C9A961;">${p.player}</td>
                    <td>${p.stat_type}</td>
                    <td>${p.line}</td>
                    <td style="color: #C9A961; font-weight: bold;">${p.prediction}</td>
                    <td class="${p.edge > 0 ? 'positive' : ''}">${p.edge}%</td>
                    <td class="${p.pick}">${p.pick.toUpperCase()}</td>
                    <td class="${p.ev > 0 ? 'positive' : ''}">${p.ev}%</td>
                </tr>
            `).join('');
        }
        
        function showSection(section) {
            document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
            event.target.classList.add('active');
            
            document.getElementById('ncaab-section').style.display = 
                section === 'ncaab' ? 'block' : 'none';
            document.getElementById('dota-section').style.display = 
                section === 'dota' ? 'block' : 'none';
        }
        
        loadData();
        setInterval(loadData, 30000);
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html)

@app.get("/api/all")
async def get_all_props():
    return {
        "ncaab_props": STATE["ncaab_props"],
        "dota_props": STATE["dota_props"],
        "last_update": STATE["last_update"].isoformat() if STATE["last_update"] else None
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
