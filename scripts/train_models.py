"""
Train Dota 2 XGBoost Models
Enhanced with hyperparameter tuning and cross-validation
"""

import sqlite3
import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split, cross_val_score, GridSearchCV
from sklearn.metrics import mean_absolute_error, r2_score
import xgboost as xgb
import pickle
import logging

logging.basicConfig(level=logging.INFO)

def prepare_data():
    """Load and prepare training data"""
    logging.info("Loading data...")
    
    conn = sqlite3.connect('data/dota_data.db')
    
    # Get player stats with more features
    df = pd.read_sql_query("""
        SELECT 
            player_name,
            kills,
            deaths,
            assists,
            gpm,
            xpm,
            last_hits,
            denies,
            hero_damage,
            tower_damage,
            fantasy_points,
            win,
            duration,
            match_date
        FROM player_stats
        ORDER BY match_date DESC
    """, conn)
    
    conn.close()
    
    logging.info(f"Loaded {len(df)} matches")
    
    # Feature engineering
    features_list = []
    
    for player in df['player_name'].unique():
        player_df = df[df['player_name'] == player].copy()
        
        if len(player_df) < 10:
            continue
        
        # Calculate rolling features
        for window in [5, 10, 20]:
            player_df[f'avg_kills_{window}'] = player_df['kills'].shift(1).rolling(window=window, min_periods=window//2).mean()
            player_df[f'avg_fantasy_{window}'] = player_df['fantasy_points'].shift(1).rolling(window=window, min_periods=window//2).mean()
            player_df[f'avg_gpm_{window}'] = player_df['gpm'].shift(1).rolling(window=window, min_periods=window//2).mean()
        
        # Additional features
        player_df['avg_deaths_5'] = player_df['deaths'].shift(1).rolling(window=5, min_periods=3).mean()
        player_df['avg_assists_5'] = player_df['assists'].shift(1).rolling(window=5, min_periods=3).mean()
        player_df['recent_kills'] = player_df['kills'].shift(1).rolling(window=3, min_periods=2).mean()
        player_df['recent_fantasy'] = player_df['fantasy_points'].shift(1).rolling(window=3, min_periods=2).mean()
        
        # Variance (consistency)
        player_df['kills_std_5'] = player_df['kills'].shift(1).rolling(window=5, min_periods=3).std()
        player_df['fantasy_std_5'] = player_df['fantasy_points'].shift(1).rolling(window=5, min_periods=3).std()
        
        # KDA and efficiency
        player_df['avg_kda'] = ((player_df['kills'].shift(1) + player_df['assists'].shift(1)) / 
                                np.maximum(player_df['deaths'].shift(1), 1)).rolling(window=5, min_periods=3).mean()
        
        # Game duration impact
        player_df['avg_duration'] = player_df['duration'].shift(1).rolling(window=5, min_periods=3).mean()
        
        # Trend
        player_df['kills_trend'] = player_df['avg_kills_5'] - player_df['avg_kills_10']
        player_df['fantasy_trend'] = player_df['avg_fantasy_5'] - player_df['avg_fantasy_10']
        
        # Win rate
        player_df['recent_win_rate'] = player_df['win'].shift(1).rolling(window=5, min_periods=3).mean()
        
        # Form indicators
        player_df['form_hot'] = (player_df['avg_kills_5'] > player_df['avg_kills_10'] * 1.1).astype(int)
        player_df['form_cold'] = (player_df['avg_kills_5'] < player_df['avg_kills_10'] * 0.9).astype(int)
        
        features_list.append(player_df)
    
    features_df = pd.concat(features_list, ignore_index=True)
    features_df = features_df.dropna()
    
    logging.info(f"Created features for {len(features_df)} matches")
    
    return features_df

def train_models(features_df):
    """Train XGBoost models with hyperparameter tuning"""
    
    # Define feature columns
    feature_cols = [
        'avg_kills_5', 'avg_kills_10', 'avg_kills_20',
        'avg_fantasy_5', 'avg_fantasy_10', 'avg_fantasy_20',
        'avg_gpm_5', 'avg_gpm_10', 'avg_gpm_20',
        'avg_deaths_5', 'avg_assists_5',
        'recent_kills', 'recent_fantasy',
        'kills_std_5', 'fantasy_std_5',
        'avg_kda', 'avg_duration',
        'kills_trend', 'fantasy_trend',
        'recent_win_rate', 'form_hot', 'form_cold'
    ]
    
    # Remove any missing columns
    feature_cols = [col for col in feature_cols if col in features_df.columns]
    
    X = features_df[feature_cols]
    y_kills = features_df['kills']
    y_fantasy = features_df['fantasy_points']
    
    # Split data
    X_train, X_test, y_kills_train, y_kills_test = train_test_split(
        X, y_kills, test_size=0.2, random_state=42
    )
    
    _, _, y_fantasy_train, y_fantasy_test = train_test_split(
        X, y_fantasy, test_size=0.2, random_state=42
    )
    
    logging.info(f"Training set: {len(X_train)}, Test set: {len(X_test)}")
    
    # Hyperparameter grid
    param_grid = {
        'n_estimators': [100, 150, 200],
        'max_depth': [4, 5, 6],
        'learning_rate': [0.05, 0.1],
        'subsample': [0.8, 0.9],
        'colsample_bytree': [0.8, 0.9]
    }
    
    # Train Kills Model
    logging.info("Training Kills model...")
    
    kills_model = xgb.XGBRegressor(random_state=42, n_jobs=-1)
    
    # Quick grid search (use fewer params for speed)
    quick_params = {
        'n_estimators': [150],
        'max_depth': [5],
        'learning_rate': [0.1],
        'subsample': [0.8]
    }
    
    grid_search = GridSearchCV(
        kills_model, quick_params, cv=3,
        scoring='neg_mean_absolute_error', verbose=1
    )
    
    grid_search.fit(X_train, y_kills_train)
    kills_model = grid_search.best_estimator_
    
    # Evaluate
    kills_pred = kills_model.predict(X_test)
    kills_mae = mean_absolute_error(y_kills_test, kills_pred)
    kills_r2 = r2_score(y_kills_test, kills_pred)
    
    logging.info(f"Kills Model - MAE: {kills_mae:.2f}, R2: {kills_r2:.3f}")
    
    # Train Fantasy Model
    logging.info("Training Fantasy model...")
    
    fantasy_model = xgb.XGBRegressor(random_state=42, n_jobs=-1)
    
    grid_search = GridSearchCV(
        fantasy_model, quick_params, cv=3,
        scoring='neg_mean_absolute_error', verbose=1
    )
    
    grid_search.fit(X_train, y_fantasy_train)
    fantasy_model = grid_search.best_estimator_
    
    # Evaluate
    fantasy_pred = fantasy_model.predict(X_test)
    fantasy_mae = mean_absolute_error(y_fantasy_test, fantasy_pred)
    fantasy_r2 = r2_score(y_fantasy_test, fantasy_pred)
    
    logging.info(f"Fantasy Model - MAE: {fantasy_mae:.2f}, R2: {fantasy_r2:.3f}")
    
    # Feature importance
    logging.info("\nTop Features (Kills):")
    importance = pd.DataFrame({
        'feature': feature_cols,
        'importance': kills_model.feature_importances_
    }).sort_values('importance', ascending=False)
    
    for _, row in importance.head(10).iterrows():
        logging.info(f"  {row['feature']}: {row['importance']:.3f}")
    
    # Save models
    logging.info("Saving models...")
    
    with open('models/dota_kills_model.pkl', 'wb') as f:
        pickle.dump(kills_model, f)
    
    with open('models/dota_fantasy_model.pkl', 'wb') as f:
        pickle.dump(fantasy_model, f)
    
    with open('models/dota_features.pkl', 'wb') as f:
        pickle.dump(feature_cols, f)
    
    logging.info("Models saved successfully!")
    
    return kills_model, fantasy_model, feature_cols

if __name__ == '__main__':
    features_df = prepare_data()
    train_models(features_df)
