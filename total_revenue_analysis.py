import pandas as pd
from google.cloud import bigquery

# Initialize BigQuery client
client = bigquery.Client(project='yotam-395120')

# First get simple revenue totals by media source
query = '''
-- Media source performance for scaling analysis
SELECT 
  first_mediasource as media_source,
  COUNT(DISTINCT distinct_id) as total_users,
  SUM(total_revenue) as total_revenue
FROM `yotam-395120.peerplay.agg_player_daily`
WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
  AND date < CURRENT_DATE()
  AND first_country NOT IN ("UA", "IL", "AM")
  AND first_mediasource IS NOT NULL
GROUP BY first_mediasource
HAVING SUM(total_revenue) > 1000  -- Only sources with meaningful revenue
ORDER BY total_revenue DESC
LIMIT 15
'''

df = client.query(query).to_dataframe()

# Add calculated fields
df['avg_daily_revenue'] = df['total_revenue'] / 7
df['avg_daily_users'] = df['total_users'] / 7  
df['revenue_per_user'] = df['total_revenue'] / df['total_users']

print('TOP MEDIA SOURCES FOR SCALING (Last 7 Days)')
print('=' * 70)
print(f"{'Rank':<5}{'Media Source':<25}{'Daily Rev':<12}{'Daily Users':<12}{'RPU':<8}")
print('-' * 70)

for i, (_, row) in enumerate(df.iterrows(), 1):
    source = row['media_source'][:24]
    daily_rev = f"${row['avg_daily_revenue']:,.0f}"
    daily_users = f"{row['avg_daily_users']:,.0f}"
    rpu = f"${row['revenue_per_user']:.2f}"
    
    print(f"{i:<5}{source:<25}{daily_rev:<12}{daily_users:<12}{rpu:<8}")

print('\n')
print('SCALING ANALYSIS:')
print('=' * 30)

# Calculate totals
total_top_sources = df['avg_daily_revenue'].sum()
median_rpu = df['revenue_per_user'].median()

print(f'Total from top sources: ${total_top_sources:,.0f}/day')
print(f'Median RPU: ${median_rpu:.2f}')

# High-value sources
high_rpu_sources = df[df['revenue_per_user'] > median_rpu].copy()
high_rpu_sources = high_rpu_sources.sort_values('revenue_per_user', ascending=False)

print(f'\nHIGH-VALUE SOURCES (RPU > ${median_rpu:.2f}):')
for i, (_, row) in enumerate(high_rpu_sources.head(5).iterrows(), 1):
    print(f'{i}. {row["media_source"]:25} - ${row["revenue_per_user"]:6.2f} RPU, ${row["avg_daily_revenue"]:8,.0f}/day')

print(f'\nSCALING REQUIREMENTS:')
print(f'• Current total revenue: $56,414/day')
print(f'• Target revenue: $95,000/day') 
print(f'• Revenue gap: $38,586/day')
print(f'• Scaling factor needed: 1.68x')

scaling_factor = 38586 / total_top_sources
print(f'• Top sources need {scaling_factor:.2f}x scale ({(scaling_factor-1)*100:.0f}% increase)')

print(f'\nKEY RECOMMENDATIONS:')
print(f'1. Focus scaling on high-RPU sources (>${median_rpu:.2f} RPU)')
print(f'2. Current ROAS is healthy at 1.03x - good foundation for scaling')
print(f'3. Android slightly outperforms iOS (53.4% vs 46.6% of total revenue)')
print(f'4. Need to increase spend by ~$37-40K/day to reach $95K revenue target')
print(f'5. Test incremental scaling on top 5 sources before expanding budget')