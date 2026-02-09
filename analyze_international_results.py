#!/usr/bin/env python3
"""
Analyze International Efficiency Results
"""

import pandas as pd
import json

def analyze_results():
    # Load the detailed results
    df = pd.read_csv('international_efficiency_analysis_20260209_105408.csv')
    
    print('DETAILED BREAKDOWN OF INTERNATIONAL EFFICIENCY ANALYSIS')
    print('='*70)
    print()
    
    # High Priority Scaling Opportunities
    high_priority = df[df['scaling_priority'] == 'High Priority Scaling'].sort_values('spend', ascending=False)
    print('🚀 HIGH PRIORITY SCALING OPPORTUNITIES (>$500 spend + better CPI than US):')
    print('-' * 70)
    for _, row in high_priority.iterrows():
        savings_pct = row['cpi_vs_us_pct'] * -100
        print(f"{row['country']:3} - {row['mediasource']:12} | ${row['spend']:6.0f} | CPI: ${row['cpi']:5.2f} | {savings_pct:4.1f}% savings vs US")
    print()
    
    # Country Analysis
    print('🌍 COUNTRY PERFORMANCE ANALYSIS:')
    print('-' * 70)
    country_summary = df.groupby('country').agg({
        'spend': 'sum',
        'installs': 'sum', 
        'cpi': 'mean',
        'mediasource': 'count'
    }).round(2)
    country_summary['avg_cpi'] = country_summary['spend'] / country_summary['installs']
    country_summary = country_summary.sort_values('spend', ascending=False)
    
    for country in country_summary.index[:10]:  # Top 10 countries
        row = country_summary.loc[country]
        efficient_sources = len(df[(df['country'] == country) & (df['efficiency_rating'] == 'Better than US')])
        print(f"{country:3} | ${row['spend']:6.0f} spend | {row['installs']:4.0f} installs | ${row['avg_cpi']:5.2f} CPI | {efficient_sources}/{int(row['mediasource'])} efficient sources")
    print()
    
    # Media Source Analysis  
    print('📱 MEDIA SOURCE INTERNATIONAL EFFICIENCY:')
    print('-' * 70)
    source_summary = df.groupby('mediasource').agg({
        'spend': 'sum',
        'country': 'nunique',
        'efficiency_rating': lambda x: (x == 'Better than US').sum()
    }).sort_values('spend', ascending=False)
    
    for source in source_summary.index:
        row = source_summary.loc[source]
        eff_pct = (row['efficiency_rating'] / row['country']) * 100
        print(f"{source:12} | ${row['spend']:6.0f} spend | {int(row['country']):2d} countries | {int(row['efficiency_rating']):2d}/{int(row['country']):2d} efficient ({eff_pct:4.1f}%)")
    print()
    
    # Cost Arbitrage Analysis
    print('💰 COST ARBITRAGE OPPORTUNITIES:')
    print('-' * 70)
    arbitrage = df[df['efficiency_rating'] == 'Better than US'].copy()
    arbitrage['potential_savings'] = arbitrage['spend'] * arbitrage['cpi_vs_us_pct'] * -1
    arbitrage_by_source = arbitrage.groupby('mediasource').agg({
        'spend': 'sum',
        'potential_savings': 'sum', 
        'country': 'nunique'
    }).sort_values('potential_savings', ascending=False)
    
    for source in arbitrage_by_source.index:
        row = arbitrage_by_source.loc[source]
        savings_pct = (row['potential_savings'] / row['spend']) * 100
        print(f"{source:12} | ${row['spend']:6.0f} current | ${row['potential_savings']:5.0f} potential savings | {row['country']} countries | {savings_pct:4.1f}% avg savings")
    
    print()
    print('🎯 STRATEGIC RECOMMENDATIONS:')
    print('-' * 70)
    
    # Generate recommendations
    recommendations = []
    
    # Top scaling opportunities
    if not high_priority.empty:
        top_opp = high_priority.iloc[0]
        recommendations.append(f"1. IMMEDIATE SCALE: {top_opp['country']} - {top_opp['mediasource']} showing ${top_opp['spend']:.0f} spend with {abs(top_opp['cpi_vs_us_pct']*100):.1f}% CPI efficiency")
    
    # Best performing countries
    top_countries = country_summary.head(3)
    for i, (country, row) in enumerate(top_countries.iterrows(), 2):
        efficient_count = len(df[(df['country'] == country) & (df['efficiency_rating'] == 'Better than US')])
        if efficient_count > 0:
            recommendations.append(f"{i}. COUNTRY FOCUS: {country} has {efficient_count} efficient sources with ${row['spend']:.0f} total spend")
    
    # Best media sources
    best_sources = source_summary[source_summary['efficiency_rating'] >= 5].head(2)
    for i, (source, row) in enumerate(best_sources.iterrows(), len(recommendations)+1):
        recommendations.append(f"{i}. SOURCE EXPANSION: {source} efficient in {row['efficiency_rating']}/{row['country']} markets - expand budget")
    
    for rec in recommendations:
        print(rec)

if __name__ == "__main__":
    analyze_results()