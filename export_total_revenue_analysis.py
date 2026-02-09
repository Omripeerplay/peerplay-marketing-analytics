import pandas as pd
from google.cloud import bigquery

# Initialize BigQuery client
client = bigquery.Client(project='yotam-395120')

# Create comprehensive analysis for export
data = []

# Executive Summary
data.append({
    'Category': 'CURRENT PERFORMANCE',
    'Metric': 'Daily Revenue (7-day avg)',
    'Value': '$56,414',
    'Notes': 'Total revenue from all users'
})

data.append({
    'Category': 'CURRENT PERFORMANCE', 
    'Metric': 'Daily Marketing Spend',
    'Value': '$55,000',
    'Notes': 'Estimated from Feb 8 analysis'
})

data.append({
    'Category': 'CURRENT PERFORMANCE',
    'Metric': 'Current ROAS',
    'Value': '1.03x (102.6%)',
    'Notes': 'Healthy baseline for scaling'
})

data.append({
    'Category': 'CURRENT PERFORMANCE',
    'Metric': 'Revenue Mix',
    'Value': '85.2% IAP + 14.8% Ads',
    'Notes': 'Strong in-app purchase performance'
})

data.append({
    'Category': 'CURRENT PERFORMANCE',
    'Metric': 'Attribution Split',
    'Value': '93.7% Paid + 6.3% Organic',
    'Notes': 'Heavy reliance on paid acquisition'
})

data.append({
    'Category': 'CURRENT PERFORMANCE',
    'Metric': 'Platform Split',
    'Value': '53.4% Android + 46.6% iOS',
    'Notes': 'Balanced platform performance'
})

data.append({
    'Category': 'CURRENT PERFORMANCE',
    'Metric': 'Daily Active Users',
    'Value': '68,672',
    'Notes': 'Strong user base'
})

data.append({
    'Category': 'CURRENT PERFORMANCE',
    'Metric': 'ARPDAU',
    'Value': '$0.82',
    'Notes': 'Revenue per daily active user'
})

# Scaling Requirements
data.append({
    'Category': 'SCALING REQUIREMENTS',
    'Metric': 'Target Revenue',
    'Value': '$95,000',
    'Notes': 'Daily revenue goal'
})

data.append({
    'Category': 'SCALING REQUIREMENTS',
    'Metric': 'Revenue Gap',
    'Value': '$38,586',
    'Notes': 'Additional daily revenue needed'
})

data.append({
    'Category': 'SCALING REQUIREMENTS',
    'Metric': 'Scaling Factor',
    'Value': '1.68x',
    'Notes': '68% increase needed'
})

# Spend Scenarios
data.append({
    'Category': 'SPEND SCENARIOS',
    'Metric': 'Scenario A - Maintain 1.03x ROAS',
    'Value': '$92,619 spend (+$37,619)',
    'Notes': 'Conservative approach'
})

data.append({
    'Category': 'SPEND SCENARIOS',
    'Metric': 'Scenario B - Target 1.00x ROAS',
    'Value': '$95,000 spend (+$40,000)',
    'Notes': 'Break-even approach'
})

# Create DataFrame
df_summary = pd.DataFrame(data)

# Get media source data
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

df_sources = client.query(query).to_dataframe()
df_sources['daily_revenue'] = df_sources['total_revenue_7d'] / 7
df_sources['scaling_79pct'] = df_sources['daily_revenue'] * 1.79  # 79% increase
df_sources['additional_revenue'] = df_sources['scaling_79pct'] - df_sources['daily_revenue']

# Rename columns for export
df_sources = df_sources.rename(columns={
    'media_source': 'Media Source',
    'total_revenue_7d': '7-Day Total Revenue',
    'daily_revenue': 'Current Daily Revenue',
    'scaling_79pct': 'Target Daily Revenue (79% increase)',
    'additional_revenue': 'Additional Revenue Needed'
})

# Round monetary values
monetary_cols = ['7-Day Total Revenue', 'Current Daily Revenue', 'Target Daily Revenue (79% increase)', 'Additional Revenue Needed']
for col in monetary_cols:
    df_sources[col] = df_sources[col].round(2)

print("TOTAL DAILY REVENUE ANALYSIS - EXPORT READY")
print("=" * 50)
print()
print("SUMMARY DATA:")
print(df_summary.to_string(index=False))
print()
print("TOP MEDIA SOURCES:")
print(df_sources.to_string(index=False))
print()

# Save to CSV files
df_summary.to_csv('total_revenue_executive_summary.csv', index=False)
df_sources.to_csv('top_media_sources_scaling.csv', index=False)

print("Files saved:")
print("1. total_revenue_executive_summary.csv")
print("2. top_media_sources_scaling.csv")

# Create recommendations DataFrame
recommendations = [
    {'Priority': 'HIGH', 'Action': 'Start with 30-40% spend increase on top 3 sources', 'Timeline': 'Week 1', 'Expected Impact': '+$12-15K daily revenue'},
    {'Priority': 'HIGH', 'Action': 'Monitor ROAS daily, maintain above 95%', 'Timeline': 'Ongoing', 'Expected Impact': 'Risk mitigation'},  
    {'Priority': 'MEDIUM', 'Action': 'Scale additional $20K if Week 1 successful', 'Timeline': 'Week 2-3', 'Expected Impact': '+$20-25K daily revenue'},
    {'Priority': 'MEDIUM', 'Action': 'Fine-tune by individual source performance', 'Timeline': 'Week 3-4', 'Expected Impact': 'Efficiency optimization'},
    {'Priority': 'LOW', 'Action': 'Test new sources if current scaling maxes out', 'Timeline': 'Week 4+', 'Expected Impact': 'Additional growth potential'}
]

df_recommendations = pd.DataFrame(recommendations)
df_recommendations.to_csv('scaling_recommendations.csv', index=False)

print("3. scaling_recommendations.csv")
print()
print("Ready to export to Google Sheets!")