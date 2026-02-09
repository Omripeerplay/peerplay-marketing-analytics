#!/usr/bin/env python3
"""
CORRECTED YESTERDAY'S ANALYSIS (Feb 8, 2026) - GLOBAL DATA
Removing US-only filter to match reported $52,560 total spend
"""

from google.cloud import bigquery
import pandas as pd
import json
from datetime import datetime
import os

def execute_corrected_global_analysis():
    """Execute corrected global analysis for Feb 8, 2026"""
    
    # Initialize BigQuery client
    client = bigquery.Client(project='yotam-395120')
    
    # Corrected Global Analysis Query - NO country filter
    query = """
    -- CORRECTED YESTERDAY'S ANALYSIS (Feb 8, 2026) - GLOBAL DATA
    WITH daily_overview AS (
      SELECT
        'Global Daily Overview' as section,
        COUNT(DISTINCT mediasource) as total_sources,
        ROUND(SUM(cost), 2) as total_spend,
        SUM(installs) as total_installs,
        ROUND(SAFE_DIVIDE(SUM(cost), SUM(installs)), 2) as avg_cpi,
        ROUND(SUM(CASE WHEN platform = 'Android' THEN cost ELSE 0 END), 2) as android_spend,
        ROUND(SUM(CASE WHEN platform = 'Apple' THEN cost ELSE 0 END), 2) as ios_spend,
        SUM(CASE WHEN platform = 'Android' THEN installs ELSE 0 END) as android_installs,
        SUM(CASE WHEN platform = 'Apple' THEN installs ELSE 0 END) as ios_installs,
        ROUND(SAFE_DIVIDE(SUM(CASE WHEN platform = 'Android' THEN cost ELSE 0 END), 
                          SUM(CASE WHEN platform = 'Android' THEN installs ELSE 0 END)), 2) as android_cpi,
        ROUND(SAFE_DIVIDE(SUM(CASE WHEN platform = 'Apple' THEN cost ELSE 0 END), 
                          SUM(CASE WHEN platform = 'Apple' THEN installs ELSE 0 END)), 2) as ios_cpi
      FROM `yotam-395120.peerplay.ua_cohort`
      WHERE install_date = '2026-02-08'
        AND cost > 0
        AND installs > 0
    ),
    
    top_sources AS (
      SELECT
        mediasource,
        ROUND(SUM(cost), 2) as spend,
        SUM(installs) as installs,
        ROUND(SAFE_DIVIDE(SUM(cost), SUM(installs)), 2) as cpi,
        ROUND(SUM(CASE WHEN platform = 'Android' THEN cost ELSE 0 END), 2) as android_spend,
        ROUND(SUM(CASE WHEN platform = 'Apple' THEN cost ELSE 0 END), 2) as ios_spend,
        SUM(CASE WHEN platform = 'Android' THEN installs ELSE 0 END) as android_installs,
        SUM(CASE WHEN platform = 'Apple' THEN installs ELSE 0 END) as ios_installs,
        ROUND(SAFE_DIVIDE(SUM(CASE WHEN platform = 'Android' THEN cost ELSE 0 END), 
                          SUM(CASE WHEN platform = 'Android' THEN installs ELSE 0 END)), 2) as android_cpi,
        ROUND(SAFE_DIVIDE(SUM(CASE WHEN platform = 'Apple' THEN cost ELSE 0 END), 
                          SUM(CASE WHEN platform = 'Apple' THEN installs ELSE 0 END)), 2) as ios_cpi
      FROM `yotam-395120.peerplay.ua_cohort`
      WHERE install_date = '2026-02-08'
        AND cost > 0
        AND installs > 0
      GROUP BY mediasource
      ORDER BY spend DESC
      LIMIT 10
    ),
    
    country_performance AS (
      SELECT
        country,
        ROUND(SUM(cost), 2) as spend,
        SUM(installs) as installs,
        ROUND(SAFE_DIVIDE(SUM(cost), SUM(installs)), 2) as cpi,
        COUNT(DISTINCT mediasource) as sources_count
      FROM `yotam-395120.peerplay.ua_cohort`
      WHERE install_date = '2026-02-08'
        AND cost > 0
        AND installs > 0
      GROUP BY country
      ORDER BY spend DESC
      LIMIT 15
    )
    
    SELECT 
      'overview' as query_type,
      section,
      CAST(total_sources as STRING) as mediasource,
      total_spend as spend,
      total_installs as installs,
      avg_cpi as cpi,
      android_spend,
      ios_spend,
      android_installs,
      ios_installs,
      android_cpi,
      ios_cpi
    FROM daily_overview
    
    UNION ALL
    
    SELECT 
      'sources' as query_type,
      'Top Sources Performance' as section,
      mediasource,
      spend,
      installs,
      cpi,
      android_spend,
      ios_spend,
      android_installs,
      ios_installs,
      android_cpi,
      ios_cpi
    FROM top_sources
    
    UNION ALL
    
    SELECT 
      'countries' as query_type,
      'Country Performance' as section,
      country as mediasource,
      spend,
      installs,
      cpi,
      NULL as android_spend,
      NULL as ios_spend,
      NULL as android_installs,
      NULL as ios_installs,
      NULL as android_cpi,
      NULL as ios_cpi
    FROM country_performance
    
    ORDER BY query_type, spend DESC
    """
    
    print("Executing corrected global analysis for Feb 8, 2026...")
    print("=" * 80)
    
    # Execute query
    try:
        query_job = client.query(query)
        results = query_job.result()
        df = results.to_dataframe()
        
        if df.empty:
            print("No data found for Feb 8, 2026")
            return
            
        # Process results by section
        overview_data = df[df['query_type'] == 'overview'].iloc[0] if not df[df['query_type'] == 'overview'].empty else None
        sources_data = df[df['query_type'] == 'sources']
        countries_data = df[df['query_type'] == 'countries']
        
        # Print results
        print("\n🌍 CORRECTED GLOBAL DAILY OVERVIEW (Feb 8, 2026)")
        print("=" * 60)
        if overview_data is not None:
            print(f"Total Spend: ${overview_data['spend']:,.2f}")
            print(f"Total Installs: {overview_data['installs']:,}")
            print(f"Average CPI: ${overview_data['cpi']:.2f}")
            print(f"Total Sources: {overview_data['mediasource']}")
            print(f"\nPlatform Breakdown:")
            print(f"  Android: ${overview_data['android_spend']:,.2f} ({overview_data['android_installs']:,} installs, CPI: ${overview_data['android_cpi']:.2f})")
            print(f"  iOS: ${overview_data['ios_spend']:,.2f} ({overview_data['ios_installs']:,} installs, CPI: ${overview_data['ios_cpi']:.2f})")
        
        print(f"\n📊 TOP SOURCES PERFORMANCE")
        print("=" * 60)
        print(f"{'Source':<15} {'Spend':<12} {'Installs':<9} {'CPI':<6} {'Android $':<11} {'iOS $':<11}")
        print("-" * 80)
        for _, row in sources_data.iterrows():
            android_spend = f"${row['android_spend']:,.0f}" if pd.notna(row['android_spend']) and row['android_spend'] > 0 else "$0"
            ios_spend = f"${row['ios_spend']:,.0f}" if pd.notna(row['ios_spend']) and row['ios_spend'] > 0 else "$0"
            print(f"{row['mediasource']:<15} ${row['spend']:>10,.0f} {row['installs']:>8,} ${row['cpi']:>5.2f} {android_spend:>10} {ios_spend:>10}")
        
        print(f"\n🌎 COUNTRY PERFORMANCE")
        print("=" * 60)
        print(f"{'Country':<12} {'Spend':<12} {'Installs':<9} {'CPI':<6} {'% of Total':<10}")
        print("-" * 60)
        total_spend = overview_data['spend'] if overview_data is not None else countries_data['spend'].sum()
        for _, row in countries_data.iterrows():
            pct = (row['spend'] / total_spend * 100) if total_spend > 0 else 0
            print(f"{row['mediasource']:<12} ${row['spend']:>10,.0f} {row['installs']:>8,} ${row['cpi']:>5.2f} {pct:>8.1f}%")
        
        # Summary insights
        print(f"\n📋 KEY CORRECTIONS & INSIGHTS")
        print("=" * 60)
        
        if overview_data is not None:
            almedia_row = sources_data[sources_data['mediasource'] == 'almedia']
            if not almedia_row.empty:
                almedia_spend = almedia_row.iloc[0]['spend']
                almedia_installs = almedia_row.iloc[0]['installs']
                print(f"✅ Total Spend: ${overview_data['spend']:,.2f} (should match your ${52560:,.0f})")
                print(f"✅ Almedia Spend: ${almedia_spend:,.2f} (should match your ${17086:,.0f})")
                print(f"✅ Almedia Installs: {almedia_installs:,} installs")
            
            us_row = countries_data[countries_data['mediasource'] == 'US']
            international_spend = countries_data[countries_data['mediasource'] != 'US']['spend'].sum()
            if not us_row.empty:
                us_spend = us_row.iloc[0]['spend']
                print(f"🇺🇸 US Spend: ${us_spend:,.2f} ({us_spend/overview_data['spend']*100:.1f}% of total)")
                print(f"🌍 International: ${international_spend:,.2f} ({international_spend/overview_data['spend']*100:.1f}% of total)")
        
        print(f"\n🔧 CORRECTED ACTION ITEMS")
        print("=" * 60)
        print("1. Almedia Performance: Review the $17K+ spend efficiency")
        print("2. Global vs US: Analyze international market opportunities")
        print("3. Platform Mix: Optimize Android vs iOS spend allocation")
        print("4. CPI Optimization: Focus on sources with best cost efficiency")
        
        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save overview
        overview_filename = f"corrected_global_feb8_overview_{timestamp}.csv"
        if overview_data is not None:
            pd.DataFrame([overview_data]).to_csv(overview_filename, index=False)
            print(f"\n💾 Overview saved: {overview_filename}")
        
        # Save sources
        sources_filename = f"corrected_global_feb8_sources_{timestamp}.csv"
        sources_data.to_csv(sources_filename, index=False)
        print(f"💾 Sources saved: {sources_filename}")
        
        # Save countries
        countries_filename = f"corrected_global_feb8_countries_{timestamp}.csv"
        countries_data.to_csv(countries_filename, index=False)
        print(f"💾 Countries saved: {countries_filename}")
        
        return {
            'overview': overview_data.to_dict() if overview_data is not None else None,
            'sources': sources_data.to_dict('records'),
            'countries': countries_data.to_dict('records'),
            'query': query
        }
        
    except Exception as e:
        print(f"Error executing query: {str(e)}")
        return None

if __name__ == "__main__":
    results = execute_corrected_global_analysis()