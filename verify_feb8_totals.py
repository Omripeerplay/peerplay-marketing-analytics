#!/usr/bin/env python3
"""
Verify Feb 8, 2026 totals to understand discrepancy
"""

from google.cloud import bigquery
import pandas as pd

def verify_feb8_totals():
    """Check exact totals for Feb 8, 2026"""
    
    client = bigquery.Client(project='yotam-395120')
    
    # Simple total query
    query = """
    SELECT
        COUNT(*) as row_count,
        COUNT(DISTINCT mediasource) as unique_sources,
        ROUND(SUM(cost), 2) as total_cost,
        SUM(installs) as total_installs,
        ROUND(MIN(cost), 2) as min_cost,
        ROUND(MAX(cost), 2) as max_cost,
        ROUND(AVG(cost), 2) as avg_cost,
        -- Platform breakdown
        ROUND(SUM(CASE WHEN platform = 'Android' THEN cost ELSE 0 END), 2) as android_cost,
        ROUND(SUM(CASE WHEN platform = 'Apple' THEN cost ELSE 0 END), 2) as apple_cost,
        SUM(CASE WHEN platform = 'Android' THEN installs ELSE 0 END) as android_installs,
        SUM(CASE WHEN platform = 'Apple' THEN installs ELSE 0 END) as apple_installs,
        -- Almedia specific
        ROUND(SUM(CASE WHEN mediasource = 'almedia' THEN cost ELSE 0 END), 2) as almedia_cost,
        SUM(CASE WHEN mediasource = 'almedia' THEN installs ELSE 0 END) as almedia_installs
    FROM `yotam-395120.peerplay.ua_cohort`
    WHERE install_date = '2026-02-08'
        AND cost > 0
        AND installs > 0
    """
    
    print("Verifying Feb 8, 2026 totals...")
    print("=" * 50)
    
    try:
        result = client.query(query).result()
        df = result.to_dataframe()
        
        if df.empty:
            print("No data found!")
            return
            
        row = df.iloc[0]
        
        print(f"Total Records: {row['row_count']:,}")
        print(f"Unique Sources: {row['unique_sources']}")
        print(f"")
        print(f"COSTS:")
        print(f"  Total Cost: ${row['total_cost']:,.2f}")
        print(f"  Android: ${row['android_cost']:,.2f}")
        print(f"  Apple: ${row['apple_cost']:,.2f}")
        print(f"  Min Cost: ${row['min_cost']:,.2f}")
        print(f"  Max Cost: ${row['max_cost']:,.2f}")
        print(f"  Avg Cost: ${row['avg_cost']:,.2f}")
        print(f"")
        print(f"INSTALLS:")
        print(f"  Total Installs: {row['total_installs']:,}")
        print(f"  Android: {row['android_installs']:,}")
        print(f"  Apple: {row['apple_installs']:,}")
        print(f"")
        print(f"ALMEDIA:")
        print(f"  Almedia Cost: ${row['almedia_cost']:,.2f}")
        print(f"  Almedia Installs: {row['almedia_installs']:,}")
        
        # Check if there are records with cost = 0 or installs = 0
        zero_check_query = """
        SELECT
            'All Records' as category,
            COUNT(*) as count,
            ROUND(SUM(cost), 2) as total_cost,
            SUM(installs) as total_installs
        FROM `yotam-395120.peerplay.ua_cohort`
        WHERE install_date = '2026-02-08'
        
        UNION ALL
        
        SELECT
            'Cost > 0 Only' as category,
            COUNT(*) as count,
            ROUND(SUM(cost), 2) as total_cost,
            SUM(installs) as total_installs
        FROM `yotam-395120.peerplay.ua_cohort`
        WHERE install_date = '2026-02-08'
            AND cost > 0
        
        UNION ALL
        
        SELECT
            'Installs > 0 Only' as category,
            COUNT(*) as count,
            ROUND(SUM(cost), 2) as total_cost,
            SUM(installs) as total_installs
        FROM `yotam-395120.peerplay.ua_cohort`
        WHERE install_date = '2026-02-08'
            AND installs > 0
            
        UNION ALL
        
        SELECT
            'Both > 0' as category,
            COUNT(*) as count,
            ROUND(SUM(cost), 2) as total_cost,
            SUM(installs) as total_installs
        FROM `yotam-395120.peerplay.ua_cohort`
        WHERE install_date = '2026-02-08'
            AND cost > 0
            AND installs > 0
        """
        
        print(f"\nZERO VALUES CHECK:")
        print("=" * 50)
        zero_result = client.query(zero_check_query).result()
        zero_df = zero_result.to_dataframe()
        
        for _, row in zero_df.iterrows():
            print(f"{row['category']:<15}: {row['count']:>6} records, ${row['total_cost']:>10,.2f}, {row['total_installs']:>6,} installs")
        
        return df.iloc[0].to_dict()
        
    except Exception as e:
        print(f"Error: {e}")
        return None

if __name__ == "__main__":
    verify_feb8_totals()