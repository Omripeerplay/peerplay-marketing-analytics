#!/usr/bin/env python3
"""
Yesterday's Marketing Performance Analysis - February 8, 2026
Comprehensive analysis using corrected ua_cohort table with actual spend data
"""

import json
import pandas as pd
from google.cloud import bigquery
from datetime import datetime, timedelta
import os

def execute_marketing_analysis():
    """Execute comprehensive marketing analysis for February 8, 2026"""
    
    # Initialize BigQuery client
    client = bigquery.Client(project='yotam-395120')
    
    # Main comprehensive query
    query = """
    -- Yesterday's Marketing Performance Analysis (Feb 8, 2026)
    -- Comprehensive analysis with actual spend data from ua_cohort table

    WITH yesterday_performance AS (
      SELECT 
        install_date,
        platform,
        media_source,
        campaign,
        SUM(cost) AS total_spend,
        COUNT(DISTINCT player_id) AS total_installs,
        SAFE_DIVIDE(SUM(cost), COUNT(DISTINCT player_id)) AS cpi,
        SUM(CASE WHEN purchase_date IS NOT NULL THEN purchase_amount ELSE 0 END) AS total_revenue,
        SAFE_DIVIDE(SUM(CASE WHEN purchase_date IS NOT NULL THEN purchase_amount ELSE 0 END), SUM(cost)) AS roas
      FROM `yotam-395120.peerplay.ua_cohort`
      WHERE install_date = '2026-02-08'
        AND country_code = 'US'
        AND currency = 'USD'
      GROUP BY install_date, platform, media_source, campaign
    ),

    previous_day_performance AS (
      SELECT 
        install_date,
        platform,
        media_source,
        campaign,
        SUM(cost) AS total_spend,
        COUNT(DISTINCT player_id) AS total_installs,
        SAFE_DIVIDE(SUM(cost), COUNT(DISTINCT player_id)) AS cpi,
        SUM(CASE WHEN purchase_date IS NOT NULL THEN purchase_amount ELSE 0 END) AS total_revenue,
        SAFE_DIVIDE(SUM(CASE WHEN purchase_date IS NOT NULL THEN purchase_amount ELSE 0 END), SUM(cost)) AS roas
      FROM `yotam-395120.peerplay.ua_cohort`
      WHERE install_date = '2026-02-07'
        AND country_code = 'US'
        AND currency = 'USD'
      GROUP BY install_date, platform, media_source, campaign
    ),

    -- Daily Summary Comparison
    daily_summary AS (
      SELECT
        '2026-02-08' AS analysis_date,
        'Yesterday' AS period_label,
        SUM(total_spend) AS daily_spend,
        SUM(total_installs) AS daily_installs,
        SAFE_DIVIDE(SUM(total_spend), SUM(total_installs)) AS overall_cpi,
        SUM(total_revenue) AS daily_revenue,
        SAFE_DIVIDE(SUM(total_revenue), SUM(total_spend)) AS overall_roas
      FROM yesterday_performance
      
      UNION ALL
      
      SELECT
        '2026-02-07' AS analysis_date,
        'Previous Day' AS period_label,
        SUM(total_spend) AS daily_spend,
        SUM(total_installs) AS daily_installs,
        SAFE_DIVIDE(SUM(total_spend), SUM(total_installs)) AS overall_cpi,
        SUM(total_revenue) AS daily_revenue,
        SAFE_DIVIDE(SUM(total_revenue), SUM(total_spend)) AS overall_roas
      FROM previous_day_performance
    ),

    -- Platform Breakdown
    platform_breakdown AS (
      SELECT
        platform,
        SUM(total_spend) AS platform_spend,
        SUM(total_installs) AS platform_installs,
        SAFE_DIVIDE(SUM(total_spend), SUM(total_installs)) AS platform_cpi,
        SUM(total_revenue) AS platform_revenue,
        SAFE_DIVIDE(SUM(total_revenue), SUM(total_spend)) AS platform_roas,
        ROUND(SAFE_DIVIDE(SUM(total_spend), (SELECT SUM(total_spend) FROM yesterday_performance)) * 100, 1) AS spend_share_pct
      FROM yesterday_performance
      GROUP BY platform
      ORDER BY platform_spend DESC
    ),

    -- Source Performance with Day-over-Day Changes
    source_performance AS (
      SELECT
        y.media_source,
        y.total_spend AS yesterday_spend,
        y.total_installs AS yesterday_installs,
        y.cpi AS yesterday_cpi,
        y.roas AS yesterday_roas,
        COALESCE(p.total_spend, 0) AS previous_spend,
        COALESCE(p.total_installs, 0) AS previous_installs,
        COALESCE(p.cpi, 0) AS previous_cpi,
        COALESCE(p.roas, 0) AS previous_roas,
        SAFE_DIVIDE(y.total_spend - COALESCE(p.total_spend, 0), COALESCE(p.total_spend, 1)) * 100 AS spend_change_pct,
        SAFE_DIVIDE(y.total_installs - COALESCE(p.total_installs, 0), COALESCE(p.total_installs, 1)) * 100 AS installs_change_pct,
        SAFE_DIVIDE(y.cpi - COALESCE(p.cpi, 0), COALESCE(p.cpi, 1)) * 100 AS cpi_change_pct,
        SAFE_DIVIDE(y.roas - COALESCE(p.roas, 0), COALESCE(p.roas, 1)) * 100 AS roas_change_pct
      FROM (
        SELECT 
          media_source, 
          SUM(total_spend) AS total_spend, 
          SUM(total_installs) AS total_installs,
          SAFE_DIVIDE(SUM(total_spend), SUM(total_installs)) AS cpi,
          SAFE_DIVIDE(SUM(total_revenue), SUM(total_spend)) AS roas
        FROM yesterday_performance 
        GROUP BY media_source
      ) y
      LEFT JOIN (
        SELECT 
          media_source, 
          SUM(total_spend) AS total_spend, 
          SUM(total_installs) AS total_installs,
          SAFE_DIVIDE(SUM(total_spend), SUM(total_installs)) AS cpi,
          SAFE_DIVIDE(SUM(total_revenue), SUM(total_spend)) AS roas
        FROM previous_day_performance 
        GROUP BY media_source
      ) p ON y.media_source = p.media_source
      ORDER BY y.total_spend DESC
    ),

    -- Performance Alerts
    performance_alerts AS (
      SELECT
        media_source,
        yesterday_spend,
        yesterday_cpi,
        yesterday_roas,
        cpi_change_pct,
        installs_change_pct,
        roas_change_pct,
        CASE 
          WHEN cpi_change_pct > 20 AND yesterday_spend > 1000 THEN 'CRITICAL: CPI Spike >20%'
          WHEN installs_change_pct < -30 AND yesterday_spend > 1000 THEN 'CRITICAL: Volume Drop >30%'
          WHEN yesterday_spend > 5000 AND yesterday_cpi > 8.0 THEN 'WARNING: High CPI on High Spend'
          WHEN yesterday_roas < 0.3 AND yesterday_spend > 2000 THEN 'WARNING: Low ROAS'
          WHEN roas_change_pct < -25 AND yesterday_spend > 1000 THEN 'WARNING: ROAS Decline >25%'
          ELSE 'MONITOR'
        END AS alert_level,
        CASE 
          WHEN cpi_change_pct > 20 AND yesterday_spend > 1000 THEN 'Reduce spend or investigate targeting'
          WHEN installs_change_pct < -30 AND yesterday_spend > 1000 THEN 'Check campaign status and bid adjustments'
          WHEN yesterday_spend > 5000 AND yesterday_cpi > 8.0 THEN 'Consider pausing or reducing budget'
          WHEN yesterday_roas < 0.3 AND yesterday_spend > 2000 THEN 'Immediate optimization needed'
          WHEN roas_change_pct < -25 AND yesterday_spend > 1000 THEN 'Review creative and targeting'
          ELSE 'Continue monitoring'
        END AS recommended_action
      FROM source_performance
      WHERE (
        (cpi_change_pct > 20 AND yesterday_spend > 1000) OR 
        (installs_change_pct < -30 AND yesterday_spend > 1000) OR 
        (yesterday_spend > 5000 AND yesterday_cpi > 8.0) OR 
        (yesterday_roas < 0.3 AND yesterday_spend > 2000) OR
        (roas_change_pct < -25 AND yesterday_spend > 1000)
      )
    ),

    -- Top Campaigns Analysis
    top_campaigns AS (
      SELECT
        media_source,
        campaign,
        platform,
        SUM(total_spend) AS campaign_spend,
        SUM(total_installs) AS campaign_installs,
        SAFE_DIVIDE(SUM(total_spend), SUM(total_installs)) AS campaign_cpi,
        SAFE_DIVIDE(SUM(total_revenue), SUM(total_spend)) AS campaign_roas,
        RANK() OVER (ORDER BY SUM(total_spend) DESC) AS spend_rank,
        RANK() OVER (ORDER BY SAFE_DIVIDE(SUM(total_revenue), SUM(total_spend)) DESC) AS roas_rank
      FROM yesterday_performance
      GROUP BY media_source, campaign, platform
      HAVING SUM(total_spend) > 500
      ORDER BY campaign_spend DESC
    )

    -- Output all sections
    SELECT 'DAILY_SUMMARY' AS section, 
           analysis_date, period_label, 
           ROUND(daily_spend, 2) AS daily_spend, 
           daily_installs, 
           ROUND(overall_cpi, 2) AS overall_cpi, 
           ROUND(daily_revenue, 2) AS daily_revenue, 
           ROUND(overall_roas, 3) AS overall_roas,
           NULL AS platform, NULL AS media_source, NULL AS campaign, NULL AS alert_info
    FROM daily_summary

    UNION ALL

    SELECT 'PLATFORM_BREAKDOWN' AS section,
           '2026-02-08' AS analysis_date, 
           platform AS period_label,
           ROUND(platform_spend, 2) AS daily_spend, 
           platform_installs AS daily_installs, 
           ROUND(platform_cpi, 2) AS overall_cpi, 
           ROUND(platform_revenue, 2) AS daily_revenue, 
           ROUND(platform_roas, 3) AS overall_roas,
           platform, NULL AS media_source, NULL AS campaign, 
           CONCAT(spend_share_pct, '% of total spend') AS alert_info
    FROM platform_breakdown

    UNION ALL

    SELECT 'SOURCE_PERFORMANCE' AS section,
           '2026-02-08' AS analysis_date, 
           'Top Sources' AS period_label,
           ROUND(yesterday_spend, 2) AS daily_spend, 
           yesterday_installs AS daily_installs,
           ROUND(yesterday_cpi, 2) AS overall_cpi, 
           NULL AS daily_revenue, 
           ROUND(yesterday_roas, 3) AS overall_roas,
           NULL AS platform, 
           media_source, 
           NULL AS campaign,
           CONCAT('Spend: ', ROUND(spend_change_pct, 1), '% | CPI: ', ROUND(cpi_change_pct, 1), '% | ROAS: ', ROUND(roas_change_pct, 1), '%') AS alert_info
    FROM source_performance
    WHERE yesterday_spend > 100

    UNION ALL

    SELECT 'PERFORMANCE_ALERTS' AS section,
           '2026-02-08' AS analysis_date, 
           alert_level AS period_label,
           ROUND(yesterday_spend, 2) AS daily_spend, 
           NULL AS daily_installs, 
           ROUND(yesterday_cpi, 2) AS overall_cpi,
           NULL AS daily_revenue, 
           ROUND(yesterday_roas, 3) AS overall_roas,
           NULL AS platform, 
           media_source, 
           NULL AS campaign,
           recommended_action AS alert_info
    FROM performance_alerts

    UNION ALL

    SELECT 'TOP_CAMPAIGNS' AS section,
           '2026-02-08' AS analysis_date,
           CONCAT('Rank #', spend_rank) AS period_label,
           ROUND(campaign_spend, 2) AS daily_spend,
           campaign_installs AS daily_installs,
           ROUND(campaign_cpi, 2) AS overall_cpi,
           NULL AS daily_revenue,
           ROUND(campaign_roas, 3) AS overall_roas,
           platform,
           media_source,
           campaign,
           CONCAT('ROAS Rank: #', roas_rank) AS alert_info
    FROM top_campaigns
    WHERE spend_rank <= 10

    ORDER BY 
      CASE section 
        WHEN 'DAILY_SUMMARY' THEN 1
        WHEN 'PLATFORM_BREAKDOWN' THEN 2  
        WHEN 'SOURCE_PERFORMANCE' THEN 3
        WHEN 'PERFORMANCE_ALERTS' THEN 4
        WHEN 'TOP_CAMPAIGNS' THEN 5
      END,
      daily_spend DESC;
    """
    
    print("Executing comprehensive marketing analysis for February 8, 2026...")
    print("=" * 80)
    
    # Execute query
    try:
        job_config = bigquery.QueryJobConfig(
            use_query_cache=True,
            use_legacy_sql=False
        )
        
        query_job = client.query(query, job_config=job_config)
        results = query_job.result()
        
        # Convert to DataFrame
        df = results.to_dataframe()
        
        if df.empty:
            print("❌ No data found for February 8, 2026. Please check the date and ua_cohort table.")
            return None
            
        # Process and display results by section
        sections = df['section'].unique()
        
        analysis_summary = {
            'analysis_date': '2026-02-08',
            'total_sections': len(sections),
            'sections': {}
        }
        
        for section in ['DAILY_SUMMARY', 'PLATFORM_BREAKDOWN', 'SOURCE_PERFORMANCE', 'PERFORMANCE_ALERTS', 'TOP_CAMPAIGNS']:
            if section in sections:
                section_df = df[df['section'] == section].copy()
                
                print(f"\n{'='*20} {section.replace('_', ' ')} {'='*20}")
                
                if section == 'DAILY_SUMMARY':
                    display_daily_summary(section_df)
                    analysis_summary['sections']['daily_summary'] = section_df.to_dict('records')
                    
                elif section == 'PLATFORM_BREAKDOWN':
                    display_platform_breakdown(section_df)
                    analysis_summary['sections']['platform_breakdown'] = section_df.to_dict('records')
                    
                elif section == 'SOURCE_PERFORMANCE':
                    display_source_performance(section_df)
                    analysis_summary['sections']['source_performance'] = section_df.to_dict('records')
                    
                elif section == 'PERFORMANCE_ALERTS':
                    display_performance_alerts(section_df)
                    analysis_summary['sections']['performance_alerts'] = section_df.to_dict('records')
                    
                elif section == 'TOP_CAMPAIGNS':
                    display_top_campaigns(section_df)
                    analysis_summary['sections']['top_campaigns'] = section_df.to_dict('records')
        
        # Generate action items
        print(f"\n{'='*20} ACTION ITEMS & RECOMMENDATIONS {'='*20}")
        generate_action_items(df)
        
        # Save detailed results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save to CSV
        csv_filename = f"yesterday_marketing_analysis_{timestamp}.csv"
        df.to_csv(csv_filename, index=False)
        
        # Save summary to JSON
        json_filename = f"yesterday_marketing_summary_{timestamp}.json"
        with open(json_filename, 'w') as f:
            json.dump(analysis_summary, f, indent=2, default=str)
            
        print(f"\n📊 Analysis complete!")
        print(f"📁 Detailed results saved to: {csv_filename}")
        print(f"📄 Summary saved to: {json_filename}")
        
        return analysis_summary
        
    except Exception as e:
        print(f"❌ Error executing analysis: {str(e)}")
        return None

def display_daily_summary(df):
    """Display daily summary comparison"""
    print("\n📈 DAILY PERFORMANCE OVERVIEW")
    print("-" * 50)
    
    for _, row in df.iterrows():
        period = row['period_label']
        spend = f"${row['daily_spend']:,.2f}" if pd.notna(row['daily_spend']) else "N/A"
        installs = f"{int(row['daily_installs']):,}" if pd.notna(row['daily_installs']) else "N/A"
        cpi = f"${row['overall_cpi']:.2f}" if pd.notna(row['overall_cpi']) else "N/A"
        revenue = f"${row['daily_revenue']:,.2f}" if pd.notna(row['daily_revenue']) else "N/A"
        roas = f"{row['overall_roas']:.3f}" if pd.notna(row['overall_roas']) else "N/A"
        
        print(f"{period:12} | Spend: {spend:>12} | Installs: {installs:>8} | CPI: {cpi:>7} | Revenue: {revenue:>12} | ROAS: {roas:>6}")
    
    # Calculate day-over-day changes
    if len(df) >= 2:
        yesterday = df[df['period_label'] == 'Yesterday'].iloc[0]
        previous = df[df['period_label'] == 'Previous Day'].iloc[0]
        
        if pd.notna(yesterday['daily_spend']) and pd.notna(previous['daily_spend']) and previous['daily_spend'] > 0:
            spend_change = ((yesterday['daily_spend'] - previous['daily_spend']) / previous['daily_spend']) * 100
            installs_change = ((yesterday['daily_installs'] - previous['daily_installs']) / previous['daily_installs']) * 100 if previous['daily_installs'] > 0 else 0
            cpi_change = ((yesterday['overall_cpi'] - previous['overall_cpi']) / previous['overall_cpi']) * 100 if previous['overall_cpi'] > 0 else 0
            
            print("\n📊 Day-over-Day Changes:")
            print(f"   Spend: {spend_change:+.1f}% | Installs: {installs_change:+.1f}% | CPI: {cpi_change:+.1f}%")

def display_platform_breakdown(df):
    """Display platform performance breakdown"""
    print("\n📱 PLATFORM PERFORMANCE")
    print("-" * 70)
    print("Platform    | Spend         | Installs | CPI     | Revenue      | ROAS   | Share")
    print("-" * 70)
    
    for _, row in df.iterrows():
        platform = row['period_label'][:10]
        spend = f"${row['daily_spend']:,.0f}" if pd.notna(row['daily_spend']) else "N/A"
        installs = f"{int(row['daily_installs']):,}" if pd.notna(row['daily_installs']) else "N/A"
        cpi = f"${row['overall_cpi']:.2f}" if pd.notna(row['overall_cpi']) else "N/A"
        revenue = f"${row['daily_revenue']:,.0f}" if pd.notna(row['daily_revenue']) else "N/A"
        roas = f"{row['overall_roas']:.3f}" if pd.notna(row['overall_roas']) else "N/A"
        share = row['alert_info'] if pd.notna(row['alert_info']) else "N/A"
        
        print(f"{platform:11} | {spend:>13} | {installs:>8} | {cpi:>7} | {revenue:>12} | {roas:>6} | {share}")

def display_source_performance(df):
    """Display top source performance"""
    print("\n🎯 TOP MEDIA SOURCES PERFORMANCE")
    print("-" * 90)
    print("Media Source                 | Spend      | Installs | CPI     | ROAS   | Changes")
    print("-" * 90)
    
    for _, row in df.iterrows():
        source = (row['media_source'] or 'Unknown')[:28]
        spend = f"${row['daily_spend']:,.0f}" if pd.notna(row['daily_spend']) else "N/A"
        installs = f"{int(row['daily_installs']):,}" if pd.notna(row['daily_installs']) else "N/A"
        cpi = f"${row['overall_cpi']:.2f}" if pd.notna(row['overall_cpi']) else "N/A"
        roas = f"{row['overall_roas']:.3f}" if pd.notna(row['overall_roas']) else "N/A"
        changes = (row['alert_info'] or 'N/A')[:25] if pd.notna(row['alert_info']) else "N/A"
        
        print(f"{source:28} | {spend:>10} | {installs:>8} | {cpi:>7} | {roas:>6} | {changes}")

def display_performance_alerts(df):
    """Display critical performance alerts"""
    print("\n🚨 CRITICAL PERFORMANCE ALERTS")
    print("-" * 80)
    
    if df.empty:
        print("✅ No critical alerts - all sources performing within normal ranges")
        return
    
    print("Alert Level              | Source                | Spend    | CPI     | ROAS")
    print("-" * 80)
    
    for _, row in df.iterrows():
        alert_level = (row['period_label'] or 'Unknown')[:24]
        source = (row['media_source'] or 'Unknown')[:20]
        spend = f"${row['daily_spend']:,.0f}" if pd.notna(row['daily_spend']) else "N/A"
        cpi = f"${row['overall_cpi']:.2f}" if pd.notna(row['overall_cpi']) else "N/A"
        roas = f"{row['overall_roas']:.3f}" if pd.notna(row['overall_roas']) else "N/A"
        
        print(f"{alert_level:24} | {source:20} | {spend:>8} | {cpi:>7} | {roas:>5}")
        
        # Show recommended action
        if pd.notna(row['alert_info']):
            print(f"   → Action: {row['alert_info']}")
        print()

def display_top_campaigns(df):
    """Display top campaign performance"""
    print("\n🏆 TOP CAMPAIGNS BY SPEND")
    print("-" * 100)
    print("Rank | Media Source          | Campaign                    | Platform | Spend    | CPI     | ROAS")
    print("-" * 100)
    
    for _, row in df.iterrows():
        rank = (row['period_label'] or 'Unknown')[6:]  # Remove "Rank #"
        source = (row['media_source'] or 'Unknown')[:20]
        campaign = (row['campaign'] or 'Unknown')[:26]
        platform = (row['platform'] or 'Unknown')[:8]
        spend = f"${row['daily_spend']:,.0f}" if pd.notna(row['daily_spend']) else "N/A"
        cpi = f"${row['overall_cpi']:.2f}" if pd.notna(row['overall_cpi']) else "N/A"
        roas = f"{row['overall_roas']:.3f}" if pd.notna(row['overall_roas']) else "N/A"
        
        print(f"{rank:4} | {source:20} | {campaign:26} | {platform:8} | {spend:>8} | {cpi:>7} | {roas:>5}")

def generate_action_items(df):
    """Generate actionable recommendations"""
    print("\n🎯 IMMEDIATE ACTION ITEMS FOR TODAY:")
    print("-" * 50)
    
    # Analyze alerts
    alerts_df = df[df['section'] == 'PERFORMANCE_ALERTS']
    
    if not alerts_df.empty:
        critical_alerts = alerts_df[alerts_df['period_label'].str.contains('CRITICAL', na=False)]
        warning_alerts = alerts_df[alerts_df['period_label'].str.contains('WARNING', na=False)]
        
        if not critical_alerts.empty:
            print("🔴 CRITICAL ACTIONS (Do Now):")
            for _, alert in critical_alerts.iterrows():
                print(f"   • {alert['media_source']}: {alert['alert_info']}")
            print()
            
        if not warning_alerts.empty:
            print("🟡 WARNING ACTIONS (Monitor Closely):")
            for _, alert in warning_alerts.iterrows():
                print(f"   • {alert['media_source']}: {alert['alert_info']}")
            print()
    
    # Budget optimization opportunities
    source_df = df[df['section'] == 'SOURCE_PERFORMANCE']
    
    if not source_df.empty:
        # Find high-spend, high-CPI sources
        high_cpi_sources = source_df[
            (pd.to_numeric(source_df['daily_spend'], errors='coerce') > 2000) &
            (pd.to_numeric(source_df['overall_cpi'], errors='coerce') > 7.0)
        ]
        
        if not high_cpi_sources.empty:
            print("💰 BUDGET OPTIMIZATION:")
            for _, source in high_cpi_sources.iterrows():
                spend = source['daily_spend']
                cpi = source['overall_cpi']
                print(f"   • Consider reducing {source['media_source']} (${spend:,.0f} spend, ${cpi:.2f} CPI)")
            print()
    
    # Scaling opportunities
    campaigns_df = df[df['section'] == 'TOP_CAMPAIGNS']
    
    if not campaigns_df.empty:
        top_roas_campaigns = campaigns_df.head(3)
        print("📈 SCALING OPPORTUNITIES:")
        for _, campaign in top_roas_campaigns.iterrows():
            if pd.notna(campaign['overall_roas']) and campaign['overall_roas'] > 0.5:
                print(f"   • Scale {campaign['media_source']} - {campaign['campaign']} (ROAS: {campaign['overall_roas']:.3f})")
        print()
    
    print("📋 DAILY MONITORING CHECKLIST:")
    print("   • Review all CRITICAL alerts and take immediate action")
    print("   • Monitor CPI trends for sources with >$2K daily spend")
    print("   • Check campaign performance vs targets")
    print("   • Verify no budget caps are limiting high-performing campaigns")
    print("   • Update bid adjustments based on performance data")

if __name__ == "__main__":
    execute_marketing_analysis()