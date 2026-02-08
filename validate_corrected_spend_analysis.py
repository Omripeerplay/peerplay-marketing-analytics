#!/usr/bin/env python3
"""
Comprehensive 7-Day Analysis Validation Script
Tests the corrected marketing analytics agent using actual ua_cohort spend data
Feb 1-7, 2026 validation period
"""

import os
import sys
import json
import pandas as pd
from datetime import datetime, timedelta
from marketing_analytics_agent import MarketingAnalyticsAgent

def validate_spend_totals(agent, start_date, end_date):
    """Validate that we're getting actual spend data from ua_cohort table"""
    
    print("=== SPEND VALIDATION TEST ===")
    
    # Query actual spend totals directly from ua_cohort
    query = f"""
    SELECT 
        install_date,
        SUM(cost) as daily_spend,
        SUM(installs) as daily_installs,
        SAFE_DIVIDE(SUM(cost), SUM(installs)) as blended_cpi,
        COUNT(DISTINCT mediasource) as active_sources
    FROM `yotam-395120.peerplay.ua_cohort`
    WHERE install_date BETWEEN '{start_date}' AND '{end_date}'
    GROUP BY install_date
    ORDER BY install_date
    """
    
    df = agent.client.query(query).to_dataframe()
    
    total_spend = df['daily_spend'].sum() if len(df) > 0 else 0
    avg_daily_spend = df['daily_spend'].mean() if len(df) > 0 else 0
    
    print(f"📊 7-Day Spend Validation (Feb 1-7, 2026):")
    print(f"   Total 7-Day Spend: ${total_spend:,.2f}")
    print(f"   Average Daily Spend: ${avg_daily_spend:,.2f}")
    print(f"   Expected ~$393K: {'✅ PASS' if total_spend > 350000 else '❌ FAIL'}")
    print(f"   Expected ~$56K/day: {'✅ PASS' if avg_daily_spend > 50000 else '❌ FAIL'}")
    
    # Daily breakdown
    print(f"\n📅 Daily Spend Breakdown:")
    for _, row in df.iterrows():
        print(f"   {row['install_date']}: ${row['daily_spend']:,.2f} ({row['daily_installs']:,.0f} installs, CPI: ${row['blended_cpi']:.2f})")
    
    return {
        'total_7day_spend': float(total_spend),
        'avg_daily_spend': float(avg_daily_spend),
        'daily_breakdown': df.to_dict('records'),
        'validation_passed': total_spend > 350000 and avg_daily_spend > 50000
    }

def validate_source_spend_levels(agent, start_date, end_date):
    """Validate specific source spend levels"""
    
    print("\n=== SOURCE SPEND VALIDATION ===")
    
    # Query source-level spend
    query = f"""
    SELECT 
        mediasource,
        SUM(cost) as total_spend,
        SUM(cost) / 7 as avg_daily_spend,
        SUM(installs) as total_installs,
        SAFE_DIVIDE(SUM(cost), SUM(installs)) as avg_cpi,
        COUNT(DISTINCT install_date) as active_days
    FROM `yotam-395120.peerplay.ua_cohort`
    WHERE install_date BETWEEN '{start_date}' AND '{end_date}'
    GROUP BY mediasource
    HAVING SUM(cost) > 1000  -- Filter out minimal sources
    ORDER BY total_spend DESC
    """
    
    df = agent.client.query(query).to_dataframe()
    
    print(f"🎯 Top Source Spend Validation:")
    
    # Check key sources
    almedia_spend = df[df['mediasource'] == 'almedia']['avg_daily_spend'].iloc[0] if 'almedia' in df['mediasource'].values else 0
    adjoe_spend = df[df['mediasource'] == 'adjoe']['avg_daily_spend'].iloc[0] if 'adjoe' in df['mediasource'].values else 0
    
    print(f"   almedia daily spend: ${almedia_spend:,.2f} (Expected ~$21K: {'✅' if almedia_spend > 15000 else '❌'})")
    print(f"   adjoe daily spend: ${adjoe_spend:,.2f} (Expected ~$9K: {'✅' if adjoe_spend > 7000 else '❌'})")
    
    print(f"\n📈 Top 10 Sources by Spend:")
    for i, (_, row) in enumerate(df.head(10).iterrows()):
        print(f"   {i+1:2d}. {row['mediasource']:<20} ${row['avg_daily_spend']:>8,.0f}/day (${row['total_spend']:>10,.0f} total, CPI: ${row['avg_cpi']:>6.2f})")
    
    return {
        'top_sources': df.head(20).to_dict('records'),
        'almedia_daily_spend': float(almedia_spend) if almedia_spend else 0,
        'adjoe_daily_spend': float(adjoe_spend) if adjoe_spend else 0,
        'validation_passed': almedia_spend > 15000 and adjoe_spend > 7000
    }

def run_comprehensive_analysis(agent, test_dates):
    """Run complete marketing analytics suite"""
    
    print("\n=== COMPREHENSIVE ANALYSIS EXECUTION ===")
    
    results = {}
    
    # 1. Daily Health Checks for each day
    print(f"📊 Running Daily Health Checks...")
    daily_results = []
    for date_str in test_dates:
        daily_result = agent.daily_health_check(date=date_str)
        daily_results.append(daily_result)
        
        # Quick summary
        overview = daily_result['overview']
        alerts = len(daily_result['critical_alerts'])
        print(f"   {date_str}: ${overview['total_spend']:,.0f} spend, {overview['total_installs']:,.0f} installs, {alerts} alerts")
    
    results['daily_health_checks'] = daily_results
    
    # 2. Weekly Cohort Analysis
    print(f"📊 Running Weekly Cohort Analysis...")
    weekly_result = agent.weekly_cohort_analysis(week_end_date='2026-02-07')
    print(f"   Week 2 ROAS: {weekly_result['overall_metrics']['week2_roas']:.3f}")
    print(f"   Week 2 Retention: {weekly_result['overall_metrics']['week2_retention']:.3f}")
    print(f"   Week 2 CPI: ${weekly_result['overall_metrics']['week2_cpi']:.2f}")
    
    results['weekly_cohort_analysis'] = weekly_result
    
    # 3. Source Deep Dives for top sources
    print(f"📊 Running Source Deep Dives...")
    source_analyses = {}
    top_sources = ['almedia', 'adjoe', 'adcolony', 'fyber']
    
    for source in top_sources:
        try:
            source_result = agent.source_deep_dive(source=source, lookback_weeks=4)
            source_analyses[source] = source_result
            print(f"   {source}: CPI ${source_result['current_week']['cpi']:.2f}, D7 ROAS {source_result['current_week']['d7_roas']:.3f}")
        except Exception as e:
            print(f"   {source}: Analysis failed - {str(e)}")
    
    results['source_deep_dives'] = source_analyses
    
    # 4. Platform Breakdown
    print(f"📊 Running Platform Analysis...")
    platform_query = f"""
    SELECT 
        platform,
        SUM(cost) as total_spend,
        SUM(cost) / 7 as avg_daily_spend,
        SUM(installs) as total_installs,
        SAFE_DIVIDE(SUM(cost), SUM(installs)) as avg_cpi,
        AVG(d7_retention) as avg_d7_retention,
        AVG(d7_total_net_revenue) as avg_d7_arpu,
        SAFE_DIVIDE(AVG(d7_total_net_revenue), SAFE_DIVIDE(SUM(cost), SUM(installs))) as d7_roas
    FROM `yotam-395120.peerplay.ua_cohort`
    WHERE install_date BETWEEN '2026-02-01' AND '2026-02-07'
    GROUP BY platform
    ORDER BY total_spend DESC
    """
    
    platform_df = agent.client.query(platform_query).to_dataframe()
    results['platform_breakdown'] = platform_df.to_dict('records')
    
    for _, row in platform_df.iterrows():
        print(f"   {row['platform']}: ${row['avg_daily_spend']:,.0f}/day, CPI ${row['avg_cpi']:.2f}, D7 ROAS {row['d7_roas']:.3f}")
    
    return results

def generate_action_items(analysis_results, validation_results):
    """Generate prioritized action items based on actual data"""
    
    print("\n=== GENERATING ACTION ITEMS ===")
    
    action_items = []
    
    # Spend validation issues
    if not validation_results['spend_validation']['validation_passed']:
        action_items.append({
            'priority': 'HIGH',
            'category': 'Data Quality',
            'action': 'Investigate spend data discrepancy - expected $393K total but found different amount',
            'impact': 'Critical for accurate ROAS calculations'
        })
    
    if not validation_results['source_validation']['validation_passed']:
        action_items.append({
            'priority': 'HIGH', 
            'category': 'Data Quality',
            'action': 'Validate top source spend levels - almedia and adjoe not matching expected daily spend',
            'impact': 'Affects budget allocation decisions'
        })
    
    # Performance-based actions from daily health checks
    all_alerts = []
    for daily in analysis_results['daily_health_checks']:
        all_alerts.extend(daily['critical_alerts'])
    
    # Group alerts by source and severity
    high_priority_sources = []
    for alert in all_alerts:
        if alert['severity'] == 'high' and alert['source'] not in high_priority_sources:
            high_priority_sources.append(alert['source'])
            action_items.append({
                'priority': 'HIGH',
                'category': 'Performance',
                'action': f"Review {alert['source']} performance: {alert['issue']}",
                'impact': alert['recommendation']
            })
    
    # ROAS-based actions from weekly analysis
    weekly = analysis_results['weekly_cohort_analysis']
    if weekly['overall_metrics']['week2_roas'] < 0.8:
        action_items.append({
            'priority': 'MEDIUM',
            'category': 'ROAS',
            'action': f"Overall D7 ROAS below 0.8 at {weekly['overall_metrics']['week2_roas']:.3f}",
            'impact': 'Review bidding strategies and audience targeting'
        })
    
    # Source-specific actions
    for source, analysis in analysis_results['source_deep_dives'].items():
        if analysis['trends']['roas_trend'] == 'declining':
            action_items.append({
                'priority': 'MEDIUM',
                'category': 'Source Optimization',
                'action': f"Address declining ROAS trend in {source}",
                'impact': f"Current D7 ROAS: {analysis['current_week']['d7_roas']:.3f}"
            })
        
        if analysis['trends']['cpi_trend'] == 'increasing':
            action_items.append({
                'priority': 'MEDIUM',
                'category': 'Cost Control', 
                'action': f"Investigate rising CPI in {source}",
                'impact': f"Current CPI: ${analysis['current_week']['cpi']:.2f}"
            })
    
    # Budget reallocation opportunities
    for platform in analysis_results['platform_breakdown']:
        if platform['d7_roas'] > 1.0 and platform['avg_daily_spend'] > 10000:
            action_items.append({
                'priority': 'LOW',
                'category': 'Scale Opportunity',
                'action': f"Consider scaling {platform['platform']} - profitable at scale",
                'impact': f"D7 ROAS: {platform['d7_roas']:.3f}, ${platform['avg_daily_spend']:,.0f}/day spend"
            })
    
    # Sort by priority
    priority_order = {'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
    action_items.sort(key=lambda x: priority_order[x['priority']])
    
    print(f"🎯 Generated {len(action_items)} Action Items:")
    for i, item in enumerate(action_items[:10]):  # Show top 10
        print(f"   {i+1:2d}. [{item['priority']}] {item['category']}: {item['action']}")
    
    return action_items

def main():
    """Main execution function"""
    
    print("🚀 MARKETING ANALYTICS VALIDATION - CORRECTED SPEND DATA")
    print("=" * 60)
    
    # Initialize agent
    agent = MarketingAnalyticsAgent(project_id='yotam-395120')
    
    # Test period
    start_date = '2026-02-01'
    end_date = '2026-02-07'
    test_dates = ['2026-02-01', '2026-02-02', '2026-02-03', '2026-02-04', 
                  '2026-02-05', '2026-02-06', '2026-02-07']
    
    # 1. Validate Spend Accuracy
    spend_validation = validate_spend_totals(agent, start_date, end_date)
    
    # 2. Validate Source Spend Levels  
    source_validation = validate_source_spend_levels(agent, start_date, end_date)
    
    # 3. Run Comprehensive Analysis
    analysis_results = run_comprehensive_analysis(agent, test_dates)
    
    # 4. Generate Action Items
    validation_results = {
        'spend_validation': spend_validation,
        'source_validation': source_validation
    }
    action_items = generate_action_items(analysis_results, validation_results)
    
    # 5. Compile Final Results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    final_results = {
        'validation_summary': {
            'test_period': f"{start_date} to {end_date}",
            'timestamp': timestamp,
            'spend_validation_passed': spend_validation['validation_passed'],
            'source_validation_passed': source_validation['validation_passed'],
            'total_7day_spend': spend_validation['total_7day_spend'],
            'avg_daily_spend': spend_validation['avg_daily_spend'],
            'almedia_daily_spend': source_validation['almedia_daily_spend'],
            'adjoe_daily_spend': source_validation['adjoe_daily_spend']
        },
        'detailed_validations': validation_results,
        'comprehensive_analysis': analysis_results,
        'prioritized_actions': action_items
    }
    
    # Save results
    output_file = f'corrected_spend_validation_{timestamp}.json'
    with open(output_file, 'w') as f:
        json.dump(final_results, f, indent=2, default=str)
    
    print(f"\n✅ VALIDATION COMPLETE")
    print(f"📁 Results saved to: {output_file}")
    
    # Summary
    print(f"\n📊 VALIDATION SUMMARY:")
    print(f"   Spend Data Validation: {'✅ PASSED' if spend_validation['validation_passed'] else '❌ FAILED'}")
    print(f"   Source Level Validation: {'✅ PASSED' if source_validation['validation_passed'] else '❌ FAILED'}")
    print(f"   Total 7-Day Spend: ${spend_validation['total_7day_spend']:,.2f}")
    print(f"   Action Items Generated: {len(action_items)}")
    
    return output_file

if __name__ == '__main__':
    output_file = main()
    print(f"\nValidation script completed. Results in: {output_file}")