#!/usr/bin/env python3
"""
Execute Revenue Scaling Analysis with BigQuery (CORRECTED VERSION)
Target: Scale to $95K daily revenue while maintaining ROAS
Fixed: Removed currency filter which doesn't exist in ua_cohort table
"""

import pandas as pd
import json
from datetime import datetime
import sys
import os

def execute_bigquery_analysis():
    """Execute the revenue scaling analysis using BigQuery"""
    
    try:
        from google.cloud import bigquery
        client = bigquery.Client()
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        results = {}
        
        print("🚀 EXECUTING REVENUE SCALING ANALYSIS (CORRECTED)")
        print("=" * 60)
        
        # Query 1: Current Baseline Performance (Fixed - removed currency filter)
        baseline_query = """
        WITH daily_performance AS (
          SELECT 
            install_date,
            country,
            platform,
            mediasource,
            SUM(cost) as daily_spend,
            SUM(installs) as daily_installs,
            SUM(d0_total_net_revenue) as d0_revenue,
            SUM(d1_total_net_revenue) as d1_revenue,
            SUM(d7_total_net_revenue) as d7_revenue,
            SAFE_DIVIDE(SUM(d0_total_net_revenue), SUM(cost)) as d0_roas,
            SAFE_DIVIDE(SUM(d1_total_net_revenue), SUM(cost)) as d1_roas,
            SAFE_DIVIDE(SUM(d7_total_net_revenue), SUM(cost)) as d7_roas
          FROM `yotam-395120.peerplay.ua_cohort`
          WHERE install_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
            AND install_date < CURRENT_DATE()
            AND cost > 0
            AND country NOT IN ('UA', 'IL', 'AM')
            AND is_test_campaign = FALSE
          GROUP BY 1, 2, 3, 4
        ),
        daily_totals AS (
          SELECT 
            install_date,
            SUM(daily_spend) as total_daily_spend,
            SUM(d0_revenue) as total_d0_revenue,
            SUM(d1_revenue) as total_d1_revenue,
            SUM(d7_revenue) as total_d7_revenue,
            SAFE_DIVIDE(SUM(d0_revenue), SUM(daily_spend)) as overall_d0_roas,
            SAFE_DIVIDE(SUM(d1_revenue), SUM(daily_spend)) as overall_d1_roas,
            SAFE_DIVIDE(SUM(d7_revenue), SUM(daily_spend)) as overall_d7_roas
          FROM daily_performance
          GROUP BY 1
        )
        
        SELECT 
          install_date,
          total_daily_spend as marketing_spend,
          total_d0_revenue as d0_revenue,
          total_d1_revenue as d1_revenue,
          total_d7_revenue as d7_revenue,
          overall_d0_roas as d0_roas,
          overall_d1_roas as d1_roas,
          overall_d7_roas as d7_roas
        FROM daily_totals
        ORDER BY install_date DESC;
        """
        
        print("📊 Executing baseline performance analysis...")
        baseline_df = client.query(baseline_query).to_dataframe()
        results['baseline'] = baseline_df
        
        # Calculate summary metrics
        avg_daily_spend = baseline_df['marketing_spend'].mean()
        avg_d0_revenue = baseline_df['d0_revenue'].mean()
        avg_d1_revenue = baseline_df['d1_revenue'].mean()
        avg_d7_revenue = baseline_df['d7_revenue'].mean()
        avg_d0_roas = baseline_df['d0_roas'].mean()
        avg_d1_roas = baseline_df['d1_roas'].mean()
        avg_d7_roas = baseline_df['d7_roas'].mean()
        
        print(f"\n📈 CURRENT PERFORMANCE BASELINE (Last 7 days)")
        print(f"   Average Daily Marketing Spend: ${avg_daily_spend:,.0f}")
        print(f"   Average Daily D0 Revenue: ${avg_d0_revenue:,.0f}")
        print(f"   Average Daily D1 Revenue: ${avg_d1_revenue:,.0f}")
        print(f"   Average Daily D7 Revenue: ${avg_d7_revenue:,.0f}")
        print(f"   Average D0 ROAS: {avg_d0_roas:.3f}")
        print(f"   Average D1 ROAS: {avg_d1_roas:.3f}")
        print(f"   Average D7 ROAS: {avg_d7_roas:.3f}")
        
        # Calculate scaling requirements
        target_revenue = 95000
        
        print(f"\n🎯 SCALING REQUIREMENTS")
        print(f"   Target Daily Revenue: ${target_revenue:,.0f}")
        print(f"   Current Daily Revenue (D1): ${avg_d1_revenue:,.0f}")
        print(f"   Revenue Gap: ${target_revenue - avg_d1_revenue:,.0f}")
        
        if avg_d1_roas > 0:
            additional_spend_d1 = (target_revenue - avg_d1_revenue) / avg_d1_roas
            target_spend_d1 = avg_daily_spend + additional_spend_d1
            budget_increase_pct = ((target_spend_d1 / avg_daily_spend) - 1) * 100
            
            print(f"   Additional Spend Needed (D1 ROAS): ${additional_spend_d1:,.0f}")
            print(f"   Target Daily Spend: ${target_spend_d1:,.0f}")
            print(f"   Budget Increase Required: {budget_increase_pct:.1f}%")
        
        if avg_d7_roas > 0:
            additional_spend_d7 = (target_revenue - avg_d7_revenue) / avg_d7_roas
            target_spend_d7 = avg_daily_spend + additional_spend_d7
            budget_increase_pct_d7 = ((target_spend_d7 / avg_daily_spend) - 1) * 100
            
            print(f"   Additional Spend Needed (D7 ROAS): ${additional_spend_d7:,.0f}")
            print(f"   Target Daily Spend (D7): ${target_spend_d7:,.0f}")
            print(f"   Budget Increase Required (D7): {budget_increase_pct_d7:.1f}%")
        
        # Query 2: Platform Performance
        platform_query = """
        WITH platform_performance AS (
          SELECT 
            platform,
            install_date,
            SUM(cost) as daily_spend,
            SUM(d0_total_net_revenue) as d0_revenue,
            SUM(d1_total_net_revenue) as d1_revenue,
            SUM(d7_total_net_revenue) as d7_revenue,
            SAFE_DIVIDE(SUM(d0_total_net_revenue), SUM(cost)) as d0_roas,
            SAFE_DIVIDE(SUM(d1_total_net_revenue), SUM(cost)) as d1_roas,
            SAFE_DIVIDE(SUM(d7_total_net_revenue), SUM(cost)) as d7_roas
          FROM `yotam-395120.peerplay.ua_cohort`
          WHERE install_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
            AND install_date < CURRENT_DATE()
            AND cost > 0
            AND country NOT IN ('UA', 'IL', 'AM')
            AND is_test_campaign = FALSE
          GROUP BY 1, 2
        ),
        platform_summary AS (
          SELECT 
            platform,
            AVG(daily_spend) as avg_daily_spend,
            AVG(d1_revenue) as avg_d1_revenue,
            AVG(d1_roas) as avg_d1_roas,
            AVG(d7_roas) as avg_d7_roas,
            SUM(daily_spend) as total_spend_7d
          FROM platform_performance
          GROUP BY 1
        )
        
        SELECT 
          platform,
          avg_daily_spend,
          avg_d1_revenue,
          avg_d1_roas,
          avg_d7_roas,
          total_spend_7d,
          CASE 
            WHEN avg_d1_roas > 1.0 THEN 'HIGH_SCALE'
            WHEN avg_d1_roas > 0.7 THEN 'MEDIUM_SCALE'
            ELSE 'LOW_SCALE'
          END as scaling_potential
        FROM platform_summary
        ORDER BY total_spend_7d DESC;
        """
        
        print(f"\n📱 Executing platform performance analysis...")
        platform_df = client.query(platform_query).to_dataframe()
        results['platform'] = platform_df
        
        print(f"\n📊 PLATFORM PERFORMANCE")
        for _, row in platform_df.iterrows():
            print(f"   {row['platform']}: ${row['avg_daily_spend']:,.0f}/day, "
                  f"D1 ROAS: {row['avg_d1_roas']:.3f}, "
                  f"Scale Potential: {row['scaling_potential']}")
        
        # Query 3: Top Media Sources
        source_query = """
        WITH source_performance AS (
          SELECT 
            mediasource,
            SUM(cost) as total_spend,
            AVG(cost) as avg_daily_spend,
            AVG(SAFE_DIVIDE(d1_total_net_revenue, cost)) as avg_d1_roas,
            AVG(SAFE_DIVIDE(d7_total_net_revenue, cost)) as avg_d7_roas,
            COUNT(DISTINCT install_date) as active_days
          FROM `yotam-395120.peerplay.ua_cohort`
          WHERE install_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
            AND install_date < CURRENT_DATE()
            AND cost > 0
            AND country NOT IN ('UA', 'IL', 'AM')
            AND is_test_campaign = FALSE
          GROUP BY 1
          HAVING SUM(cost) > 1000
        )
        
        SELECT 
          mediasource,
          total_spend,
          avg_daily_spend,
          avg_d1_roas,
          avg_d7_roas,
          active_days,
          CASE 
            WHEN avg_d1_roas > 1.2 AND total_spend > 5000 THEN 'HIGH_SCALE'
            WHEN avg_d1_roas > 0.8 AND total_spend > 2000 THEN 'MEDIUM_SCALE'
            ELSE 'LOW_SCALE'
          END as scaling_potential
        FROM source_performance
        ORDER BY total_spend DESC;
        """
        
        print(f"\n📺 Executing media source analysis...")
        source_df = client.query(source_query).to_dataframe()
        results['sources'] = source_df
        
        print(f"\n💰 TOP MEDIA SOURCES (7-day performance)")
        for _, row in source_df.head(10).iterrows():
            print(f"   {row['mediasource']}: ${row['total_spend']:,.0f} total, "
                  f"D1 ROAS: {row['avg_d1_roas']:.3f}, "
                  f"Scale: {row['scaling_potential']}")
        
        # Query 4: Geographic Performance
        geo_query = """
        WITH geo_performance AS (
          SELECT 
            CASE 
              WHEN country = 'US' THEN 'US'
              WHEN country IN ('GB', 'CA', 'AU') THEN 'Tier1_English'
              WHEN country IN ('DE', 'FR', 'IT', 'ES') THEN 'Tier1_EU'
              WHEN country IN ('JP', 'KR') THEN 'APAC_Premium'
              ELSE 'Other_International'
            END as region,
            SUM(cost) as total_spend,
            AVG(cost) as avg_daily_spend,
            AVG(SAFE_DIVIDE(d1_total_net_revenue, cost)) as avg_d1_roas,
            AVG(SAFE_DIVIDE(d7_total_net_revenue, cost)) as avg_d7_roas,
            COUNT(DISTINCT install_date || platform || mediasource) as data_points
          FROM `yotam-395120.peerplay.ua_cohort`
          WHERE install_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
            AND install_date < CURRENT_DATE()
            AND cost > 0
            AND country NOT IN ('UA', 'IL', 'AM')
            AND is_test_campaign = FALSE
          GROUP BY 1
          HAVING SUM(cost) > 500
        )
        
        SELECT 
          region,
          total_spend,
          avg_daily_spend,
          avg_d1_roas,
          avg_d7_roas,
          data_points,
          CASE 
            WHEN avg_d1_roas > 1.0 AND total_spend > 3000 THEN 'HIGH_SCALE'
            WHEN avg_d1_roas > 0.7 AND total_spend > 1000 THEN 'MEDIUM_SCALE'
            ELSE 'LOW_SCALE'
          END as scaling_potential
        FROM geo_performance
        ORDER BY total_spend DESC;
        """
        
        print(f"\n🌍 Executing geographic performance analysis...")
        geo_df = client.query(geo_query).to_dataframe()
        results['geography'] = geo_df
        
        print(f"\n🗺️ GEOGRAPHIC PERFORMANCE")
        for _, row in geo_df.iterrows():
            print(f"   {row['region']}: ${row['total_spend']:,.0f} total, "
                  f"D1 ROAS: {row['avg_d1_roas']:.3f}, "
                  f"Scale: {row['scaling_potential']}")
        
        # Save results to CSV files
        print(f"\n💾 SAVING RESULTS")
        for analysis_type, df in results.items():
            filename = f"revenue_scaling_{analysis_type}_results_{timestamp}.csv"
            df.to_csv(filename, index=False)
            print(f"   ✅ {filename}")
        
        # Create executive summary
        summary = {
            "analysis_timestamp": datetime.now().isoformat(),
            "target_revenue": target_revenue,
            "current_metrics": {
                "avg_daily_spend": float(avg_daily_spend),
                "avg_d0_revenue": float(avg_d0_revenue),
                "avg_d1_revenue": float(avg_d1_revenue),
                "avg_d7_revenue": float(avg_d7_revenue),
                "avg_d0_roas": float(avg_d0_roas),
                "avg_d1_roas": float(avg_d1_roas),
                "avg_d7_roas": float(avg_d7_roas)
            },
            "scaling_requirements": {
                "revenue_gap": float(target_revenue - avg_d1_revenue),
                "additional_spend_needed_d1": float(additional_spend_d1) if avg_d1_roas > 0 else None,
                "target_daily_spend_d1": float(target_spend_d1) if avg_d1_roas > 0 else None,
                "budget_increase_percent_d1": float(budget_increase_pct) if avg_d1_roas > 0 else None,
                "additional_spend_needed_d7": float(additional_spend_d7) if avg_d7_roas > 0 else None,
                "target_daily_spend_d7": float(target_spend_d7) if avg_d7_roas > 0 else None,
                "budget_increase_percent_d7": float(budget_increase_pct_d7) if avg_d7_roas > 0 else None
            },
            "top_scaling_opportunities": {
                "platforms": platform_df[platform_df['scaling_potential'] == 'HIGH_SCALE']['platform'].tolist(),
                "sources": source_df[source_df['scaling_potential'] == 'HIGH_SCALE']['mediasource'].tolist()[:5],
                "regions": geo_df[geo_df['scaling_potential'] == 'HIGH_SCALE']['region'].tolist()
            }
        }
        
        summary_filename = f"revenue_scaling_executive_summary_{timestamp}.json"
        with open(summary_filename, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        print(f"\n📋 EXECUTIVE SUMMARY")
        print(f"   ✅ {summary_filename}")
        print(f"\n🎯 SCALING STRATEGY RECOMMENDATIONS")
        
        # Scaling recommendations
        if avg_d1_roas > 0:
            print(f"   📈 Scale marketing spend from ${avg_daily_spend:,.0f} to ${target_spend_d1:,.0f}")
            print(f"   💰 Increase budget by {budget_increase_pct:.1f}% to reach $95K daily revenue")
        
        high_scale_platforms = platform_df[platform_df['scaling_potential'] == 'HIGH_SCALE']['platform'].tolist()
        if high_scale_platforms:
            print(f"   📱 Priority platforms for scaling: {', '.join(high_scale_platforms)}")
        
        high_scale_sources = source_df[source_df['scaling_potential'] == 'HIGH_SCALE']['mediasource'].tolist()[:3]
        if high_scale_sources:
            print(f"   📺 Top media sources to scale: {', '.join(high_scale_sources)}")
        
        high_scale_regions = geo_df[geo_df['scaling_potential'] == 'HIGH_SCALE']['region'].tolist()
        if high_scale_regions:
            print(f"   🌍 Focus regions: {', '.join(high_scale_regions)}")
        
        print(f"\n✅ REVENUE SCALING ANALYSIS COMPLETE")
        print(f"📁 Results saved with timestamp: {timestamp}")
        
        return results, summary
        
    except ImportError:
        print("❌ Google Cloud BigQuery library not available")
        print("📝 Please install: pip install google-cloud-bigquery")
        return None, None
        
    except Exception as e:
        print(f"❌ Error executing BigQuery analysis: {e}")
        return None, None

def main():
    """Main execution function"""
    
    print("🚀 REVENUE SCALING ANALYSIS - CORRECTED VERSION")
    print("🎯 Target: Scale to $95,000 daily revenue while maintaining ROAS")
    print("🔧 Fixed: Removed currency filter, added test campaign exclusion")
    print("=" * 70)
    
    # Execute analysis
    results, summary = execute_bigquery_analysis()
    
    return results, summary

if __name__ == "__main__":
    main()