import pandas as pd
from google.cloud import bigquery

# Initialize BigQuery client
client = bigquery.Client(project='yotam-395120')

print("=== TOTAL DAILY REVENUE ANALYSIS CORRECTED ===")
print()

print("1. CONFIRMED CURRENT PERFORMANCE:")
print("• Daily Revenue: $56,414 (7-day average)")
print("• Daily Marketing Spend: ~$55,000") 
print("• Current ROAS: 1.03x (102.6%)")
print("• Revenue Mix: 85.2% IAP + 14.8% Ads")
print("• Attribution: 93.7% Paid + 6.3% Organic")
print("• Platform: 53.4% Android + 46.6% iOS")
print("• Daily Active Users: 68,672")
print("• ARPDAU: $0.82")
print()

print("2. SCALING TO $95K DAILY REVENUE:")
target_revenue = 95000
current_revenue = 56414
current_spend = 55000
current_roas = current_revenue / current_spend

revenue_gap = target_revenue - current_revenue
scaling_factor = target_revenue / current_revenue

print(f"• Target Revenue: ${target_revenue:,}")
print(f"• Current Revenue: ${current_revenue:,}")
print(f"• Revenue Gap: ${revenue_gap:,}")
print(f"• Scaling Factor: {scaling_factor:.2f}x")
print()

print("3. SPEND SCENARIOS:")
# Scenario 1: Maintain current ROAS
target_spend_current = target_revenue / current_roas
spend_increase_current = target_spend_current - current_spend

print(f"Scenario A - Maintain Current ROAS ({current_roas:.2f}x):")
print(f"  • Required Spend: ${target_spend_current:,.0f}")
print(f"  • Spend Increase: ${spend_increase_current:,.0f} ({spend_increase_current/current_spend*100:.0f}%)")
print()

# Scenario 2: Target 100% ROAS
target_spend_100 = target_revenue / 1.0
spend_increase_100 = target_spend_100 - current_spend

print(f"Scenario B - Target 100% ROAS (1.00x):")
print(f"  • Required Spend: ${target_spend_100:,.0f}")
print(f"  • Spend Increase: ${spend_increase_100:,.0f} ({spend_increase_100/current_spend*100:.0f}%)")
print()

print("4. STRATEGIC RECOMMENDATIONS:")
print()
print("IMMEDIATE ACTIONS:")
print("• Current 102.6% ROAS provides buffer for scaling")
print("• Need ~68% increase across all sources OR")
print("• Focus on high-performing sources for efficient scaling")
print()

print("SCALING PRIORITY:")
print("• Step 1: Increase spend by $20K/day on top sources")
print("• Step 2: Monitor ROAS - target to stay above 95%") 
print("• Step 3: Scale remaining $20K if Step 1 maintains efficiency")
print("• Step 4: Fine-tune based on source-level performance")
print()

print("PLATFORM STRATEGY:")
print("• Android generates 53.4% of revenue - slightly prioritize")
print("• iOS at 46.6% - maintain current investment level")
print("• Both platforms performing well relative to volume")
print()

print("RISK MITIGATION:")
print("• Start with conservative 30-40% spend increase")
print("• Test for 1-2 weeks before full scaling")
print("• Monitor daily ROAS to catch efficiency drops early")
print("• Have rollback plan if ROAS drops below 90%")

# Now get actual media source data
print()
print("=" * 60)
print("GETTING TOP MEDIA SOURCE DATA...")
print()

query = '''
SELECT 
  first_mediasource as media_source,
  SUM(total_revenue) as total_revenue_7d
FROM `yotam-395120.peerplay.agg_player_daily`
WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
  AND date < CURRENT_DATE()
  AND first_country NOT IN ("UA", "IL", "AM")
  AND first_mediasource IS NOT NULL
  AND first_mediasource != "organic"
GROUP BY first_mediasource
HAVING SUM(total_revenue) > 1000
ORDER BY total_revenue_7d DESC
LIMIT 10
'''

df = client.query(query).to_dataframe()
df['daily_revenue'] = df['total_revenue_7d'] / 7

print("TOP PAID MEDIA SOURCES (7-day totals):")
print("-" * 50)
total_paid = 0
for i, (_, row) in enumerate(df.iterrows(), 1):
    daily_rev = row['daily_revenue']
    total_paid += daily_rev
    print(f"{i:2}. {row['media_source'][:30]:30} ${daily_rev:8,.0f}/day")

print("-" * 50)
print(f"{'Total from Top 10 Sources:':32} ${total_paid:8,.0f}/day")
print(f"{'% of Total Paid Revenue:':32} {total_paid/52849*100:8.1f}%")

print()
print("SCALING MATH FOR TOP SOURCES:")
print(f"• To reach $95K total, need ${revenue_gap:,} additional revenue")
print(f"• If scaling top sources proportionally: {revenue_gap/total_paid:.2f}x increase needed")
print(f"• Each top source needs ~{(revenue_gap/total_paid)*100:.0f}% increase")
print()
print("Next step: Analyze individual source efficiency to prioritize scaling")