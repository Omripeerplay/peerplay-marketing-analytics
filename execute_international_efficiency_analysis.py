#!/usr/bin/env python3
"""
International Performance Efficiency Analysis
Date: Feb 8, 2026

This script analyzes international UA performance efficiency by:
1. Country-level performance vs US benchmarks
2. Media source efficiency by country  
3. Cost arbitrage opportunities
4. Scaling priority recommendations
"""

from google.cloud import bigquery
import pandas as pd
import json
from datetime import datetime
import os

def execute_international_efficiency_analysis():
    """Execute comprehensive international efficiency analysis"""
    
    client = bigquery.Client(project='yotam-395120')
    
    query = """
    WITH country_source_performance AS (
      SELECT 
        country,
        mediasource,
        SUM(cost) as spend,
        SUM(installs) as installs,
        SAFE_DIVIDE(SUM(cost), SUM(CASE WHEN installs > 0 THEN installs END)) as cpi,
        SAFE_DIVIDE(SUM(d7_total_net_revenue), SUM(installs)) as d7_arpu,
        SAFE_DIVIDE(SUM(d7_total_net_revenue), SUM(cost)) as d7_roas,
        AVG(d7_retention) as d7_retention,
        COUNT(*) as cohorts
      FROM `yotam-395120.peerplay.ua_cohort`
      WHERE install_date = '2026-02-08'
        AND cost > 0
        AND country IS NOT NULL
        AND country != 'Unknown'
      GROUP BY country, mediasource
      HAVING installs >= 10  -- Minimum volume threshold
    ),
    us_benchmarks AS (
      SELECT 
        mediasource,
        SAFE_DIVIDE(SUM(cost), SUM(CASE WHEN installs > 0 THEN installs END)) as us_cpi,
        SAFE_DIVIDE(SUM(d7_total_net_revenue), SUM(cost)) as us_d7_roas,
        AVG(d7_retention) as us_d7_retention
      FROM `yotam-395120.peerplay.ua_cohort`
      WHERE install_date = '2026-02-08'
        AND country = 'US'
        AND cost > 0
      GROUP BY mediasource
    ),
    country_totals AS (
      SELECT 
        country,
        SUM(spend) as total_spend,
        SUM(installs) as total_installs,
        SAFE_DIVIDE(SUM(spend), SUM(installs)) as avg_cpi,
        SAFE_DIVIDE(SUM(spend * d7_roas), SUM(spend)) as weighted_d7_roas,
        COUNT(DISTINCT mediasource) as source_count
      FROM country_source_performance
      GROUP BY country
    )
    SELECT 
      csp.country,
      csp.mediasource,
      csp.spend,
      csp.installs,
      csp.cpi,
      csp.d7_arpu,
      csp.d7_roas,
      csp.d7_retention,
      ub.us_cpi,
      ub.us_d7_roas,
      ub.us_d7_retention,
      SAFE_DIVIDE(csp.cpi - ub.us_cpi, ub.us_cpi) as cpi_vs_us_pct,
      SAFE_DIVIDE(csp.d7_roas - ub.us_d7_roas, ub.us_d7_roas) as roas_vs_us_pct,
      ct.total_spend as country_total_spend,
      ct.avg_cpi as country_avg_cpi,
      CASE 
        WHEN csp.cpi < ub.us_cpi THEN 'Better than US'
        WHEN csp.cpi < ub.us_cpi * 1.1 THEN 'Comparable to US'
        ELSE 'More expensive than US'
      END as efficiency_rating,
      CASE 
        WHEN csp.spend >= 500 AND csp.cpi < ub.us_cpi THEN 'High Priority Scaling'
        WHEN csp.spend >= 200 AND csp.cpi < ub.us_cpi * 1.1 THEN 'Medium Priority'
        WHEN csp.cpi < ub.us_cpi THEN 'Small Scale Test'
        ELSE 'Monitor'
      END as scaling_priority
    FROM country_source_performance csp
    LEFT JOIN us_benchmarks ub USING (mediasource)
    LEFT JOIN country_totals ct USING (country)
    WHERE csp.country != 'US' -- Focus on international markets
    ORDER BY 
      CASE WHEN csp.cpi < ub.us_cpi THEN 1 ELSE 2 END, -- Efficient countries first
      csp.spend DESC
    """
    
    print("Executing International Efficiency Analysis...")
    print("Query processing...")
    
    try:
        # Execute query
        df = client.query(query).to_dataframe()
        
        if df.empty:
            print("No data returned for Feb 8, 2026")
            return
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save detailed results
        filename = f"international_efficiency_analysis_{timestamp}.csv"
        df.to_csv(filename, index=False)
        
        # Generate executive summary
        summary = generate_executive_summary(df)
        
        # Save summary
        summary_filename = f"international_efficiency_executive_summary_{timestamp}.json"
        with open(summary_filename, 'w') as f:
            json.dump(summary, f, indent=2, default=str)
        
        print(f"✅ Analysis completed successfully!")
        print(f"📊 Results saved to: {filename}")
        print(f"📋 Executive summary: {summary_filename}")
        print(f"📈 Total records analyzed: {len(df):,}")
        
        # Display key insights
        display_key_insights(summary)
        
        return filename, summary_filename
        
    except Exception as e:
        print(f"❌ Error executing analysis: {str(e)}")
        return None, None

def generate_executive_summary(df):
    """Generate executive summary of international efficiency analysis"""
    
    # Efficiency analysis
    better_than_us = df[df['efficiency_rating'] == 'Better than US']
    high_priority = df[df['scaling_priority'] == 'High Priority Scaling']
    
    # Volume analysis
    total_intl_spend = df['spend'].sum()
    total_intl_installs = df['installs'].sum()
    
    # Top opportunities
    top_opportunities = better_than_us.nlargest(10, 'spend')
    
    summary = {
        'analysis_date': '2026-02-08',
        'total_international_spend': float(total_intl_spend),
        'total_international_installs': int(total_intl_installs),
        'countries_analyzed': df['country'].nunique(),
        'media_sources_analyzed': df['mediasource'].nunique(),
        
        'efficiency_breakdown': {
            'better_than_us': len(better_than_us),
            'comparable_to_us': len(df[df['efficiency_rating'] == 'Comparable to US']),
            'more_expensive_than_us': len(df[df['efficiency_rating'] == 'More expensive than US'])
        },
        
        'scaling_priorities': {
            'high_priority_scaling': len(high_priority),
            'medium_priority': len(df[df['scaling_priority'] == 'Medium Priority']),
            'small_scale_test': len(df[df['scaling_priority'] == 'Small Scale Test']),
            'monitor': len(df[df['scaling_priority'] == 'Monitor'])
        },
        
        'top_opportunities': top_opportunities[['country', 'mediasource', 'spend', 'cpi', 'efficiency_rating', 'scaling_priority']].to_dict('records'),
        
        'cost_arbitrage_potential': {
            'better_efficiency_spend': float(better_than_us['spend'].sum()),
            'better_efficiency_countries': better_than_us['country'].nunique(),
            'avg_cpi_savings_pct': float(better_than_us['cpi_vs_us_pct'].mean()) if not better_than_us.empty else 0
        },
        
        'key_insights': generate_key_insights(df)
    }
    
    return summary

def generate_key_insights(df):
    """Generate key insights from the analysis"""
    insights = []
    
    # Efficiency insights
    better_than_us = df[df['efficiency_rating'] == 'Better than US']
    if not better_than_us.empty:
        avg_savings = better_than_us['cpi_vs_us_pct'].mean() * -1
        insights.append(f"Found {len(better_than_us)} country/source combinations with better CPI efficiency than US (avg {avg_savings:.1%} savings)")
    
    # Volume insights
    high_volume_efficient = df[(df['spend'] >= 500) & (df['efficiency_rating'] == 'Better than US')]
    if not high_volume_efficient.empty:
        insights.append(f"Identified {len(high_volume_efficient)} high-volume, high-efficiency opportunities for immediate scaling")
    
    # Top country insights
    country_performance = df.groupby('country').agg({
        'spend': 'sum',
        'installs': 'sum',
        'cpi': 'mean'
    }).sort_values('spend', ascending=False)
    
    top_country = country_performance.index[0]
    insights.append(f"Top international market by spend: {top_country} (${country_performance.loc[top_country, 'spend']:,.0f})")
    
    # Media source insights
    source_efficiency = better_than_us.groupby('mediasource').size().sort_values(ascending=False)
    if not source_efficiency.empty:
        top_efficient_source = source_efficiency.index[0]
        insights.append(f"Most internationally efficient media source: {top_efficient_source} ({source_efficiency.iloc[0]} efficient markets)")
    
    return insights

def display_key_insights(summary):
    """Display key insights from the analysis"""
    print("\n" + "="*80)
    print("🎯 INTERNATIONAL EFFICIENCY ANALYSIS - KEY INSIGHTS")
    print("="*80)
    
    print(f"📊 Total International Performance:")
    print(f"   • Spend: ${summary['total_international_spend']:,.0f}")
    print(f"   • Installs: {summary['total_international_installs']:,}")
    print(f"   • Countries: {summary['countries_analyzed']}")
    print(f"   • Media Sources: {summary['media_sources_analyzed']}")
    
    print(f"\n🚀 Efficiency Breakdown:")
    eff = summary['efficiency_breakdown']
    print(f"   • Better than US: {eff['better_than_us']} combinations")
    print(f"   • Comparable to US: {eff['comparable_to_us']} combinations")
    print(f"   • More expensive: {eff['more_expensive_than_us']} combinations")
    
    print(f"\n📈 Scaling Priorities:")
    scale = summary['scaling_priorities']
    print(f"   • High Priority: {scale['high_priority_scaling']} opportunities")
    print(f"   • Medium Priority: {scale['medium_priority']} opportunities")
    print(f"   • Test & Monitor: {scale['small_scale_test'] + scale['monitor']} combinations")
    
    print(f"\n💰 Cost Arbitrage Potential:")
    arb = summary['cost_arbitrage_potential']
    print(f"   • Efficient Market Spend: ${arb['better_efficiency_spend']:,.0f}")
    print(f"   • Efficient Countries: {arb['better_efficiency_countries']}")
    print(f"   • Avg CPI Savings: {arb['avg_cpi_savings_pct']:.1%}")
    
    print(f"\n🔍 Key Insights:")
    for i, insight in enumerate(summary['key_insights'], 1):
        print(f"   {i}. {insight}")
    
    print(f"\n🏆 Top 5 Scaling Opportunities:")
    for i, opp in enumerate(summary['top_opportunities'][:5], 1):
        print(f"   {i}. {opp['country']} - {opp['mediasource']}: ${opp['spend']:,.0f} spend, {opp['efficiency_rating']}")

if __name__ == "__main__":
    execute_international_efficiency_analysis()