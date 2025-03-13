# services/dashboard_service.py
from datetime import datetime, timedelta
from sqlalchemy import func, and_, or_
import pandas as pd

from models.bet import Bet
from models.user_model import User
from models.subscription import Subscription
from models.leaderboard_model import LeaderboardEntry
from services.bet_service import BetService

class DashboardService:
    @staticmethod
    def get_user_metrics(user_id):
        """
        Calculate key metrics for a user's dashboard
        
        Args:
            user_id (int): ID of the user
            
        Returns:
            dict: Dictionary containing user metrics
        """
        # Get user from database
        user = User.query.get(user_id)
        if not user:
            return None
        
        # Get user's bets for calculating metrics
        all_bets = Bet.query.filter_by(user_id=user_id).all()
        settled_bets = [bet for bet in all_bets if bet.status != 'pending']
        
        # Calculate win rate
        win_rate = DashboardService._calculate_win_rate(settled_bets)
        
        # Calculate win rate trend
        win_rate_trend = DashboardService._calculate_trend_metric(
            user_id, 
            DashboardService._calculate_period_win_rate,
            30, # Current period (last 30 days)
            60  # Previous period (30-60 days ago)
        )
        
        # Calculate total profit
        total_profit = sum(bet.profit for bet in settled_bets if hasattr(bet, 'profit'))
        
        # Calculate profit trend
        profit_trend = DashboardService._calculate_trend_metric(
            user_id,
            DashboardService._calculate_period_profit,
            30,
            60
        )
        
        # Get clutch picks metrics
        clutch_picks = BetService.get_clutch_picks_count(user_id)
        
        # Calculate clutch picks trend
        now = datetime.now()
        one_month_ago = now - timedelta(days=30)
        two_months_ago = now - timedelta(days=60)
        
        current_clutch_picks = BetService.get_clutch_picks_count(user_id, start_date=one_month_ago)
        previous_clutch_picks = BetService.get_clutch_picks_count(user_id, start_date=two_months_ago, end_date=one_month_ago)
        
        clutch_picks_trend = DashboardService._calculate_percentage_change(
            current_clutch_picks, 
            previous_clutch_picks
        )
        
        # Get followers count and trend
        followers_count = DashboardService._get_followers_count(user_id)
        followers_trend = DashboardService._calculate_followers_trend(user_id)
        
        # Compile metrics
        metrics = {
            "winRate": round(win_rate, 1),
            "winRateTrend": round(win_rate_trend, 1),
            "totalProfit": round(total_profit, 2),
            "profitTrend": round(profit_trend, 1),
            "clutchPicks": clutch_picks,
            "clutchPicksTrend": round(clutch_picks_trend, 1),
            "followers": followers_count,
            "followersTrend": round(followers_trend, 1)
        }
        
        return metrics
    
    @staticmethod
    def get_performance_history(user_id, days=180):
        """
        Get historical performance data for charting
        
        Args:
            user_id (int): ID of the user
            days (int): Number of days of history to retrieve
            
        Returns:
            list: List of date/profit pairs for charting
        """
        # Calculate start date for history
        start_date = datetime.now() - timedelta(days=days)
        
        # Get all bets in the period
        bets = Bet.query.filter(
            Bet.user_id == user_id,
            Bet.created_at >= start_date,
            Bet.status != 'pending'
        ).order_by(Bet.created_at).all()
        
        # Convert to pandas DataFrame for analysis
        bet_data = []
        for bet in bets:
            if hasattr(bet, 'profit'):
                bet_data.append({
                    'date': bet.created_at,
                    'profit': bet.profit
                })
        
        if not bet_data:
            # Return empty performance history
            return []
        
        df = pd.DataFrame(bet_data)
        
        # Resample to get biweekly performance data
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        
        # Determine appropriate sampling frequency based on data range
        if days <= 30:
            freq = '1D'  # Daily for short ranges
        elif days <= 90:
            freq = '7D'  # Weekly for medium ranges
        else:
            freq = '15D'  # Biweekly for longer ranges
            
        resampled = df.resample(freq).sum().reset_index()
        
        # Calculate cumulative profit
        resampled['profit'] = resampled['profit'].cumsum()
        
        # Format for chart display
        performance_history = []
        for _, row in resampled.iterrows():
            performance_history.append({
                "date": row['date'].strftime('%b %d'),
                "profit": round(float(row['profit']), 2)
            })
        
        return performance_history
    
    @staticmethod
    def get_recent_activity(user_id, limit=15):
        """
        Get recent user activity for the dashboard
        
        Args:
            user_id (int): ID of the user
            limit (int): Maximum number of activities to return
            
        Returns:
            list: List of recent activity items
        """
        # Get recent bets
        recent_bets = Bet.query.filter_by(user_id=user_id).order_by(Bet.created_at.desc()).limit(limit).all()
        
        # Get recent subscription changes
        recent_subscriptions = Subscription.query.filter_by(user_id=user_id).order_by(Subscription.created_at.desc()).limit(3).all()
        
        # Combine all activities
        activities = []
        
        # Process bets
        for bet in recent_bets:
            activity_type = bet.status if bet.status in ['win', 'loss'] else 'bet'
            
            # Format description based on bet type
            if hasattr(bet, 'event_name') and bet.event_name:
                description = f"{'Won' if bet.status == 'win' else 'Lost' if bet.status == 'loss' else 'Placed'} ${abs(bet.amount)} on {bet.event_name}"
            else:
                description = f"{'Won' if bet.status == 'win' else 'Lost' if bet.status == 'loss' else 'Placed'} ${abs(bet.amount)} bet"
                
            # Add bet profit/loss if applicable
            if bet.status in ['win', 'loss'] and hasattr(bet, 'profit'):
                description += f" (${abs(bet.profit)})"
            
            activities.append({
                "type": activity_type,
                "description": description,
                "time": DashboardService._format_relative_time(bet.created_at),
                "date": bet.created_at
            })
        
        # Process subscriptions
        for sub in recent_subscriptions:
            activities.append({
                "type": "purchase",
                "description": f"Purchased {sub.plan_name} Plan",
                "time": DashboardService._format_relative_time(sub.created_at),
                "date": sub.created_at
            })
        
        # Sort by date and limit
        activities.sort(key=lambda x: x["date"], reverse=True)
        
        # Remove the actual date field from response
        for activity in activities:
            del activity["date"]
        
        return activities[:limit]
    
    # Helper methods
    @staticmethod
    def _calculate_win_rate(bets):
        """Calculate win rate from a list of bets"""
        if not bets:
            return 0
            
        winning_bets = [bet for bet in bets if bet.status == 'win']
        return (len(winning_bets) / len(bets)) * 100
    
    @staticmethod
    def _calculate_period_win_rate(user_id, start_date, end_date=None):
        """Calculate win rate for a specific period"""
        query = Bet.query.filter(
            Bet.user_id == user_id,
            Bet.created_at >= start_date,
            Bet.status != 'pending'
        )
        
        if end_date:
            query = query.filter(Bet.created_at < end_date)
            
        bets = query.all()
        return DashboardService._calculate_win_rate(bets)
    
    @staticmethod
    def _calculate_period_profit(user_id, start_date, end_date=None):
        """Calculate total profit for a specific period"""
        query = Bet.query.filter(
            Bet.user_id == user_id,
            Bet.created_at >= start_date,
            Bet.status != 'pending'
        )
        
        if end_date:
            query = query.filter(Bet.created_at < end_date)
            
        bets = query.all()
        return sum(bet.profit for bet in bets if hasattr(bet, 'profit'))
    
    @staticmethod
    def _calculate_trend_metric(user_id, metric_func, current_period_days, previous_period_days):
        """
        Calculate trend for a metric by comparing current period to previous period
        
        Args:
            user_id (int): User ID
            metric_func (function): Function that calculates the metric for a period
            current_period_days (int): Days in current period
            previous_period_days (int): Days in previous period
            
        Returns:
            float: Percentage change between periods
        """
        now = datetime.now()
        current_period_start = now - timedelta(days=current_period_days)
        previous_period_start = now - timedelta(days=previous_period_days)
        
        current_metric = metric_func(user_id, current_period_start)
        previous_metric = metric_func(user_id, previous_period_start, current_period_start)
        
        return DashboardService._calculate_percentage_change(current_metric, previous_metric)
    
    @staticmethod
    def _calculate_percentage_change(current_value, previous_value):
        """Calculate percentage change between two values"""
        if previous_value == 0:
            return 0  # Avoid division by zero
            
        return ((current_value - previous_value) / abs(previous_value)) * 100
    
    @staticmethod
    def _get_followers_count(user_id):
        """Get number of followers for a user"""
        # This implementation depends on your social model
        user = User.query.get(user_id)
        if user and hasattr(user, 'followers'):
            return len(user.followers)
        elif user and hasattr(user, 'followers_count'):
            return user.followers_count
        return 0
    
    @staticmethod
    def _calculate_followers_trend(user_id):
        """Calculate trend in followers over the last month"""
        # This implementation depends on your social tracking model
        # You might need to adjust based on how you track follower history
        return 0  # Placeholder - implement based on your model
    
    @staticmethod
    def _format_relative_time(timestamp):
        """Format a timestamp as a relative time string (e.g., '2h ago')"""
        time_diff = datetime.now() - timestamp
        
        if time_diff.days > 0:
            return f"{time_diff.days}d ago"
        elif time_diff.seconds >= 3600:
            return f"{time_diff.seconds // 3600}h ago"
        elif time_diff.seconds >= 60:
            return f"{time_diff.seconds // 60}m ago"
        else:
            return "just now"