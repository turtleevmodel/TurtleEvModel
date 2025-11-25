"""
Dota 2 Betting Dashboard
Professional UI with real-time updates
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import sqlite3
import json
from datetime import datetime
import asyncio
import subprocess
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
    "predictions": [],
    "props": [],
    "last_update": None,
    "model_performance": {},
    "is_updating": False
}

def get_database_stats():
    """Get database statistics"""
    try:
        conn = sqlite3.connect('data/dota_data.db')
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(DISTINCT player_name) FROM player_stats")
        total_players = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM player_stats")
        total_matches = cursor.fetchone()[0]
        
        cursor.execute("SELECT MAX(match_date) FROM player_stats")
        last_update = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "total_players": total_players,
            "total_matches": total_matches,
            "last_data_update": last_update
        }
    except:
        return {
            "total_players": 0,
            "total_matches": 0,
            "last_data_update": None
        }

async def load_predictions():
    """Load predictions from database"""
    global STATE
    
    try:
        conn = sqlite3.connect('data/dota_props.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Get predictions
        cursor.execute("""
            SELECT 
                p.player,
                p.stat_type,
                p.line,
                pr.prediction,
                pr.lower_bound,
                pr.upper_bound,
                pr.edge,
                pr.pick_direction as pick,
                pr.confidence,
                pr.ev,
                p.game_info
            FROM dota_props p
            LEFT JOIN predictions pr
                ON p.player = pr.player
                AND p.stat_type = pr.stat_type
                AND p.line = pr.line
            WHERE p.line > 0
            ORDER BY ABS(pr.ev) DESC
        """)
        
        predictions = []
        for row in cursor.fetchall():
            predictions.append(dict(row))
        
        # Get props without predictions
        cursor.execute("""
            SELECT player, stat_type, line, game_info
            FROM dota_props
            WHERE line > 0
        """)
        
        props = []
        for row in cursor.fetchall():
            props.append(dict(row))
        
        conn.close()
        
        STATE["predictions"] = predictions
        STATE["props"] = props
        STATE["last_update"] = datetime.now()
        
    except Exception as e:
        print(f"Error loading predictions: {e}")

async def update_system():
    """Run the prediction pipeline"""
    global STATE
    
    if STATE["is_updating"]:
        return
    
    STATE["is_updating"] = True
    
    try:
        # Run data pipeline
        subprocess.run(["python3", "scripts/dota_data_pipeline.py"], timeout=300)
        
        # Run predictions
        subprocess.run(["python3", "scripts/dota_predictions.py"], timeout=120)
        
        # Reload predictions
        await load_predictions()
        
    except Exception as e:
        print(f"Update error: {e}")
    
    STATE["is_updating"] = False

@app.on_event("startup")
async def startup():
    await load_predictions()
    
    # Schedule updates
    async def update_loop():
        while True:
            await asyncio.sleep(1800)  # 30 minutes
            await update_system()
    
    asyncio.create_task(update_loop())

@app.get("/")
async def home():
    """Main dashboard"""
    html = """
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
            line-height: 1.6;
        }
        
        .header {
            background: linear-gradient(135deg, #1a1a1a, #0f0f0f);
            padding: 30px;
            border-bottom: 3px solid #C9A961;
        }
        
        .header h1 {
            color: #C9A961;
            font-size: 36px;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 15px;
        }
        
        .subtitle {
            color: #888;
            font-size: 14px;
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
            background: rgba(201, 169, 97, 0.08);
            transform: translateY(-2px);
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
        
        .controls {
            display: flex;
            gap: 15px;
            margin-bottom: 20px;
            flex-wrap: wrap;
        }
        
        .btn {
            background: #C9A961;
            color: #000;
            border: none;
            padding: 12px 24px;
            border-radius: 5px;
            font-weight: bold;
            cursor: pointer;
            transition: all 0.3s;
            text-transform: uppercase;
            font-size: 12px;
            letter-spacing: 1px;
        }
        
        .btn:hover {
            background: #b89650;
            transform: translateY(-2px);
        }
        
        .btn.secondary {
            background: #333;
            color: #C9A961;
        }
        
        .filter-input {
            background: #1a1a1a;
            border: 1px solid #333;
            color: #fff;
            padding: 10px;
            border-radius: 5px;
            flex: 1;
            min-width: 200px;
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
            position: sticky;
            top: 0;
            z-index: 10;
        }
        
        td {
            padding: 12px 15px;
            border-bottom: 1px solid rgba(51, 51, 51, 0.5);
        }
        
        tr:hover {
            background: rgba(201, 169, 97, 0.03);
        }
        
        .player-name {
            color: #C9A961;
            font-weight: 600;
        }
        
        .pick-over {
            color: #10b981;
            font-weight: bold;
        }
        
        .pick-under {
            color: #ef4444;
            font-weight: bold;
        }
        
        .pick-pass {
            color: #666;
        }
        
        .positive {
            color: #10b981;
            font-weight: bold;
        }
        
        .negative {
            color: #ef4444;
        }
        
        .confidence-high {
            color: #10b981;
        }
        
        .confidence-med {
            color: #C9A961;
        }
        
        .confidence-low {
            color: #ef4444;
        }
        
        .loading {
            text-align: center;
            padding: 40px;
            color: #888;
        }
        
        .update-indicator {
            display: inline-block;
            width: 10px;
            height: 10px;
            background: #10b981;
            border-radius: 50%;
            margin-left: 10px;
            animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
        }
        
        .tabs {
            display: flex;
            gap: 10px;
            margin-bottom: 20px;
            border-bottom: 2px solid #333;
        }
        
        .tab {
            padding: 12px 24px;
            background: none;
            color: #888;
            border: none;
            cursor: pointer;
            transition: all 0.3s;
            font-weight: 600;
        }
        
        .tab.active {
            color: #C9A961;
            border-bottom: 2px solid #C9A961;
            margin-bottom: -2px;
        }
        
        .tab:hover {
            color: #C9A961;
        }
        
        @media (max-width: 768px) {
            .stats-grid {
                grid-template-columns: repeat(2, 1fr);
            }
            
            .header h1 {
                font-size: 24px;
            }
            
            table {
                font-size: 14px;
            }
            
            td, th {
                padding: 8px;
            }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>
            🎮 TURTLE +EV
            <span style="font-size: 20px; color: #888;">DOTA 2</span>
            <span class="update-indicator"></span>
        </h1>
        <p class="subtitle">XGBoost ML Predictions | OpenDota Stats | Real-Time Props</p>
    </div>
    
    <div class="container">
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value" id="total-props">-</div>
                <div class="stat-label">Total Props</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="ev-count">-</div>
                <div class="stat-label">+EV Bets</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="best-edge">-</div>
                <div class="stat-label">Best Edge</div>
            </div>
            <div class="stat-card">
                <div class="stat-value" id="avg-confidence">-</div>
                <div class="stat-label">Avg Confidence</div>
            </div>
        </div>
        
        <div class="tabs">
            <button class="tab active" onclick="showTab('predictions')">Predictions</button>
            <button class="tab" onclick="showTab('all-props')">All Props</button>
            <button class="tab" onclick="showTab('stats')">Model Stats</button>
        </div>
        
        <div class="controls">
            <input type="text" class="filter-input" id="search" placeholder="Search player..." onkeyup="filterTable()">
            <button class="btn" onclick="refreshData()">Refresh</button>
            <button class="btn secondary" onclick="exportData()">Export CSV</button>
        </div>
        
        <div id="predictions-tab">
            <table id="predictions-table">
                <thead>
                    <tr>
                        <th>Player</th>
                        <th>Stat</th>
                        <th>Line</th>
                        <th>Prediction</th>
                        <th>Range</th>
                        <th>Edge</th>
                        <th>Pick</th>
                        <th>Confidence</th>
                        <th>EV</th>
                    </tr>
                </thead>
                <tbody id="predictions-body">
                    <tr class="loading">
                        <td colspan="9">Loading predictions...</td>
                    </tr>
                </tbody>
            </table>
        </div>
        
        <div id="all-props-tab" style="display:none;">
            <table>
                <thead>
                    <tr>
                        <th>Player</th>
                        <th>Stat</th>
                        <th>Line</th>
                        <th>Game Info</th>
                    </tr>
                </thead>
                <tbody id="props-body">
                    <tr class="loading">
                        <td colspan="4">Loading props...</td>
                    </tr>
                </tbody>
            </table>
        </div>
        
        <div id="stats-tab" style="display:none;">
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value" id="total-players">-</div>
                    <div class="stat-label">Players Tracked</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="total-matches">-</div>
                    <div class="stat-label">Matches Analyzed</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="model-accuracy">-</div>
                    <div class="stat-label">Model Accuracy</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value" id="last-updated">-</div>
                    <div class="stat-label">Last Update</div>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        let currentData = {};
        let currentTab = 'predictions';
        
        async function loadData() {
            try {
                const response = await fetch('/api/predictions');
                const data = await response.json();
                currentData = data;
                updateUI(data);
            } catch (error) {
                console.error('Error loading data:', error);
            }
        }
        
        function updateUI(data) {
            // Update stats
            const totalProps = data.props ? data.props.length : 0;
            const predictions = data.predictions || [];
            const evBets = predictions.filter(p => p.ev && p.ev > 0);
            const bestEdge = predictions.length > 0 ? 
                Math.max(...predictions.map(p => Math.abs(p.edge || 0))) : 0;
            const avgConfidence = predictions.length > 0 ?
                predictions.reduce((sum, p) => sum + (p.confidence || 0), 0) / predictions.length : 0;
            
            document.getElementById('total-props').textContent = totalProps;
            document.getElementById('ev-count').textContent = evBets.length;
            document.getElementById('best-edge').textContent = bestEdge.toFixed(1) + '%';
            document.getElementById('avg-confidence').textContent = (avgConfidence * 100).toFixed(1) + '%';
            
            // Update predictions table
            const tbody = document.getElementById('predictions-body');
            
            if (predictions.length === 0) {
                tbody.innerHTML = '<tr class="loading"><td colspan="9">No predictions available</td></tr>';
            } else {
                tbody.innerHTML = predictions.map(p => {
                    const pickClass = p.pick === 'over' ? 'pick-over' : 
                                    p.pick === 'under' ? 'pick-under' : 'pick-pass';
                    const evClass = p.ev > 0 ? 'positive' : p.ev < 0 ? 'negative' : '';
                    const confClass = p.confidence > 0.65 ? 'confidence-high' :
                                     p.confidence > 0.55 ? 'confidence-med' : 'confidence-low';
                    
                    const range = p.lower_bound && p.upper_bound ? 
                        `${p.lower_bound.toFixed(1)}-${p.upper_bound.toFixed(1)}` : '-';
                    
                    return `
                        <tr>
                            <td class="player-name">${p.player || '-'}</td>
                            <td>${p.stat_type || '-'}</td>
                            <td>${p.line ? p.line.toFixed(1) : '-'}</td>
                            <td>${p.prediction ? p.prediction.toFixed(1) : '-'}</td>
                            <td>${range}</td>
                            <td class="${p.edge > 0 ? 'positive' : 'negative'}">
                                ${p.edge ? p.edge.toFixed(1) + '%' : '-'}
                            </td>
                            <td class="${pickClass}">${(p.pick || '-').toUpperCase()}</td>
                            <td class="${confClass}">
                                ${p.confidence ? (p.confidence * 100).toFixed(1) + '%' : '-'}
                            </td>
                            <td class="${evClass}">
                                ${p.ev ? p.ev.toFixed(1) + '%' : '-'}
                            </td>
                        </tr>
                    `;
                }).join('');
            }
            
            // Update props table
            const propsBody = document.getElementById('props-body');
            if (data.props && data.props.length > 0) {
                propsBody.innerHTML = data.props.map(p => `
                    <tr>
                        <td class="player-name">${p.player}</td>
                        <td>${p.stat_type}</td>
                        <td>${p.line.toFixed(1)}</td>
                        <td style="color: #888; font-size: 12px;">${p.game_info || '-'}</td>
                    </tr>
                `).join('');
            }
            
            // Update database stats
            if (data.db_stats) {
                document.getElementById('total-players').textContent = data.db_stats.total_players || '-';
                document.getElementById('total-matches').textContent = data.db_stats.total_matches || '-';
            }
            
            if (data.last_update) {
                const lastUpdate = new Date(data.last_update);
                document.getElementById('last-updated').textContent = lastUpdate.toLocaleTimeString();
            }
        }
        
        function showTab(tab) {
            currentTab = tab;
            
            // Update tab buttons
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            event.target.classList.add('active');
            
            // Show/hide content
            document.getElementById('predictions-tab').style.display = 
                tab === 'predictions' ? 'block' : 'none';
            document.getElementById('all-props-tab').style.display = 
                tab === 'all-props' ? 'block' : 'none';
            document.getElementById('stats-tab').style.display = 
                tab === 'stats' ? 'block' : 'none';
        }
        
        function filterTable() {
            const search = document.getElementById('search').value.toLowerCase();
            const rows = document.querySelectorAll('#predictions-body tr');
            
            rows.forEach(row => {
                const text = row.textContent.toLowerCase();
                row.style.display = text.includes(search) ? '' : 'none';
            });
        }
        
        async function refreshData() {
            await loadData();
        }
        
        function exportData() {
            if (!currentData.predictions) return;
            
            let csv = 'Player,Stat,Line,Prediction,Edge,Pick,Confidence,EV\\n';
            
            currentData.predictions.forEach(p => {
                csv += `${p.player},${p.stat_type},${p.line},${p.prediction},`;
                csv += `${p.edge},${p.pick},${p.confidence},${p.ev}\\n`;
            });
            
            const blob = new Blob([csv], { type: 'text/csv' });
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'dota2_predictions.csv';
            a.click();
        }
        
        // Load data on page load
        loadData();
        
        // Auto-refresh every 60 seconds
        setInterval(loadData, 60000);
    </script>
</body>
</html>
    """
    return HTMLResponse(content=html)

@app.get("/api/predictions")
async def get_predictions():
    """API endpoint for predictions"""
    db_stats = get_database_stats()
    
    return {
        "predictions": STATE["predictions"],
        "props": STATE["props"],
        "last_update": STATE["last_update"].isoformat() if STATE["last_update"] else None,
        "db_stats": db_stats,
        "is_updating": STATE["is_updating"]
    }

@app.post("/api/update")
async def trigger_update():
    """Manually trigger system update"""
    if STATE["is_updating"]:
        return {"status": "already_updating"}
    
    asyncio.create_task(update_system())
    return {"status": "update_started"}

@app.get("/api/stats")
async def get_stats():
    """Get detailed statistics"""
    try:
        conn = sqlite3.connect('data/dota_data.db')
        cursor = conn.cursor()
        
        # Get player performance stats
        cursor.execute("""
            SELECT 
                player_name,
                COUNT(*) as games,
                AVG(kills) as avg_kills,
                AVG(fantasy_points) as avg_fantasy,
                MAX(kills) as max_kills,
                MAX(fantasy_points) as max_fantasy
            FROM player_stats
            GROUP BY player_name
            ORDER BY games DESC
            LIMIT 20
        """)
        
        top_players = []
        for row in cursor.fetchall():
            top_players.append({
                "player": row[0],
                "games": row[1],
                "avg_kills": round(row[2], 1),
                "avg_fantasy": round(row[3], 1),
                "max_kills": row[4],
                "max_fantasy": round(row[5], 1)
            })
        
        conn.close()
        
        return {
            "top_players": top_players,
            "last_update": STATE["last_update"].isoformat() if STATE["last_update"] else None
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
