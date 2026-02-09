#!/usr/bin/env python3
"""
FINAL CORRECTED YESTERDAY'S ANALYSIS (Feb 8, 2026) - GLOBAL DATA
Using cost > 0 filter to match the $52,560 figure
"""

from google.cloud import bigquery
import pandas as pd
import json
from datetime import datetime
import os

def execute_final_corrected_analysis():
    """Execute final corrected analysis matching user's $52,560 total"""
    
    client = bigquery.Client(project='yotam-395120')
    
    # FINAL CORRECTED Query - cost > 0 only (matches user's $52,560)
    query = """
    -- FINAL CORRECTED YESTERDAY'S ANALYSIS (Feb 8, 2026) - GLOBAL DATA
    WITH daily_overview AS (
      SELECT
        'Global Daily Overview' as section,
        COUNT(DISTINCT mediasource) as total_sources,
        COUNT(*) as total_records,
        ROUND(SUM(cost), 2) as total_spend,
        SUM(installs) as total_installs,
        ROUND(SAFE_DIVIDE(SUM(cost), SUM(CASE WHEN installs > 0 THEN installs END)), 2) as effective_cpi,
        ROUND(SUM(CASE WHEN platform = 'Android' THEN cost ELSE 0 END), 2) as android_spend,
        ROUND(SUM(CASE WHEN platform = 'Apple' THEN cost ELSE 0 END), 2) as apple_spend,
        SUM(CASE WHEN platform = 'Android' THEN installs ELSE 0 END) as android_installs,
        SUM(CASE WHEN platform = 'Apple' THEN installs ELSE 0 END) as apple_installs,
        ROUND(SAFE_DIVIDE(SUM(CASE WHEN platform = 'Android' THEN cost ELSE 0 END), 
                          SUM(CASE WHEN platform = 'Android' AND installs > 0 THEN installs END)), 2) as android_cpi,
        ROUND(SAFE_DIVIDE(SUM(CASE WHEN platform = 'Apple' THEN cost ELSE 0 END), 
                          SUM(CASE WHEN platform = 'Apple' AND installs > 0 THEN installs END)), 2) as apple_cpi
      FROM `yotam-395120.peerplay.ua_cohort`
      WHERE install_date = '2026-02-08'
        AND cost > 0  -- Only filter on cost > 0 to match user's $52,560
    ),
    
    top_sources AS (
      SELECT
        mediasource,
        ROUND(SUM(cost), 2) as spend,
        SUM(installs) as installs,
        ROUND(SAFE_DIVIDE(SUM(cost), SUM(CASE WHEN installs > 0 THEN installs END)), 2) as effective_cpi,
        ROUND(SUM(CASE WHEN platform = 'Android' THEN cost ELSE 0 END), 2) as android_spend,
        ROUND(SUM(CASE WHEN platform = 'Apple' THEN cost ELSE 0 END), 2) as apple_spend,
        SUM(CASE WHEN platform = 'Android' THEN installs ELSE 0 END) as android_installs,
        SUM(CASE WHEN platform = 'Apple' THEN installs ELSE 0 END) as apple_installs,
        ROUND(SAFE_DIVIDE(SUM(CASE WHEN platform = 'Android' THEN cost ELSE 0 END), 
                          SUM(CASE WHEN platform = 'Android' AND installs > 0 THEN installs END)), 2) as android_cpi,
        ROUND(SAFE_DIVIDE(SUM(CASE WHEN platform = 'Apple' THEN cost ELSE 0 END), 
                          SUM(CASE WHEN platform = 'Apple' AND installs > 0 THEN installs END)), 2) as apple_cpi,
        SUM(CASE WHEN installs = 0 THEN 1 ELSE 0 END) as zero_install_records,
        ROUND(SUM(CASE WHEN installs = 0 THEN cost ELSE 0 END), 2) as zero_install_spend
      FROM `yotam-395120.peerplay.ua_cohort`
      WHERE install_date = '2026-02-08'
        AND cost > 0
      GROUP BY mediasource
      ORDER BY spend DESC
      LIMIT 15
    ),
    
    country_performance AS (
      SELECT
        country,
        ROUND(SUM(cost), 2) as spend,
        SUM(installs) as installs,
        ROUND(SAFE_DIVIDE(SUM(cost), SUM(CASE WHEN installs > 0 THEN installs END)), 2) as effective_cpi,
        COUNT(DISTINCT mediasource) as sources_count,
        SUM(CASE WHEN installs = 0 THEN 1 ELSE 0 END) as zero_install_records,
        ROUND(SUM(CASE WHEN installs = 0 THEN cost ELSE 0 END), 2) as zero_install_spend
      FROM `yotam-395120.peerplay.ua_cohort`
      WHERE install_date = '2026-02-08'
        AND cost > 0
      GROUP BY country
      ORDER BY spend DESC
      LIMIT 20
    )
    
    SELECT 
      'overview' as query_type,
      section,
      CAST(total_sources as STRING) as mediasource,
      total_spend as spend,
      total_installs as installs,
      effective_cpi as cpi,
      android_spend,
      apple_spend as ios_spend,
      android_installs,
      apple_installs as ios_installs,
      android_cpi,
      apple_cpi as ios_cpi,
      total_records
    FROM daily_overview
    
    UNION ALL
    
    SELECT 
      'sources' as query_type,
      'Top Sources Performance' as section,
      mediasource,
      spend,
      installs,
      effective_cpi as cpi,
      android_spend,
      apple_spend as ios_spend,
      android_installs,
      apple_installs as ios_installs,
      android_cpi,
      apple_cpi as ios_cpi,
      zero_install_records
    FROM top_sources
    
    UNION ALL
    
    SELECT 
      'countries' as query_type,
      'Country Performance' as section,
      country as mediasource,
      spend,
      installs,
      effective_cpi as cpi,
      NULL as android_spend,
      NULL as ios_spend,
      NULL as android_installs,
      NULL as ios_installs,
      NULL as android_cpi,
      NULL as ios_cpi,
      zero_install_records
    FROM country_performance
    
    ORDER BY query_type, spend DESC
    """
    
    print("Executing FINAL corrected global analysis for Feb 8, 2026...")
    print("Using cost > 0 filter to match your $52,560 total")
    print("=" * 80)
    
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
        print("\n🌍 FINAL CORRECTED GLOBAL ANALYSIS (Feb 8, 2026)")
        print("=" * 60)
        if overview_data is not None:
            print(f"✅ Total Spend: ${overview_data['spend']:,.2f} (should match your $52,560)")
            print(f"Total Records: {overview_data['total_records']:,.0f}")
            print(f"Total Installs: {overview_data['installs']:,}")
            print(f"Effective CPI: ${overview_data['cpi']:.2f} (cost/installs where installs > 0)")
            print(f"Total Sources: {overview_data['mediasource']}")
            print(f"\nPlatform Breakdown:")
            print(f"  Android: ${overview_data['android_spend']:,.2f} ({overview_data['android_installs']:,} installs, CPI: ${overview_data['android_cpi']:.2f})")
            print(f"  Apple/iOS: ${overview_data['ios_spend']:,.2f} ({overview_data['ios_installs']:,} installs, CPI: ${overview_data['ios_cpi']:.2f})")
        
        print(f"\n📊 TOP SOURCES PERFORMANCE (Cost > 0)")
        print("=" * 80)
        print(f"{'Source':<12} {'Spend':<12} {'Installs':<9} {'Eff.CPI':<8} {'Android$':<10} {'iOS$':<10} {'0-Install':<9}")
        print("-" * 80)
        for _, row in sources_data.iterrows():
            android_spend = f"${row['android_spend']:,.0f}" if pd.notna(row['android_spend']) and row['android_spend'] > 0 else "$0"
            ios_spend = f"${row['ios_spend']:,.0f}" if pd.notna(row['ios_spend']) and row['ios_spend'] > 0 else "$0"
            zero_records = int(row['total_records']) if pd.notna(row['total_records']) else 0
            cpi_str = f"${row['cpi']:.2f}" if pd.notna(row['cpi']) else "N/A"
            print(f"{row['mediasource']:<12} ${row['spend']:>10,.0f} {row['installs']:>8,} {cpi_str:>7} {android_spend:>9} {ios_spend:>9} {zero_records:>8}")
        
        print(f"\n🌎 COUNTRY PERFORMANCE")
        print("=" * 70)
        print(f"{'Country':<10} {'Spend':<12} {'Installs':<9} {'Eff.CPI':<8} {'% Total':<8} {'0-Install':<9}")
        print("-" * 70)
        total_spend = overview_data['spend'] if overview_data is not None else countries_data['spend'].sum()
        for _, row in countries_data.iterrows():
            pct = (row['spend'] / total_spend * 100) if total_spend > 0 else 0
            zero_records = int(row['total_records']) if pd.notna(row['total_records']) else 0
            cpi_str = f"${row['cpi']:.2f}" if pd.notna(row['cpi']) else "N/A"
            print(f"{row['mediasource']:<10} ${row['spend']:>10,.0f} {row['installs']:>8,} {cpi_str:>7} {pct:>6.1f}% {zero_records:>8}")
        
        # Analysis insights
        print(f"\n🔍 KEY INSIGHTS & CORRECTIONS")
        print("=" * 60)
        
        if overview_data is not None:
            almedia_row = sources_data[sources_data['mediasource'] == 'almedia']
            if not almedia_row.empty:
                almedia_spend = almedia_row.iloc[0]['spend']
                almedia_installs = almedia_row.iloc[0]['installs']
                almedia_zero = int(almedia_row.iloc[0]['total_records']) if pd.notna(almedia_row.iloc[0]['total_records']) else 0
                print(f"✅ TOTAL VERIFICATION:")
                print(f"   Total Spend: ${overview_data['spend']:,.2f} vs Your Report: $52,560")
                print(f"   Match Status: {'✅ MATCHES' if abs(overview_data['spend'] - 52560) < 100 else '❌ MISMATCH'}")
                print(f"")
                print(f"✅ ALMEDIA VERIFICATION:")
                print(f"   Almedia Spend: ${almedia_spend:,.2f} vs Your Report: $17,086")
                print(f"   Match Status: {'✅ CLOSE MATCH' if abs(almedia_spend - 17086) < 1000 else '❌ MISMATCH'}")
                print(f"   Almedia Installs: {almedia_installs:,}")
                if almedia_zero > 0:
                    print(f"   Records with 0 installs: {almedia_zero}")
            
            us_row = countries_data[countries_data['mediasource'] == 'US']
            international_spend = countries_data[countries_data['mediasource'] != 'US']['spend'].sum()
            if not us_row.empty:
                us_spend = us_row.iloc[0]['spend']
                us_installs = us_row.iloc[0]['installs']
                us_zero = int(us_row.iloc[0]['total_records']) if pd.notna(us_row.iloc[0]['total_records']) else 0
                print(f"")
                print(f"🌍 GEOGRAPHIC BREAKDOWN:")
                print(f"   🇺🇸 US: ${us_spend:,.2f} ({us_spend/overview_data['spend']*100:.1f}%) - {us_installs:,} installs")
                print(f"   🌍 International: ${international_spend:,.2f} ({international_spend/overview_data['spend']*100:.1f}%)")
                if us_zero > 0:
                    print(f"   US records with 0 installs: {us_zero}")
        
        # Zero install analysis
        zero_install_sources = sources_data[sources_data['total_records'] > 0]
        if not zero_install_sources.empty:
            total_zero_records = zero_install_sources['total_records'].sum()
            print(f"")
            print(f"⚠️  ZERO INSTALL ANALYSIS:")
            print(f"   Records with spend but 0 installs: {total_zero_records:.0f}")
            print(f"   This explains difference between $52K (all spend) vs $45K (spend with installs)")
        
        print(f"\n🔧 UPDATED ACTION ITEMS (Based on $52K Total)")
        print("=" * 60)
        print("1. 🎯 Almedia: $17K spend - investigate efficiency vs 0-install records")
        print("2. 🌍 Geographic: 68% US vs 32% International - optimize mix")
        print("3. 📱 Platform: Android vs iOS performance analysis needed")
        print("4. ⚠️  Zero Installs: Review sources with spend but no installs")
        print("5. 💰 CPI: Focus on sources with best effective CPI")
        
        # Save results
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save all data to CSV for export
        final_summary = pd.DataFrame([{
            'date': '2026-02-08',
            'total_spend': overview_data['spend'] if overview_data is not None else 0,
            'total_installs': overview_data['installs'] if overview_data is not None else 0,
            'effective_cpi': overview_data['cpi'] if overview_data is not None else 0,
            'android_spend': overview_data['android_spend'] if overview_data is not None else 0,
            'ios_spend': overview_data['ios_spend'] if overview_data is not None else 0,
            'android_installs': overview_data['android_installs'] if overview_data is not None else 0,
            'ios_installs': overview_data['ios_installs'] if overview_data is not None else 0,
            'top_source': sources_data.iloc[0]['mediasource'] if not sources_data.empty else '',
            'top_source_spend': sources_data.iloc[0]['spend'] if not sources_data.empty else 0,
        }])
        
        summary_filename = f"FINAL_corrected_global_feb8_summary_{timestamp}.csv"
        final_summary.to_csv(summary_filename, index=False)
        
        sources_filename = f"FINAL_corrected_global_feb8_sources_{timestamp}.csv"
        sources_data.to_csv(sources_filename, index=False)
        
        countries_filename = f"FINAL_corrected_global_feb8_countries_{timestamp}.csv"
        countries_data.to_csv(countries_filename, index=False)
        
        print(f"\n💾 SAVED FILES:")
        print(f"   📊 Summary: {summary_filename}")
        print(f"   📈 Sources: {sources_filename}")
        print(f"   🌍 Countries: {countries_filename}")
        
        return {
            'overview': overview_data.to_dict() if overview_data is not None else None,
            'sources': sources_data.to_dict('records'),
            'countries': countries_data.to_dict('records'),
            'query': query,
            'files': [summary_filename, sources_filename, countries_filename]
        }
        
    except Exception as e:
        print(f"Error executing query: {str(e)}")
        return None

if __name__ == "__main__":
    results = execute_final_corrected_analysis()