from backend.app.ml.model import load_model, predict
from backend.app.services.sentiment_analysis import analyze_sentiment
import numpy as np

def predict_outcome(bet_data, reddit_data=None):
    """
    Generate predictions for a bet based on the AI model
    """
    # Load the prediction model
    model = load_model()
    
    # Prepare features from bet_data
    features = prepare_features(bet_data, reddit_data)
    
    # Get model prediction
    prediction = predict(model, features)
    
    return {
        'predicted_outcome': prediction['outcome'],
        'predicted_ev': prediction['ev'],
        'confidence': prediction['confidence'],
        'hedging_recommendation': generate_hedging_recommendation(prediction)
    }

def prepare_features(bet_data, reddit_data=None):
    """
    Extract and prepare features for the prediction model
    """
    features = {}
    
    # Extract basic bet features
    features['odds'] = bet_data.get('odds')
    features['bet_type'] = bet_data.get('bet_type')
    features['sport'] = bet_data.get('sport')
    
    # Add sentiment analysis if reddit_data is available
    if reddit_data:
        sentiment_scores = analyze_sentiment(reddit_data)
        features['sentiment_score'] = sentiment_scores['compound']
        features['positive_sentiment'] = sentiment_scores['pos']
        features['negative_sentiment'] = sentiment_scores['neg']
    
    # Additional feature engineering would go here
    
    return features

def generate_hedging_recommendation(prediction):
    """
    Generate hedging recommendations based on the prediction
    """
    if prediction['ev'] < -0.1:
        return "Consider hedging this bet as it has negative expected value."
    elif prediction['confidence'] < 0.6:
        return "This bet has low confidence. Consider a smaller stake or hedge."
    else:
        return "This bet has positive expected value. No hedging necessary."