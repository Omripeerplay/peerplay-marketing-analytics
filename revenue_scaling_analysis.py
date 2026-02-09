#!/usr/bin/env python3
"""
Revenue vs Marketing Spend Analysis for Scaling Strategy
Target: Scale to $95K daily revenue while maintaining ROAS
"""

import json
from datetime import datetime, timedelta

def create_scaling_analysis_queries():
    """Create comprehensive BigQuery analysis for revenue scaling strategy"""
    
    # Base query for current performance baseline
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
        AND currency != 'UAH'
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
      'CURRENT_BASELINE' as metric_type,
      install_date,
      total_daily_spend as marketing_spend,
      total_d0_revenue as d0_revenue,
      total_d1_revenue as d1_revenue,
      total_d7_revenue as d7_revenue,
      overall_d0_roas as d0_roas,
      overall_d1_roas as d1_roas,
      overall_d7_roas as d7_roas,
      NULL as platform,
      NULL as country,
      NULL as mediasource
    FROM daily_totals
    ORDER BY install_date DESC;
    """
    
    # Platform breakdown query
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
        AND currency != 'UAH'
      GROUP BY 1, 2
    )
    
    SELECT 
      'PLATFORM_PERFORMANCE' as metric_type,
      install_date,
      daily_spend as marketing_spend,
      d0_revenue,
      d1_revenue,
      d7_revenue,
      d0_roas,
      d1_roas,
      d7_roas,
      platform,
      NULL as country,
      NULL as mediasource
    FROM platform_performance
    ORDER BY install_date DESC, daily_spend DESC;
    """
    
    # Geographic breakdown query
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
        AND currency != 'UAH'
      GROUP BY 1, 2
    )
    
    SELECT 
      'GEO_PERFORMANCE' as metric_type,
      install_date,
      daily_spend as marketing_spend,
      d0_revenue,
      d1_revenue,
      d7_revenue,
      d0_roas,
      d1_roas,
      d7_roas,
      NULL as platform,
      region as country,
      NULL as mediasource
    FROM geo_performance
    WHERE daily_spend > 100  -- Focus on meaningful spend
    ORDER BY install_date DESC, daily_spend DESC;
    """
    
    # Media source performance query
    source_query = """
    WITH source_performance AS (
      SELECT 
        mediasource,
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
        AND currency != 'UAH'
      GROUP BY 1, 2
    ),
    source_totals AS (
      SELECT 
        mediasource,
        SUM(daily_spend) as total_7d_spend,
        AVG(daily_spend) as avg_daily_spend,
        AVG(d1_roas) as avg_d1_roas,
        AVG(d7_roas) as avg_d7_roas
      FROM source_performance
      GROUP BY 1
      HAVING SUM(daily_spend) > 1000  -- Focus on sources with meaningful spend
    )
    
    SELECT 
      'SOURCE_PERFORMANCE' as metric_type,
      NULL as install_date,
      avg_daily_spend as marketing_spend,
      NULL as d0_revenue,
      NULL as d1_revenue,
      NULL as d7_revenue,
      NULL as d0_roas,
      avg_d1_roas as d1_roas,
      avg_d7_roas as d7_roas,
      NULL as platform,
      NULL as country,
      mediasource,
      total_7d_spend,
      CASE 
        WHEN avg_d1_roas > 1.2 AND total_7d_spend > 5000 THEN 'HIGH_SCALE_POTENTIAL'
        WHEN avg_d1_roas > 0.8 AND total_7d_spend > 2000 THEN 'MEDIUM_SCALE_POTENTIAL'
        ELSE 'LOW_SCALE_POTENTIAL'
      END as scaling_tier
    FROM source_totals
    ORDER BY total_7d_spend DESC;
    """
    
    # Combined scaling requirements calculation
    scaling_calc_query = """
    WITH current_performance AS (
      SELECT 
        AVG(SUM(cost)) as avg_daily_spend,
        AVG(SUM(d1_total_net_revenue)) as avg_daily_d1_revenue,
        AVG(SUM(d7_total_net_revenue)) as avg_daily_d7_revenue,
        AVG(SAFE_DIVIDE(SUM(d1_total_net_revenue), SUM(cost))) as avg_d1_roas,
        AVG(SAFE_DIVIDE(SUM(d7_total_net_revenue), SUM(cost))) as avg_d7_roas
      FROM `yotam-395120.peerplay.ua_cohort`
      WHERE install_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
        AND install_date < CURRENT_DATE()
        AND cost > 0
        AND country NOT IN ('UA', 'IL', 'AM')
        AND currency != 'UAH'
      GROUP BY install_date
    )
    
    SELECT 
      'SCALING_REQUIREMENTS' as metric_type,
      avg_daily_spend as current_daily_spend,
      avg_daily_d1_revenue as current_daily_d1_revenue,
      avg_daily_d7_revenue as current_daily_d7_revenue,
      avg_d1_roas as current_d1_roas,
      avg_d7_roas as current_d7_roas,
      
      -- Calculate scaling requirements to reach $95K daily revenue
      CASE 
        WHEN avg_daily_d1_revenue > 0 THEN 
          ROUND((95000 - avg_daily_d1_revenue) / avg_d1_roas, 0)
        ELSE NULL 
      END as additional_spend_needed_d1,
      
      CASE 
        WHEN avg_daily_d7_revenue > 0 THEN 
          ROUND((95000 - avg_daily_d7_revenue) / avg_d7_roas, 0)
        ELSE NULL 
      END as additional_spend_needed_d7,
      
      CASE 
        WHEN avg_daily_d1_revenue > 0 THEN 
          ROUND(((95000 - avg_daily_d1_revenue) / avg_d1_roas + avg_daily_spend), 0)
        ELSE NULL 
      END as target_daily_spend_d1,
      
      CASE 
        WHEN avg_daily_d7_revenue > 0 THEN 
          ROUND(((95000 - avg_daily_d7_revenue) / avg_d7_roas + avg_daily_spend), 0)
        ELSE NULL 
      END as target_daily_spend_d7,
      
      ROUND((95000 / avg_daily_d1_revenue - 1) * 100, 1) as revenue_increase_percent_needed
      
    FROM current_performance;
    """
    
    return {
        'baseline_analysis': baseline_query,
        'platform_breakdown': platform_query,
        'geographic_breakdown': geo_query,
        'source_performance': source_query,
        'scaling_calculations': scaling_calc_query
    }

def main():
    """Execute the revenue scaling analysis"""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Create analysis queries
    queries = create_scaling_analysis_queries()
    
    # Save queries to files for execution
    for analysis_type, query in queries.items():
        filename = f"revenue_scaling_{analysis_type}_{timestamp}.sql"
        with open(filename, 'w') as f:
            f.write(f"-- Revenue Scaling Analysis: {analysis_type.replace('_', ' ').title()}\n")
            f.write(f"-- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"-- Target: Scale to $95K daily revenue while maintaining ROAS\n\n")
            f.write(query)
        print(f"✅ Created query file: {filename}")
    
    # Create execution plan
    execution_plan = {
        "analysis_goal": "Scale to $95,000 daily revenue while maintaining current ROAS levels",
        "current_date": datetime.now().isoformat(),
        "queries_created": list(queries.keys()),
        "next_steps": [
            "1. Execute baseline_analysis query to get current performance metrics",
            "2. Execute platform_breakdown to identify scaling opportunities by platform",
            "3. Execute geographic_breakdown to find best regions for scaling",
            "4. Execute source_performance to identify top media sources for increased spend",
            "5. Execute scaling_calculations to determine exact budget requirements",
            "6. Compile results into scaling strategy recommendation"
        ],
        "key_metrics_to_track": [
            "Current daily marketing spend",
            "Current daily revenue (D1 and D7)",
            "Current ROAS by platform/geo/source",
            "Additional spend needed to reach $95K revenue",
            "Scaling potential by channel"
        ]
    }
    
    # Save execution plan
    plan_filename = f"revenue_scaling_execution_plan_{timestamp}.json"
    with open(plan_filename, 'w') as f:
        json.dump(execution_plan, f, indent=2)
    
    print(f"\n📋 REVENUE SCALING ANALYSIS SETUP COMPLETE")
    print(f"📁 Execution plan saved: {plan_filename}")
    print(f"\n🎯 ANALYSIS GOAL:")
    print(f"   Scale from current revenue to $95,000 daily revenue")
    print(f"   while maintaining current ROAS levels")
    print(f"\n📊 QUERIES CREATED:")
    for i, analysis_type in enumerate(queries.keys(), 1):
        print(f"   {i}. {analysis_type.replace('_', ' ').title()}")
    
    return queries, execution_plan

if __name__ == "__main__":
    main()