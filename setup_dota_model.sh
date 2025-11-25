#!/bin/bash

echo "🎮 DOTA 2 BETTING MODEL SETUP"
echo "=============================="

# Create directories
echo "📁 Creating directory structure..."
mkdir -p ~/dota2-model/{scripts,data,models,web,logs}
cd ~/dota2-model

# Install dependencies
echo "📦 Installing Python packages..."
pip install --break-system-packages \
    requests pandas numpy scikit-learn xgboost \
    fastapi uvicorn sqlite3 pickle logging warnings

# Create all the scripts
echo "📝 Creating scripts..."
# [Copy all the Python scripts here using the cat commands above]

# Make scripts executable
chmod +x scripts/*.py
chmod +x setup_dota_model.sh

# Initialize database
echo "🗄️ Initializing database..."
python3 scripts/dota_data_pipeline.py

# Train models
echo "🤖 Training models..."
python3 scripts/train_models.py

# Start dashboard
echo "🚀 Starting dashboard..."
cd web
screen -S dota_dashboard
python3 dota_dashboard.py
# Ctrl+A, D to detach

echo ""
echo "✅ SETUP COMPLETE!"
echo "==================="
echo "Dashboard: http://YOUR_SERVER_IP:8002"
echo "API: http://YOUR_SERVER_IP:8002/api/predictions"
echo ""
echo "To update predictions manually:"
echo "  cd ~/dota2-model"
echo "  python3 scripts/dota_predictions.py"
echo ""
