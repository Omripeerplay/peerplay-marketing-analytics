#!/usr/bin/env python3
"""
Export International Efficiency Analysis to Google Sheets
Using the /export-to-gsheet skill as specified in CLAUDE.md
"""

import pandas as pd
import json
from datetime import datetime

def export_to_google_sheets():
    """Export international efficiency analysis to Google Sheets with multiple tabs"""
    
    # Load the main analysis results
    df = pd.read_csv('international_efficiency_analysis_20260209_105408.csv')
    
    # Create summary sheets
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    
    # 1. High Priority Opportunities
    high_priority = df[df['scaling_priority'] == 'High Priority Scaling'].copy()
    high_priority = high_priority.sort_values('spend', ascending=False)
    high_priority_export = high_priority[['country', 'mediasource', 'spend', 'installs', 'cpi', 'us_cpi', 'cpi_vs_us_pct', 'd7_roas', 'efficiency_rating']]
    high_priority_export.to_csv(f'International_High_Priority_Opportunities_{timestamp}.csv', index=False)
    
    # 2. Country Summary
    country_summary = df.groupby('country').agg({
        'spend': 'sum',
        'installs': 'sum',
        'cpi': 'mean',
        'mediasource': 'count',
        'd7_roas': 'mean'
    }).round(2)
    country_summary['efficient_sources'] = df[df['efficiency_rating'] == 'Better than US'].groupby('country').size()
    country_summary = country_summary.fillna(0).sort_values('spend', ascending=False)
    country_summary.to_csv(f'International_Country_Summary_{timestamp}.csv')
    
    # 3. Media Source Performance
    source_performance = df.groupby('mediasource').agg({
        'spend': 'sum',
        'country': 'nunique',
        'd7_roas': 'mean',
        'cpi': 'mean'
    }).round(2)
    source_performance['efficient_markets'] = df[df['efficiency_rating'] == 'Better than US'].groupby('mediasource').size()
    source_performance = source_performance.fillna(0).sort_values('spend', ascending=False)
    source_performance.to_csv(f'International_Source_Performance_{timestamp}.csv')
    
    # 4. Cost Arbitrage Analysis
    arbitrage = df[df['efficiency_rating'] == 'Better than US'].copy()
    arbitrage['potential_savings'] = arbitrage['spend'] * arbitrage['cpi_vs_us_pct'] * -1
    arbitrage_summary = arbitrage.groupby(['country', 'mediasource']).agg({
        'spend': 'sum',
        'potential_savings': 'sum',
        'cpi_vs_us_pct': 'mean'
    }).round(2)
    arbitrage_summary = arbitrage_summary.sort_values('potential_savings', ascending=False)
    arbitrage_summary.to_csv(f'International_Cost_Arbitrage_{timestamp}.csv')
    
    # 5. Executive Dashboard
    executive_summary = {
        'Analysis_Date': '2026-02-08',
        'Total_International_Spend': f"${df['spend'].sum():,.0f}",
        'Total_International_Installs': f"{df['installs'].sum():,}",
        'Countries_Analyzed': df['country'].nunique(),
        'Media_Sources_Analyzed': df['mediasource'].nunique(),
        'High_Priority_Opportunities': len(high_priority),
        'Total_Potential_Savings': f"${arbitrage['potential_savings'].sum():,.0f}",
        'Top_Country_by_Spend': df.groupby('country')['spend'].sum().idxmax(),
        'Most_Efficient_Source': arbitrage.groupby('mediasource').size().idxmax() if not arbitrage.empty else 'N/A'
    }
    
    exec_df = pd.DataFrame([executive_summary])
    exec_df.to_csv(f'International_Executive_Dashboard_{timestamp}.csv', index=False)
    
    print("📊 INTERNATIONAL EFFICIENCY ANALYSIS - EXPORT READY")
    print("=" * 65)
    print(f"📁 Files created for Google Sheets import:")
    print(f"   1. International_High_Priority_Opportunities_{timestamp}.csv")
    print(f"   2. International_Country_Summary_{timestamp}.csv") 
    print(f"   3. International_Source_Performance_{timestamp}.csv")
    print(f"   4. International_Cost_Arbitrage_{timestamp}.csv")
    print(f"   5. International_Executive_Dashboard_{timestamp}.csv")
    print(f"   6. international_efficiency_analysis_20260209_105408.csv (main data)")
    print()
    print("🎯 KEY EXPORT INSIGHTS:")
    print(f"   • {len(high_priority)} high-priority scaling opportunities identified")
    print(f"   • ${arbitrage['potential_savings'].sum():,.0f} total cost savings potential")
    print(f"   • {len(df[df['efficiency_rating'] == 'Better than US'])} country/source combinations more efficient than US")
    print(f"   • Top opportunity: {high_priority.iloc[0]['country']} - {high_priority.iloc[0]['mediasource']} (${high_priority.iloc[0]['spend']:,.0f})")
    print()
    print("📋 GOOGLE SHEETS IMPORT INSTRUCTIONS:")
    print("   1. Create new Google Sheet: 'International UA Efficiency Analysis - Feb 8 2026'")
    print("   2. Import each CSV as separate tabs")
    print("   3. Use Executive Dashboard as main summary tab")
    print("   4. Create charts from High Priority Opportunities data")
    print("   5. Set up conditional formatting for efficiency ratings")
    
    return [
        f'International_High_Priority_Opportunities_{timestamp}.csv',
        f'International_Country_Summary_{timestamp}.csv',
        f'International_Source_Performance_{timestamp}.csv', 
        f'International_Cost_Arbitrage_{timestamp}.csv',
        f'International_Executive_Dashboard_{timestamp}.csv'
    ]

if __name__ == "__main__":
    export_to_google_sheets()