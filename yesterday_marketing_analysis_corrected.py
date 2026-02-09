#!/usr/bin/env python3
"""
Yesterday's Marketing Performance Analysis - February 8, 2026
CORRECTED - Using actual ua_cohort table schema
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
    
    # Main comprehensive query - CORRECTED with proper field names
    query = """
    -- Yesterday's Marketing Performance Analysis (Feb 8, 2026)
    -- Using corrected ua_cohort table schema

    WITH yesterday_performance AS (
      SELECT 
        install_date,
        platform,
        mediasource,
        campaign_name,
        SUM(cost) AS total_spend,
        SUM(installs) AS total_installs,
        SAFE_DIVIDE(SUM(cost), SUM(installs)) AS cpi,
        SUM(d0_total_net_revenue) AS d0_revenue,
        SUM(d1_total_net_revenue) AS d1_revenue, 
        SUM(d7_total_net_revenue) AS d7_revenue,
        SAFE_DIVIDE(SUM(d0_total_net_revenue), SUM(cost)) AS d0_roas,
        SAFE_DIVIDE(SUM(d7_total_net_revenue), SUM(cost)) AS d7_roas
      FROM `yotam-395120.peerplay.ua_cohort`
      WHERE install_date = '2026-02-08'
        AND country = 'US'
        AND cost > 0
        AND installs > 0
        AND is_test_campaign = FALSE
      GROUP BY install_date, platform, mediasource, campaign_name
    ),

    previous_day_performance AS (
      SELECT 
        install_date,
        platform,
        mediasource,
        campaign_name,
        SUM(cost) AS total_spend,
        SUM(installs) AS total_installs,
        SAFE_DIVIDE(SUM(cost), SUM(installs)) AS cpi,
        SUM(d0_total_net_revenue) AS d0_revenue,
        SUM(d1_total_net_revenue) AS d1_revenue,
        SUM(d7_total_net_revenue) AS d7_revenue,
        SAFE_DIVIDE(SUM(d0_total_net_revenue), SUM(cost)) AS d0_roas,
        SAFE_DIVIDE(SUM(d7_total_net_revenue), SUM(cost)) AS d7_roas
      FROM `yotam-395120.peerplay.ua_cohort`
      WHERE install_date = '2026-02-07'
        AND country = 'US'
        AND cost > 0
        AND installs > 0
        AND is_test_campaign = FALSE
      GROUP BY install_date, platform, mediasource, campaign_name
    ),

    -- Daily Summary Comparison
    daily_summary AS (
      SELECT
        '2026-02-08' AS analysis_date,
        'Yesterday' AS period_label,
        SUM(total_spend) AS daily_spend,
        SUM(total_installs) AS daily_installs,
        SAFE_DIVIDE(SUM(total_spend), SUM(total_installs)) AS overall_cpi,
        SUM(d0_revenue) AS d0_revenue,
        SUM(d7_revenue) AS d7_revenue,
        SAFE_DIVIDE(SUM(d0_revenue), SUM(total_spend)) AS d0_roas,
        SAFE_DIVIDE(SUM(d7_revenue), SUM(total_spend)) AS d7_roas
      FROM yesterday_performance
      
      UNION ALL
      
      SELECT
        '2026-02-07' AS analysis_date,
        'Previous Day' AS period_label,
        SUM(total_spend) AS daily_spend,
        SUM(total_installs) AS daily_installs,
        SAFE_DIVIDE(SUM(total_spend), SUM(total_installs)) AS overall_cpi,
        SUM(d0_revenue) AS d0_revenue,
        SUM(d7_revenue) AS d7_revenue,
        SAFE_DIVIDE(SUM(d0_revenue), SUM(total_spend)) AS d0_roas,
        SAFE_DIVIDE(SUM(d7_revenue), SUM(total_spend)) AS d7_roas
      FROM previous_day_performance
    ),

    -- Platform Breakdown
    platform_breakdown AS (
      SELECT
        platform,
        SUM(total_spend) AS platform_spend,
        SUM(total_installs) AS platform_installs,
        SAFE_DIVIDE(SUM(total_spend), SUM(total_installs)) AS platform_cpi,
        SUM(d0_revenue) AS platform_d0_revenue,
        SUM(d7_revenue) AS platform_d7_revenue,
        SAFE_DIVIDE(SUM(d0_revenue), SUM(total_spend)) AS platform_d0_roas,
        SAFE_DIVIDE(SUM(d7_revenue), SUM(total_spend)) AS platform_d7_roas,
        ROUND(SAFE_DIVIDE(SUM(total_spend), (SELECT SUM(total_spend) FROM yesterday_performance)) * 100, 1) AS spend_share_pct
      FROM yesterday_performance
      GROUP BY platform
      ORDER BY platform_spend DESC
    ),

    -- Source Performance with Day-over-Day Changes
    source_performance AS (
      SELECT
        y.mediasource,
        y.total_spend AS yesterday_spend,
        y.total_installs AS yesterday_installs,
        y.cpi AS yesterday_cpi,
        y.d0_roas AS yesterday_d0_roas,
        y.d7_roas AS yesterday_d7_roas,
        COALESCE(p.total_spend, 0) AS previous_spend,
        COALESCE(p.total_installs, 0) AS previous_installs,
        COALESCE(p.cpi, 0) AS previous_cpi,
        COALESCE(p.d0_roas, 0) AS previous_d0_roas,
        SAFE_DIVIDE(y.total_spend - COALESCE(p.total_spend, 0), COALESCE(p.total_spend, 1)) * 100 AS spend_change_pct,
        SAFE_DIVIDE(y.total_installs - COALESCE(p.total_installs, 0), COALESCE(p.total_installs, 1)) * 100 AS installs_change_pct,
        SAFE_DIVIDE(y.cpi - COALESCE(p.cpi, 0), COALESCE(p.cpi, 1)) * 100 AS cpi_change_pct,
        SAFE_DIVIDE(y.d0_roas - COALESCE(p.d0_roas, 0), COALESCE(p.d0_roas, 1)) * 100 AS roas_change_pct
      FROM (
        SELECT 
          mediasource, 
          SUM(total_spend) AS total_spend, 
          SUM(total_installs) AS total_installs,
          SAFE_DIVIDE(SUM(total_spend), SUM(total_installs)) AS cpi,
          SAFE_DIVIDE(SUM(d0_revenue), SUM(total_spend)) AS d0_roas,
          SAFE_DIVIDE(SUM(d7_revenue), SUM(total_spend)) AS d7_roas
        FROM yesterday_performance 
        GROUP BY mediasource
      ) y
      LEFT JOIN (
        SELECT 
          mediasource, 
          SUM(total_spend) AS total_spend, 
          SUM(total_installs) AS total_installs,
          SAFE_DIVIDE(SUM(total_spend), SUM(total_installs)) AS cpi,
          SAFE_DIVIDE(SUM(d0_revenue), SUM(total_spend)) AS d0_roas,
          SAFE_DIVIDE(SUM(d7_revenue), SUM(total_spend)) AS d7_roas
        FROM previous_day_performance 
        GROUP BY mediasource
      ) p ON y.mediasource = p.mediasource
      ORDER BY y.total_spend DESC
    ),

    -- Performance Alerts
    performance_alerts AS (
      SELECT
        mediasource,
        yesterday_spend,
        yesterday_cpi,
        yesterday_d0_roas,
        cpi_change_pct,
        installs_change_pct,
        roas_change_pct,
        CASE 
          WHEN cpi_change_pct > 20 AND yesterday_spend > 1000 THEN 'CRITICAL: CPI Spike >20%'
          WHEN installs_change_pct < -30 AND yesterday_spend > 1000 THEN 'CRITICAL: Volume Drop >30%'
          WHEN yesterday_spend > 5000 AND yesterday_cpi > 8.0 THEN 'WARNING: High CPI on High Spend'
          WHEN yesterday_d0_roas < 0.15 AND yesterday_spend > 2000 THEN 'WARNING: Low D0 ROAS'
          WHEN roas_change_pct < -25 AND yesterday_spend > 1000 THEN 'WARNING: ROAS Decline >25%'
          ELSE 'MONITOR'
        END AS alert_level,
        CASE 
          WHEN cpi_change_pct > 20 AND yesterday_spend > 1000 THEN 'Reduce spend or investigate targeting'
          WHEN installs_change_pct < -30 AND yesterday_spend > 1000 THEN 'Check campaign status and bid adjustments'
          WHEN yesterday_spend > 5000 AND yesterday_cpi > 8.0 THEN 'Consider pausing or reducing budget'
          WHEN yesterday_d0_roas < 0.15 AND yesterday_spend > 2000 THEN 'Immediate optimization needed'
          WHEN roas_change_pct < -25 AND yesterday_spend > 1000 THEN 'Review creative and targeting'
          ELSE 'Continue monitoring'
        END AS recommended_action
      FROM source_performance
      WHERE (
        (cpi_change_pct > 20 AND yesterday_spend > 1000) OR 
        (installs_change_pct < -30 AND yesterday_spend > 1000) OR 
        (yesterday_spend > 5000 AND yesterday_cpi > 8.0) OR 
        (yesterday_d0_roas < 0.15 AND yesterday_spend > 2000) OR
        (roas_change_pct < -25 AND yesterday_spend > 1000)
      )
    ),

    -- Top Campaigns Analysis
    top_campaigns AS (
      SELECT
        mediasource,
        campaign_name,
        platform,
        SUM(total_spend) AS campaign_spend,
        SUM(total_installs) AS campaign_installs,
        SAFE_DIVIDE(SUM(total_spend), SUM(total_installs)) AS campaign_cpi,
        SAFE_DIVIDE(SUM(d0_revenue), SUM(total_spend)) AS campaign_d0_roas,
        SAFE_DIVIDE(SUM(d7_revenue), SUM(total_spend)) AS campaign_d7_roas,
        RANK() OVER (ORDER BY SUM(total_spend) DESC) AS spend_rank,
        RANK() OVER (ORDER BY SAFE_DIVIDE(SUM(d0_revenue), SUM(total_spend)) DESC) AS roas_rank
      FROM yesterday_performance
      GROUP BY mediasource, campaign_name, platform
      HAVING SUM(total_spend) > 500
      ORDER BY campaign_spend DESC
    )

    -- Output all sections
    SELECT 'DAILY_SUMMARY' AS section, 
           analysis_date, period_label, 
           ROUND(daily_spend, 2) AS daily_spend, 
           daily_installs, 
           ROUND(overall_cpi, 2) AS overall_cpi, 
           ROUND(d0_revenue, 2) AS d0_revenue,
           ROUND(d7_revenue, 2) AS d7_revenue, 
           ROUND(d0_roas, 3) AS d0_roas,
           ROUND(d7_roas, 3) AS d7_roas,
           NULL AS platform, NULL AS mediasource, NULL AS campaign_name, NULL AS alert_info
    FROM daily_summary

    UNION ALL

    SELECT 'PLATFORM_BREAKDOWN' AS section,
           '2026-02-08' AS analysis_date, 
           platform AS period_label,
           ROUND(platform_spend, 2) AS daily_spend, 
           platform_installs AS daily_installs, 
           ROUND(platform_cpi, 2) AS overall_cpi, 
           ROUND(platform_d0_revenue, 2) AS d0_revenue,
           ROUND(platform_d7_revenue, 2) AS d7_revenue, 
           ROUND(platform_d0_roas, 3) AS d0_roas,
           ROUND(platform_d7_roas, 3) AS d7_roas,
           platform, NULL AS mediasource, NULL AS campaign_name, 
           CONCAT(spend_share_pct, '% of total spend') AS alert_info
    FROM platform_breakdown

    UNION ALL

    SELECT 'SOURCE_PERFORMANCE' AS section,
           '2026-02-08' AS analysis_date, 
           'Top Sources' AS period_label,
           ROUND(yesterday_spend, 2) AS daily_spend, 
           yesterday_installs AS daily_installs,
           ROUND(yesterday_cpi, 2) AS overall_cpi, 
           NULL AS d0_revenue,
           NULL AS d7_revenue, 
           ROUND(yesterday_d0_roas, 3) AS d0_roas,
           ROUND(yesterday_d7_roas, 3) AS d7_roas,
           NULL AS platform, 
           mediasource, 
           NULL AS campaign_name,
           CONCAT('Spend: ', ROUND(spend_change_pct, 1), '% | CPI: ', ROUND(cpi_change_pct, 1), '% | D0 ROAS: ', ROUND(roas_change_pct, 1), '%') AS alert_info
    FROM source_performance
    WHERE yesterday_spend > 50

    UNION ALL

    SELECT 'PERFORMANCE_ALERTS' AS section,
           '2026-02-08' AS analysis_date, 
           alert_level AS period_label,
           ROUND(yesterday_spend, 2) AS daily_spend, 
           NULL AS daily_installs, 
           ROUND(yesterday_cpi, 2) AS overall_cpi,
           NULL AS d0_revenue,
           NULL AS d7_revenue, 
           ROUND(yesterday_d0_roas, 3) AS d0_roas,
           NULL AS d7_roas,
           NULL AS platform, 
           mediasource, 
           NULL AS campaign_name,
           recommended_action AS alert_info
    FROM performance_alerts

    UNION ALL

    SELECT 'TOP_CAMPAIGNS' AS section,
           '2026-02-08' AS analysis_date,
           CONCAT('Rank #', spend_rank) AS period_label,
           ROUND(campaign_spend, 2) AS daily_spend,
           campaign_installs AS daily_installs,
           ROUND(campaign_cpi, 2) AS overall_cpi,
           NULL AS d0_revenue,
           NULL AS d7_revenue,
           ROUND(campaign_d0_roas, 3) AS d0_roas,
           ROUND(campaign_d7_roas, 3) AS d7_roas,
           platform,
           mediasource,
           campaign_name,
           CONCAT('D0 ROAS Rank: #', roas_rank) AS alert_info
    FROM top_campaigns
    WHERE spend_rank <= 15

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
    
    print("🚀 EXECUTING COMPREHENSIVE MARKETING ANALYSIS")
    print("=" * 80)
    print("📅 Analysis Date: February 8, 2026 (Yesterday)")
    print("💰 Using actual spend data from ua_cohort table")
    print("🇺🇸 Focus: US market, non-test campaigns only")
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
            print("❌ No data found for February 8, 2026. Checking alternative dates...")
            
            # Check what dates are available
            date_check_query = """
            SELECT install_date, 
                   COUNT(*) as records,
                   SUM(cost) as total_cost,
                   SUM(installs) as total_installs
            FROM `yotam-395120.peerplay.ua_cohort`
            WHERE install_date >= '2026-02-01' 
              AND country = 'US'
              AND cost > 0
            GROUP BY install_date
            ORDER BY install_date DESC
            LIMIT 10
            """
            
            date_job = client.query(date_check_query)
            date_results = date_job.result()
            date_df = date_results.to_dataframe()
            
            print("\n📊 Available dates with US spend data:")
            print(date_df.to_string(index=False))
            return None
            
        # Process and display results by section
        sections = df['section'].unique()
        
        analysis_summary = {
            'analysis_date': '2026-02-08',
            'total_sections': len(sections),
            'data_quality': {
                'total_records': len(df),
                'sections_found': list(sections)
            },
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
        print(f"\n{'='*25} ACTION ITEMS & RECOMMENDATIONS {'='*25}")
        generate_action_items(df, analysis_summary)
        
        # Save detailed results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save to CSV
        csv_filename = f"yesterday_marketing_analysis_{timestamp}.csv"
        df.to_csv(csv_filename, index=False)
        
        # Save summary to JSON
        json_filename = f"yesterday_marketing_summary_{timestamp}.json"
        with open(json_filename, 'w') as f:
            json.dump(analysis_summary, f, indent=2, default=str)
            
        print(f"\n🎯 ANALYSIS COMPLETE!")
        print("=" * 50)
        print(f"📁 Detailed results: {csv_filename}")
        print(f"📄 Executive summary: {json_filename}")
        print(f"📊 Total data points analyzed: {len(df)}")
        
        return analysis_summary
        
    except Exception as e:
        print(f"❌ Error executing analysis: {str(e)}")
        return None

def display_daily_summary(df):
    """Display daily summary comparison"""
    print("\n📈 DAILY PERFORMANCE OVERVIEW")
    print("-" * 80)
    print("Period        | Spend         | Installs | CPI     | D0 Revenue   | D0 ROAS | D7 ROAS")
    print("-" * 80)
    
    for _, row in df.iterrows():
        period = row['period_label'][:12]
        spend = f"${row['daily_spend']:,.0f}" if pd.notna(row['daily_spend']) else "N/A"
        installs = f"{int(row['daily_installs']):,}" if pd.notna(row['daily_installs']) else "N/A"
        cpi = f"${row['overall_cpi']:.2f}" if pd.notna(row['overall_cpi']) else "N/A"
        d0_revenue = f"${row['d0_revenue']:,.0f}" if pd.notna(row['d0_revenue']) else "N/A"
        d0_roas = f"{row['d0_roas']:.3f}" if pd.notna(row['d0_roas']) else "N/A"
        d7_roas = f"{row['d7_roas']:.3f}" if pd.notna(row['d7_roas']) else "N/A"
        
        print(f"{period:12} | {spend:>13} | {installs:>8} | {cpi:>7} | {d0_revenue:>12} | {d0_roas:>7} | {d7_roas:>7}")
    
    # Calculate day-over-day changes
    if len(df) >= 2:
        yesterday = df[df['period_label'] == 'Yesterday'].iloc[0] if not df[df['period_label'] == 'Yesterday'].empty else None
        previous = df[df['period_label'] == 'Previous Day'].iloc[0] if not df[df['period_label'] == 'Previous Day'].empty else None
        
        if yesterday is not None and previous is not None:
            if pd.notna(yesterday['daily_spend']) and pd.notna(previous['daily_spend']) and previous['daily_spend'] > 0:
                spend_change = ((yesterday['daily_spend'] - previous['daily_spend']) / previous['daily_spend']) * 100
                installs_change = ((yesterday['daily_installs'] - previous['daily_installs']) / previous['daily_installs']) * 100 if previous['daily_installs'] > 0 else 0
                cpi_change = ((yesterday['overall_cpi'] - previous['overall_cpi']) / previous['overall_cpi']) * 100 if previous['overall_cpi'] > 0 else 0
                
                print("\n📊 Day-over-Day Changes:")
                print(f"   💰 Spend: {spend_change:+.1f}% | 📱 Installs: {installs_change:+.1f}% | 💵 CPI: {cpi_change:+.1f}%")
                
                # Alert if significant changes
                if abs(spend_change) > 15:
                    print(f"   🚨 ALERT: Spend changed by {spend_change:+.1f}% - investigate immediately")
                if cpi_change > 20:
                    print(f"   ⚠️  WARNING: CPI increased by {cpi_change:+.1f}% - review targeting")

def display_platform_breakdown(df):
    """Display platform performance breakdown"""
    print("\n📱 PLATFORM PERFORMANCE")
    print("-" * 90)
    print("Platform    | Spend         | Installs | CPI     | D0 Revenue   | D0 ROAS | D7 ROAS | Share")
    print("-" * 90)
    
    for _, row in df.iterrows():
        platform = row['period_label'][:10]
        spend = f"${row['daily_spend']:,.0f}" if pd.notna(row['daily_spend']) else "N/A"
        installs = f"{int(row['daily_installs']):,}" if pd.notna(row['daily_installs']) else "N/A"
        cpi = f"${row['overall_cpi']:.2f}" if pd.notna(row['overall_cpi']) else "N/A"
        d0_revenue = f"${row['d0_revenue']:,.0f}" if pd.notna(row['d0_revenue']) else "N/A"
        d0_roas = f"{row['d0_roas']:.3f}" if pd.notna(row['d0_roas']) else "N/A"
        d7_roas = f"{row['d7_roas']:.3f}" if pd.notna(row['d7_roas']) else "N/A"
        share = row['alert_info'] if pd.notna(row['alert_info']) else "N/A"
        
        print(f"{platform:11} | {spend:>13} | {installs:>8} | {cpi:>7} | {d0_revenue:>12} | {d0_roas:>7} | {d7_roas:>7} | {share}")

def display_source_performance(df):
    """Display top source performance"""
    print("\n🎯 TOP MEDIA SOURCES PERFORMANCE")
    print("-" * 110)
    print("Media Source                 | Spend      | Installs | CPI     | D0 ROAS | D7 ROAS | Day-over-Day Changes")
    print("-" * 110)
    
    for _, row in df.iterrows():
        source = (row['mediasource'] or 'Unknown')[:28]
        spend = f"${row['daily_spend']:,.0f}" if pd.notna(row['daily_spend']) else "N/A"
        installs = f"{int(row['daily_installs']):,}" if pd.notna(row['daily_installs']) else "N/A"
        cpi = f"${row['overall_cpi']:.2f}" if pd.notna(row['overall_cpi']) else "N/A"
        d0_roas = f"{row['d0_roas']:.3f}" if pd.notna(row['d0_roas']) else "N/A"
        d7_roas = f"{row['d7_roas']:.3f}" if pd.notna(row['d7_roas']) else "N/A"
        changes = (row['alert_info'] or 'N/A')[:30] if pd.notna(row['alert_info']) else "N/A"
        
        print(f"{source:28} | {spend:>10} | {installs:>8} | {cpi:>7} | {d0_roas:>7} | {d7_roas:>7} | {changes}")

def display_performance_alerts(df):
    """Display critical performance alerts"""
    print("\n🚨 CRITICAL PERFORMANCE ALERTS")
    print("-" * 100)
    
    if df.empty:
        print("✅ No critical alerts - all sources performing within normal ranges")
        return
    
    print("Alert Level              | Source                | Spend    | CPI     | D0 ROAS | Recommended Action")
    print("-" * 100)
    
    for _, row in df.iterrows():
        alert_level = (row['period_label'] or 'Unknown')[:24]
        source = (row['mediasource'] or 'Unknown')[:20]
        spend = f"${row['daily_spend']:,.0f}" if pd.notna(row['daily_spend']) else "N/A"
        cpi = f"${row['overall_cpi']:.2f}" if pd.notna(row['overall_cpi']) else "N/A"
        d0_roas = f"{row['d0_roas']:.3f}" if pd.notna(row['d0_roas']) else "N/A"
        
        print(f"{alert_level:24} | {source:20} | {spend:>8} | {cpi:>7} | {d0_roas:>7}")
        
        # Show recommended action
        if pd.notna(row['alert_info']):
            print(f"   → {row['alert_info']}")
        print()

def display_top_campaigns(df):
    """Display top campaign performance"""
    print("\n🏆 TOP CAMPAIGNS BY SPEND")
    print("-" * 120)
    print("Rank | Media Source          | Campaign                         | Platform | Spend    | CPI     | D0 ROAS | D7 ROAS")
    print("-" * 120)
    
    for _, row in df.iterrows():
        rank = (row['period_label'] or 'Unknown')[6:]  # Remove "Rank #"
        source = (row['mediasource'] or 'Unknown')[:20]
        campaign = (row['campaign_name'] or 'Unknown')[:30]
        platform = (row['platform'] or 'Unknown')[:8]
        spend = f"${row['daily_spend']:,.0f}" if pd.notna(row['daily_spend']) else "N/A"
        cpi = f"${row['overall_cpi']:.2f}" if pd.notna(row['overall_cpi']) else "N/A"
        d0_roas = f"{row['d0_roas']:.3f}" if pd.notna(row['d0_roas']) else "N/A"
        d7_roas = f"{row['d7_roas']:.3f}" if pd.notna(row['d7_roas']) else "N/A"
        
        print(f"{rank:4} | {source:20} | {campaign:30} | {platform:8} | {spend:>8} | {cpi:>7} | {d0_roas:>7} | {d7_roas:>7}")

def generate_action_items(df, analysis_summary):
    """Generate actionable recommendations"""
    
    # Get key metrics from daily summary
    daily_summary = df[df['section'] == 'DAILY_SUMMARY']
    yesterday_data = daily_summary[daily_summary['period_label'] == 'Yesterday']
    
    if not yesterday_data.empty:
        total_spend = yesterday_data.iloc[0]['daily_spend']
        total_installs = yesterday_data.iloc[0]['daily_installs']
        avg_cpi = yesterday_data.iloc[0]['overall_cpi']
        d0_roas = yesterday_data.iloc[0]['d0_roas']
        
        print(f"\n💡 KEY INSIGHTS:")
        print(f"   📊 Total spend: ${total_spend:,.0f} | Average CPI: ${avg_cpi:.2f} | D0 ROAS: {d0_roas:.3f}")
        
        # Performance assessment
        if d0_roas < 0.15:
            print("   🔴 CONCERN: D0 ROAS below 0.15 - immediate optimization required")
        elif d0_roas < 0.25:
            print("   🟡 WARNING: D0 ROAS below target - review top sources")
        else:
            print("   ✅ GOOD: D0 ROAS above 0.25 - healthy performance")
            
        if avg_cpi > 7.0:
            print("   🔴 CONCERN: Average CPI above $7.00 - cost optimization needed")
        elif avg_cpi > 5.0:
            print("   🟡 WARNING: Average CPI elevated - monitor closely")
    
    # Analyze alerts
    alerts_df = df[df['section'] == 'PERFORMANCE_ALERTS']
    
    print(f"\n🎯 IMMEDIATE ACTION ITEMS FOR TODAY:")
    print("-" * 60)
    
    if not alerts_df.empty:
        critical_alerts = alerts_df[alerts_df['period_label'].str.contains('CRITICAL', na=False)]
        warning_alerts = alerts_df[alerts_df['period_label'].str.contains('WARNING', na=False)]
        
        if not critical_alerts.empty:
            print("🔴 CRITICAL ACTIONS (Do Immediately):")
            for i, alert in critical_alerts.iterrows():
                print(f"   {i+1}. {alert['mediasource']}: {alert['alert_info']}")
                print(f"      💰 Current spend: ${alert['daily_spend']:,.0f} | CPI: ${alert['overall_cpi']:.2f}")
            print()
            
        if not warning_alerts.empty:
            print("🟡 WARNING ACTIONS (Address Today):")
            for i, alert in warning_alerts.iterrows():
                print(f"   {i+1}. {alert['mediasource']}: {alert['alert_info']}")
                print(f"      💰 Current spend: ${alert['daily_spend']:,.0f} | CPI: ${alert['overall_cpi']:.2f}")
            print()
    else:
        print("✅ No critical alerts - all major sources performing normally")
    
    # Budget optimization opportunities
    source_df = df[df['section'] == 'SOURCE_PERFORMANCE']
    
    if not source_df.empty:
        # Find scaling opportunities (good ROAS, reasonable spend)
        good_performers = source_df[
            (pd.to_numeric(source_df['d0_roas'], errors='coerce') > 0.25) &
            (pd.to_numeric(source_df['daily_spend'], errors='coerce') > 1000) &
            (pd.to_numeric(source_df['overall_cpi'], errors='coerce') < 6.0)
        ]
        
        if not good_performers.empty:
            print("📈 SCALING OPPORTUNITIES:")
            for _, source in good_performers.head(3).iterrows():
                spend = source['daily_spend']
                cpi = source['overall_cpi']
                roas = source['d0_roas']
                print(f"   • {source['mediasource']}: ${spend:,.0f} spend, ${cpi:.2f} CPI, {roas:.3f} D0 ROAS")
            print()
        
        # Find optimization needs (poor performance, high spend)
        poor_performers = source_df[
            (pd.to_numeric(source_df['daily_spend'], errors='coerce') > 2000) &
            (
                (pd.to_numeric(source_df['overall_cpi'], errors='coerce') > 7.0) |
                (pd.to_numeric(source_df['d0_roas'], errors='coerce') < 0.2)
            )
        ]
        
        if not poor_performers.empty:
            print("🔧 OPTIMIZATION PRIORITIES:")
            for _, source in poor_performers.head(3).iterrows():
                spend = source['daily_spend']
                cpi = source['overall_cpi']
                roas = source['d0_roas']
                print(f"   • {source['mediasource']}: ${spend:,.0f} spend, ${cpi:.2f} CPI, {roas:.3f} D0 ROAS")
            print()
    
    print("📋 TODAY'S MONITORING CHECKLIST:")
    print("   ☐ Review and act on all CRITICAL alerts immediately")
    print("   ☐ Check campaign delivery for sources with volume drops")
    print("   ☐ Monitor CPI trends throughout the day")
    print("   ☐ Verify creative rotation is working properly")
    print("   ☐ Update bid adjustments based on morning performance")
    print("   ☐ Scale budget for top-performing sources")
    print("   ☐ Set up alerts for any new anomalies")
    
    # Add to analysis summary
    analysis_summary['action_items'] = {
        'critical_alerts': len(alerts_df[alerts_df['period_label'].str.contains('CRITICAL', na=False)]),
        'warning_alerts': len(alerts_df[alerts_df['period_label'].str.contains('WARNING', na=False)]),
        'scaling_opportunities': len(good_performers) if 'good_performers' in locals() else 0,
        'optimization_priorities': len(poor_performers) if 'poor_performers' in locals() else 0
    }

if __name__ == "__main__":
    execute_marketing_analysis()