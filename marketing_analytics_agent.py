#!/usr/bin/env python3
"""
PeerPlay Marketing Analytics Agent
Comprehensive UA performance analysis with cohort tracking and ROAS decomposition
"""

from google.cloud import bigquery
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import json

class MarketingAnalyticsAgent:
    def __init__(self, project_id: str, dataset: str = 'analytics'):
        """Initialize the analytics agent"""
        self.client = bigquery.Client(project=project_id)
        self.dataset = dataset
        self.project_id = project_id
        
        # KPI Targets
        self.targets = {
            'offerwall': {
                'roas_d90': 1.00,  # 100% net ROAS by day 90
                'min_chapter3_cvr': 0.08,  # 8% conversion to chapter 3
            },
            'non_offerwall': {
                'roas_d365': 1.00,  # 100% net ROAS by day 365
                'roas_d180': 0.90,  # 90% by day 180 (on track)
                'min_d7_retention': 0.15,  # 15% D7 retention
                'target_d7_retention': 0.20,  # 20% D7 retention (healthy)
            }
        }
        
        # Alert thresholds
        self.alert_thresholds = {
            'cpi_spike': 0.20,  # 20% day-over-day increase
            'volume_drop': 0.30,  # 30% day-over-day decrease
            'retention_drop': 0.10,  # 10% drop in retention
            'roas_drop': 0.15,  # 15% drop in ROAS
        }

    def daily_health_check(self, date: Optional[str] = None) -> Dict:
        """
        Daily performance monitoring - flags anomalies and critical issues
        
        Args:
            date: Date to check (YYYY-MM-DD), defaults to yesterday
            
        Returns:
            Dict with health metrics and alerts
        """
        if date is None:
            check_date = (datetime.now() - timedelta(days=1)).date()
        else:
            check_date = datetime.strptime(date, '%Y-%m-%d').date()
        
        prev_date = check_date - timedelta(days=1)
        
        # Get daily metrics
        query = f"""
        WITH daily_metrics AS (
            SELECT 
                date,
                source,
                campaign_type,
                SUM(installs) as installs,
                SUM(spend) as spend,
                AVG(cpi) as cpi
            FROM `{self.project_id}.{self.dataset}.ua_daily_summary`
            WHERE date IN ('{check_date}', '{prev_date}')
            GROUP BY 1, 2, 3
        ),
        current_day AS (
            SELECT * FROM daily_metrics WHERE date = '{check_date}'
        ),
        previous_day AS (
            SELECT * FROM daily_metrics WHERE date = '{prev_date}'
        )
        SELECT 
            c.source,
            c.campaign_type,
            c.installs as current_installs,
            p.installs as prev_installs,
            c.spend as current_spend,
            p.spend as prev_spend,
            c.cpi as current_cpi,
            p.cpi as prev_cpi,
            SAFE_DIVIDE(c.installs - p.installs, p.installs) as volume_change,
            SAFE_DIVIDE(c.cpi - p.cpi, p.cpi) as cpi_change
        FROM current_day c
        LEFT JOIN previous_day p USING (source, campaign_type)
        """
        
        df = self.client.query(query).to_dataframe()
        
        # Identify alerts
        alerts = []
        strong_performers = []
        
        for _, row in df.iterrows():
            # Critical alerts
            if row['cpi_change'] > self.alert_thresholds['cpi_spike']:
                alerts.append({
                    'severity': 'high',
                    'source': row['source'],
                    'issue': f"CPI spiked {row['cpi_change']*100:.1f}% to ${row['current_cpi']:.2f}",
                    'recommendation': 'Review bid strategy and audience targeting'
                })
            
            if row['volume_change'] < -self.alert_thresholds['volume_drop']:
                alerts.append({
                    'severity': 'high',
                    'source': row['source'],
                    'issue': f"Volume dropped {abs(row['volume_change'])*100:.1f}% to {row['current_installs']:.0f} installs",
                    'recommendation': 'Check for technical issues or paused campaigns'
                })
            
            # Strong performers
            if row['volume_change'] > 0.25 and row['cpi_change'] < 0.05:
                strong_performers.append({
                    'source': row['source'],
                    'performance': f"Scaled {row['volume_change']*100:.1f}% while maintaining CPI at ${row['current_cpi']:.2f}"
                })
        
        # Calculate totals
        total_current_spend = df['current_spend'].sum()
        total_prev_spend = df['prev_spend'].sum()
        total_current_installs = df['current_installs'].sum()
        total_prev_installs = df['prev_installs'].sum()
        
        return {
            'date': str(check_date),
            'overview': {
                'total_spend': total_current_spend,
                'spend_change_pct': (total_current_spend - total_prev_spend) / total_prev_spend,
                'total_installs': total_current_installs,
                'installs_change_pct': (total_current_installs - total_prev_installs) / total_prev_installs,
                'blended_cpi': total_current_spend / total_current_installs if total_current_installs > 0 else 0
            },
            'critical_alerts': alerts,
            'strong_performers': strong_performers,
            'source_details': df.to_dict('records')
        }

    def weekly_cohort_analysis(self, week_end_date: Optional[str] = None) -> Dict:
        """
        Week-over-week cohort comparison with ROAS decomposition
        
        Args:
            week_end_date: End date of week to analyze (YYYY-MM-DD)
            
        Returns:
            Dict with cohort analysis and ROAS attribution
        """
        if week_end_date is None:
            week_end = datetime.now().date()
        else:
            week_end = datetime.strptime(week_end_date, '%Y-%m-%d').date()
        
        # Define cohort periods
        week2_end = week_end
        week2_start = week2_end - timedelta(days=6)
        week1_end = week2_start - timedelta(days=1)
        week1_start = week1_end - timedelta(days=6)
        
        # Get cohort metrics at D7
        query = f"""
        WITH cohort_installs AS (
            SELECT 
                install_date,
                source,
                campaign_type,
                SUM(installs) as cohort_size,
                SUM(spend) as cohort_spend,
                AVG(cpi) as avg_cpi
            FROM `{self.project_id}.{self.dataset}.ua_daily_summary`
            WHERE install_date BETWEEN '{week1_start}' AND '{week2_end}'
            GROUP BY 1, 2, 3
        ),
        cohort_retention AS (
            SELECT 
                install_date,
                source,
                campaign_type,
                AVG(CASE WHEN cohort_day = 1 THEN retention_rate END) as d1_retention,
                AVG(CASE WHEN cohort_day = 7 THEN retention_rate END) as d7_retention
            FROM `{self.project_id}.{self.dataset}.cohort_retention`
            WHERE install_date BETWEEN '{week1_start}' AND '{week2_end}'
            GROUP BY 1, 2, 3
        ),
        cohort_revenue AS (
            SELECT 
                install_date,
                source,
                campaign_type,
                MAX(CASE WHEN cohort_day = 7 THEN cumulative_arpu END) as d7_arpu,
                MAX(CASE WHEN cohort_day = 7 THEN ftd_rate END) as d7_ftd_rate
            FROM `{self.project_id}.{self.dataset}.cohort_revenue`
            WHERE install_date BETWEEN '{week1_start}' AND '{week2_end}'
            GROUP BY 1, 2, 3
        )
        SELECT 
            i.install_date,
            i.source,
            i.campaign_type,
            i.cohort_size,
            i.cohort_spend,
            i.avg_cpi,
            r.d1_retention,
            r.d7_retention,
            rev.d7_arpu,
            rev.d7_ftd_rate,
            SAFE_DIVIDE(rev.d7_arpu, i.avg_cpi) as d7_roas
        FROM cohort_installs i
        LEFT JOIN cohort_retention r USING (install_date, source, campaign_type)
        LEFT JOIN cohort_revenue rev USING (install_date, source, campaign_type)
        WHERE i.cohort_size >= 10
        ORDER BY i.install_date DESC
        """
        
        df = self.client.query(query).to_dataframe()
        
        # Aggregate by week
        df['week'] = df['install_date'].apply(
            lambda x: 'week2' if x >= week2_start else 'week1'
        )
        
        week_summary = df.groupby(['week', 'source', 'campaign_type']).agg({
            'cohort_size': 'sum',
            'cohort_spend': 'sum',
            'avg_cpi': 'mean',
            'd1_retention': 'mean',
            'd7_retention': 'mean',
            'd7_arpu': 'mean',
            'd7_ftd_rate': 'mean',
            'd7_roas': 'mean'
        }).reset_index()
        
        # Compare weeks
        week1 = week_summary[week_summary['week'] == 'week1']
        week2 = week_summary[week_summary['week'] == 'week2']
        
        comparison = week2.merge(
            week1,
            on=['source', 'campaign_type'],
            suffixes=('_w2', '_w1')
        )
        
        # Calculate changes and attribution
        comparison['roas_change'] = comparison['d7_roas_w2'] - comparison['d7_roas_w1']
        comparison['roas_change_pct'] = comparison['roas_change'] / comparison['d7_roas_w1']
        
        # ROAS decomposition
        comparison['retention_impact'] = (
            (comparison['d7_retention_w2'] - comparison['d7_retention_w1']) / 
            comparison['d7_retention_w1']
        )
        comparison['monetization_impact'] = (
            (comparison['d7_arpu_w2'] - comparison['d7_arpu_w1']) / 
            comparison['d7_arpu_w1']
        )
        comparison['cost_impact'] = -(
            (comparison['avg_cpi_w2'] - comparison['avg_cpi_w1']) / 
            comparison['avg_cpi_w1']
        )
        
        return {
            'period': {
                'week1': f"{week1_start} to {week1_end}",
                'week2': f"{week2_start} to {week2_end}"
            },
            'overall_metrics': {
                'week1_roas': float(week1['d7_roas'].mean()),
                'week2_roas': float(week2['d7_roas'].mean()),
                'week1_retention': float(week1['d7_retention'].mean()),
                'week2_retention': float(week2['d7_retention'].mean()),
                'week1_cpi': float(week1['avg_cpi'].mean()),
                'week2_cpi': float(week2['avg_cpi'].mean()),
            },
            'source_comparisons': comparison.to_dict('records'),
            'raw_data': df.to_dict('records')
        }

    def source_deep_dive(self, source: str, lookback_weeks: int = 8) -> Dict:
        """
        Detailed analysis of a specific source with historical trends
        
        Args:
            source: Source name to analyze
            lookback_weeks: Number of weeks of history to include
            
        Returns:
            Dict with comprehensive source analysis
        """
        end_date = datetime.now().date()
        start_date = end_date - timedelta(weeks=lookback_weeks)
        
        # Get weekly cohort performance
        query = f"""
        WITH weekly_cohorts AS (
            SELECT 
                DATE_TRUNC(install_date, WEEK) as week_start,
                source,
                SUM(installs) as installs,
                SUM(spend) as spend,
                AVG(cpi) as cpi
            FROM `{self.project_id}.{self.dataset}.ua_daily_summary`
            WHERE source = '{source}'
                AND install_date >= '{start_date}'
            GROUP BY 1, 2
        ),
        weekly_retention AS (
            SELECT 
                DATE_TRUNC(install_date, WEEK) as week_start,
                source,
                AVG(CASE WHEN cohort_day = 1 THEN retention_rate END) as d1_retention,
                AVG(CASE WHEN cohort_day = 7 THEN retention_rate END) as d7_retention,
                AVG(CASE WHEN cohort_day = 30 THEN retention_rate END) as d30_retention
            FROM `{self.project_id}.{self.dataset}.cohort_retention`
            WHERE source = '{source}'
                AND install_date >= '{start_date}'
            GROUP BY 1, 2
        ),
        weekly_revenue AS (
            SELECT 
                DATE_TRUNC(install_date, WEEK) as week_start,
                source,
                AVG(CASE WHEN cohort_day = 7 THEN cumulative_arpu END) as d7_arpu,
                AVG(CASE WHEN cohort_day = 30 THEN cumulative_arpu END) as d30_arpu
            FROM `{self.project_id}.{self.dataset}.cohort_revenue`
            WHERE source = '{source}'
                AND install_date >= '{start_date}'
            GROUP BY 1, 2
        )
        SELECT 
            c.week_start,
            c.installs,
            c.spend,
            c.cpi,
            r.d1_retention,
            r.d7_retention,
            r.d30_retention,
            rev.d7_arpu,
            rev.d30_arpu,
            SAFE_DIVIDE(rev.d7_arpu, c.cpi) as d7_roas,
            SAFE_DIVIDE(rev.d30_arpu, c.cpi) as d30_roas
        FROM weekly_cohorts c
        LEFT JOIN weekly_retention r USING (week_start, source)
        LEFT JOIN weekly_revenue rev USING (week_start, source)
        ORDER BY c.week_start DESC
        """
        
        df = self.client.query(query).to_dataframe()
        
        # Trend analysis
        recent_4_weeks = df.head(4)
        previous_4_weeks = df.iloc[4:8] if len(df) >= 8 else df.tail(4)
        
        trends = {
            'cpi_trend': 'increasing' if recent_4_weeks['cpi'].mean() > previous_4_weeks['cpi'].mean() else 'decreasing',
            'retention_trend': 'improving' if recent_4_weeks['d7_retention'].mean() > previous_4_weeks['d7_retention'].mean() else 'declining',
            'roas_trend': 'improving' if recent_4_weeks['d7_roas'].mean() > previous_4_weeks['d7_roas'].mean() else 'declining',
        }
        
        return {
            'source': source,
            'current_week': {
                'cpi': float(df.iloc[0]['cpi']),
                'd7_retention': float(df.iloc[0]['d7_retention']),
                'd7_roas': float(df.iloc[0]['d7_roas']),
                'installs_per_day': float(df.iloc[0]['installs'] / 7),
            },
            'trends': trends,
            'historical_data': df.to_dict('records'),
            'summary_stats': {
                'avg_cpi_8_weeks': float(df['cpi'].mean()),
                'avg_d7_retention_8_weeks': float(df['d7_retention'].mean()),
                'avg_d7_roas_8_weeks': float(df['d7_roas'].mean()),
            }
        }

    def offerwall_chapter_analysis(self, lookback_days: int = 30) -> Dict:
        """
        Analyze offerwall chapter progression and CVRs
        
        Args:
            lookback_days: Days of data to analyze
            
        Returns:
            Dict with chapter CVR analysis
        """
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=lookback_days)
        
        query = f"""
        SELECT 
            source,
            chapter,
            SUM(users_started) as total_started,
            SUM(users_completed) as total_completed,
            SAFE_DIVIDE(SUM(users_completed), SUM(users_started)) as cvr,
            AVG(avg_days_to_complete) as avg_days,
            SUM(revenue_generated) as total_revenue
        FROM `{self.project_id}.{self.dataset}.offerwall_chapters`
        WHERE install_date >= '{start_date}'
        GROUP BY 1, 2
        ORDER BY 1, 2
        """
        
        df = self.client.query(query).to_dataframe()
        
        # Calculate progression through funnel
        chapter_funnel = df.groupby('source').apply(
            lambda x: {
                'chapter_1_cvr': float(x[x['chapter'] == 1]['cvr'].iloc[0]) if len(x[x['chapter'] == 1]) > 0 else 0,
                'chapter_3_cvr': float(x[x['chapter'] == 3]['cvr'].iloc[0]) if len(x[x['chapter'] == 3]) > 0 else 0,
                'chapter_5_cvr': float(x[x['chapter'] == 5]['cvr'].iloc[0]) if len(x[x['chapter'] == 5]) > 0 else 0,
            }
        ).to_dict()
        
        return {
            'period': f"{start_date} to {end_date}",
            'by_source': chapter_funnel,
            'detailed_data': df.to_dict('records')
        }

# CLI interface for direct usage
if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='PeerPlay Marketing Analytics')
    parser.add_argument('--project-id', required=True, help='BigQuery project ID')
    parser.add_argument('--action', required=True, 
                       choices=['daily', 'weekly', 'source', 'offerwall'],
                       help='Analysis type')
    parser.add_argument('--source', help='Source name for source analysis')
    parser.add_argument('--date', help='Date for analysis (YYYY-MM-DD)')
    parser.add_argument('--output', help='Output file path (JSON)')
    
    args = parser.parse_args()
    
    agent = MarketingAnalyticsAgent(project_id=args.project_id)
    
    if args.action == 'daily':
        result = agent.daily_health_check(date=args.date)
    elif args.action == 'weekly':
        result = agent.weekly_cohort_analysis(week_end_date=args.date)
    elif args.action == 'source':
        if not args.source:
            print("Error: --source required for source analysis")
            exit(1)
        result = agent.source_deep_dive(source=args.source)
    elif args.action == 'offerwall':
        result = agent.offerwall_chapter_analysis()
    
    # Output results
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(result, f, indent=2)
        print(f"Results saved to {args.output}")
    else:
        print(json.dumps(result, indent=2))