# PeerPlay Marketing Analytics Agent

## Overview

Comprehensive UA (User Acquisition) performance analysis system for Merge Cruise mobile game with cohort tracking, ROAS decomposition, and automated alerting. Built for BigQuery analytics with real-time monitoring capabilities.

## 📊 Core Features

### 1. Daily Health Monitoring
- **Automated Alerts**: Flags CPI spikes (>20%), volume drops (>30%), retention issues
- **Performance Comparison**: Day-over-day metrics analysis
- **Strong Performer Detection**: Identifies sources scaling efficiently
- **Blended Metrics**: Total spend, installs, and CPI calculations

### 2. Weekly Cohort Analysis
- **ROAS Decomposition**: Breaks down performance into retention, monetization, and cost factors
- **Week-over-Week Comparison**: 7-day cohort performance tracking
- **Source Attribution**: Performance analysis by traffic source and campaign type
- **Trend Analysis**: Historical pattern recognition

### 3. Source Deep Dive
- **8-Week Historical Tracking**: Comprehensive source performance over time
- **Trend Classification**: Automatically categorizes CPI, retention, and ROAS trends
- **Statistical Summaries**: Average metrics and performance benchmarks
- **Cohort Evolution**: Weekly progression analysis

### 4. Offerwall Chapter Analysis
- **Progression Tracking**: Chapter 1, 3, and 5 conversion rates
- **Revenue Attribution**: Chapter-specific monetization analysis
- **Completion Times**: Average days to complete analysis
- **Source Comparison**: Performance across different traffic sources

## 🎯 KPI Targets & Thresholds

### Offerwall Campaigns
```python
'offerwall': {
    'roas_d90': 1.00,        # 100% net ROAS by day 90
    'min_chapter3_cvr': 0.08, # 8% conversion to chapter 3
}
```

### Non-Offerwall Campaigns
```python
'non_offerwall': {
    'roas_d365': 1.00,        # 100% net ROAS by day 365
    'roas_d180': 0.90,        # 90% by day 180 (on track)
    'min_d7_retention': 0.15,  # 15% D7 retention
    'target_d7_retention': 0.20, # 20% D7 retention (healthy)
}
```

### Alert Thresholds
```python
'alert_thresholds': {
    'cpi_spike': 0.20,      # 20% day-over-day increase
    'volume_drop': 0.30,    # 30% day-over-day decrease
    'retention_drop': 0.10, # 10% drop in retention
    'roas_drop': 0.15,      # 15% drop in ROAS
}
```

## 🚀 Usage Examples

### CLI Interface

```bash
# Daily health check (yesterday's data)
python3 marketing_analytics_agent.py --project-id your-project --action daily

# Daily health check for specific date
python3 marketing_analytics_agent.py --project-id your-project --action daily --date 2026-02-07

# Weekly cohort analysis
python3 marketing_analytics_agent.py --project-id your-project --action weekly

# Source-specific analysis
python3 marketing_analytics_agent.py --project-id your-project --action source --source facebook

# Offerwall chapter analysis
python3 marketing_analytics_agent.py --project-id your-project --action offerwall

# Export results to JSON file
python3 marketing_analytics_agent.py --project-id your-project --action daily --output results.json
```

### Python Integration

```python
from marketing_analytics_agent import MarketingAnalyticsAgent

# Initialize agent
agent = MarketingAnalyticsAgent(project_id='your-project-id')

# Daily monitoring
health_report = agent.daily_health_check(date='2026-02-07')

# Weekly analysis
cohort_analysis = agent.weekly_cohort_analysis(week_end_date='2026-02-07')

# Source deep dive
source_report = agent.source_deep_dive(source='facebook', lookback_weeks=12)

# Offerwall analysis
chapter_report = agent.offerwall_chapter_analysis(lookback_days=45)
```

## 📋 Required BigQuery Tables

### 1. `ua_daily_summary`
```sql
CREATE TABLE analytics.ua_daily_summary (
  date DATE,
  source STRING,
  campaign_type STRING,
  installs INT64,
  spend FLOAT64,
  cpi FLOAT64
);
```

### 2. `cohort_retention`
```sql
CREATE TABLE analytics.cohort_retention (
  install_date DATE,
  source STRING,
  campaign_type STRING,
  cohort_day INT64,
  retention_rate FLOAT64
);
```

### 3. `cohort_revenue`
```sql
CREATE TABLE analytics.cohort_revenue (
  install_date DATE,
  source STRING,
  campaign_type STRING,
  cohort_day INT64,
  cumulative_arpu FLOAT64,
  ftd_rate FLOAT64
);
```

### 4. `offerwall_chapters`
```sql
CREATE TABLE analytics.offerwall_chapters (
  install_date DATE,
  source STRING,
  chapter INT64,
  users_started INT64,
  users_completed INT64,
  avg_days_to_complete FLOAT64,
  revenue_generated FLOAT64
);
```

## 📈 Output Examples

### Daily Health Check Response
```json
{
  "date": "2026-02-07",
  "overview": {
    "total_spend": 15420.50,
    "spend_change_pct": 0.12,
    "total_installs": 3240,
    "installs_change_pct": 0.08,
    "blended_cpi": 4.76
  },
  "critical_alerts": [
    {
      "severity": "high",
      "source": "google_ads",
      "issue": "CPI spiked 25.3% to $6.42",
      "recommendation": "Review bid strategy and audience targeting"
    }
  ],
  "strong_performers": [
    {
      "source": "facebook",
      "performance": "Scaled 32.1% while maintaining CPI at $4.21"
    }
  ]
}
```

### Weekly Cohort Analysis Response
```json
{
  "period": {
    "week1": "2026-01-27 to 2026-02-02",
    "week2": "2026-02-03 to 2026-02-09"
  },
  "overall_metrics": {
    "week1_roas": 0.78,
    "week2_roas": 0.82,
    "week1_retention": 0.18,
    "week2_retention": 0.19,
    "week1_cpi": 4.52,
    "week2_cpi": 4.48
  },
  "source_comparisons": [
    {
      "source": "facebook",
      "roas_change": 0.06,
      "roas_change_pct": 0.08,
      "retention_impact": 0.05,
      "monetization_impact": 0.02,
      "cost_impact": 0.01
    }
  ]
}
```

## 🔧 Configuration

### Environment Setup
```bash
# Install dependencies
pip install google-cloud-bigquery pandas numpy

# Set up BigQuery authentication
export GOOGLE_APPLICATION_CREDENTIALS="path/to/service-account.json"

# Or use gcloud authentication
gcloud auth application-default login
```

### Project Configuration
```python
# Initialize with custom dataset
agent = MarketingAnalyticsAgent(
    project_id='your-project-id',
    dataset='custom_analytics'  # Default: 'analytics'
)

# Customize targets and thresholds
agent.targets['offerwall']['roas_d90'] = 1.20  # 120% target
agent.alert_thresholds['cpi_spike'] = 0.15     # 15% threshold
```

## 🎯 Use Cases & Scenarios

### 1. Daily Operations Team
- **Morning Standup**: Review yesterday's health check
- **Performance Alerts**: Immediate notification of issues
- **Budget Allocation**: Identify strong performers for scaling

### 2. Weekly Business Review
- **Cohort Performance**: Week-over-week trend analysis
- **ROAS Attribution**: Understand performance drivers
- **Strategic Planning**: Data-driven campaign decisions

### 3. Source Optimization
- **Historical Analysis**: 8-week performance trends
- **Efficiency Tracking**: CPI vs. retention balance
- **Scaling Decisions**: Identify optimal source mix

### 4. Offerwall Strategy
- **Chapter Progression**: Optimize user journey
- **Monetization Analysis**: Revenue per chapter
- **Source Quality**: Compare traffic source performance

## 📊 Integration with Existing Tools

### Related PeerPlay Analytics Projects

This marketing analytics agent works seamlessly with other PeerPlay tools:

#### 🎯 ASO Agent Integration
- **Repository**: [merge-cruise-aso-agent](https://github.com/Omripeerplay/merge-cruise-aso-agent)
- **Integration**: Cross-reference UA performance with app store optimization metrics
- **Usage**: Correlate keyword rankings with user acquisition costs
```python
# Example: Compare ASO performance with UA metrics
aso_keywords = get_aso_performance()  # From ASO agent
ua_sources = agent.source_deep_dive('organic')  # From this agent
analyze_correlation(aso_keywords, ua_sources)
```

#### 🔍 BigQuery Analytics Executor
- **Usage**: Leverage existing BigQuery workflows for data processing
- **Integration**: Use `/get-underlying-query` skill for table insights
- **Automation**: Export results via `/export-to-gsheet` skill

#### 🎫 Support Ticket Investigator  
- **Repository**: Part of claude-code-agents ecosystem
- **Integration**: Cross-reference user behavior with support issues
- **Usage**: Correlate UA source quality with customer satisfaction

### BigQuery Workflow
```sql
-- Example data preparation query
WITH daily_metrics AS (
  SELECT 
    DATE(install_timestamp) as install_date,
    media_source as source,
    campaign_type,
    COUNT(*) as installs,
    SUM(cost) as spend,
    AVG(cost) as cpi
  FROM raw_install_events
  WHERE DATE(install_timestamp) >= CURRENT_DATE() - 30
  GROUP BY 1, 2, 3
)
INSERT INTO analytics.ua_daily_summary
SELECT * FROM daily_metrics;
```

### Automation Scripts
```python
# Daily automation example
import schedule
import time
from marketing_analytics_agent import MarketingAnalyticsAgent

def daily_health_check():
    agent = MarketingAnalyticsAgent(project_id='merge-cruise-analytics')
    report = agent.daily_health_check()
    
    # Send alerts if critical issues found
    if report['critical_alerts']:
        send_slack_alert(report['critical_alerts'])
    
    # Save to monitoring dashboard
    save_to_dashboard(report)

# Schedule daily at 9 AM
schedule.every().day.at("09:00").do(daily_health_check)

while True:
    schedule.run_pending()
    time.sleep(60)
```

### Dashboard Integration
```python
# Export for Tableau/Looker
def export_for_dashboard(date_range_days=7):
    agent = MarketingAnalyticsAgent(project_id='merge-cruise-analytics')
    
    # Collect data for date range
    reports = []
    for i in range(date_range_days):
        date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
        reports.append(agent.daily_health_check(date=date))
    
    # Convert to DataFrame for export
    df = pd.DataFrame([r['overview'] for r in reports])
    df.to_csv('dashboard_export.csv', index=False)
```

## 🚨 Monitoring & Alerting

### Critical Alert Types
1. **CPI Spikes**: >20% increase day-over-day
2. **Volume Drops**: >30% decrease in installs
3. **Retention Issues**: >10% drop in D7 retention
4. **ROAS Decline**: >15% drop in performance

### Alert Integration Examples
```python
def send_slack_alert(alerts):
    for alert in alerts:
        message = f"""
        🚨 *{alert['severity'].upper()} ALERT*
        Source: {alert['source']}
        Issue: {alert['issue']}
        Recommendation: {alert['recommendation']}
        """
        send_to_slack(message)

def send_email_report(daily_report):
    html_report = generate_html_report(daily_report)
    send_email(
        to=['marketing-team@company.com'],
        subject=f"Daily UA Report - {daily_report['date']}",
        body=html_report
    )
```

## 🔍 Advanced Analytics

### ROAS Decomposition Formula
```python
# ROAS = Revenue / Cost
# Change in ROAS = (Retention Impact) + (Monetization Impact) + (Cost Impact)

roas_change = (
    (retention_new - retention_old) / retention_old +
    (arpu_new - arpu_old) / arpu_old + 
    -(cpi_new - cpi_old) / cpi_old
)
```

### Trend Analysis Logic
```python
def analyze_trend(recent_data, historical_data):
    recent_avg = recent_data.mean()
    historical_avg = historical_data.mean()
    
    if recent_avg > historical_avg * 1.05:
        return 'improving'
    elif recent_avg < historical_avg * 0.95:
        return 'declining'
    else:
        return 'stable'
```

## 📚 Knowledge Base

### Key Metrics Definitions
- **CPI**: Cost Per Install (spend / installs)
- **ROAS**: Return on Ad Spend (revenue / spend)
- **D7 Retention**: % users active 7 days after install
- **ARPU**: Average Revenue Per User
- **CVR**: Conversion Rate (completed / started)

### Data Quality Checks
```python
def validate_data_quality(df):
    checks = {
        'no_negative_values': (df['spend'] >= 0).all(),
        'reasonable_cpi': (df['cpi'] <= 50).all(),
        'retention_bounds': ((df['retention'] >= 0) & (df['retention'] <= 1)).all(),
        'no_null_sources': df['source'].notna().all()
    }
    return checks
```

### Performance Benchmarks
- **Good CPI**: < $5.00 for most sources
- **Excellent D7 Retention**: > 25%
- **Target ROAS D365**: > 100%
- **Chapter 3 CVR**: > 10% (offerwall)

## 🔄 Maintenance & Updates

### Regular Tasks
1. **Weekly**: Review alert thresholds and targets
2. **Monthly**: Update benchmark expectations
3. **Quarterly**: Validate table schemas and data quality

### Version Control
- **Agent File**: `marketing_analytics_agent.py`
- **Documentation**: `MARKETING_ANALYTICS_DOCUMENTATION.md`
- **Git Repository**: https://github.com/dashboard (replace with actual repo)

### Future Enhancements
- [ ] Machine learning anomaly detection
- [ ] Predictive ROAS modeling
- [ ] Cross-platform attribution
- [ ] Real-time streaming analytics
- [ ] A/B testing integration

---

*Last Updated: 2026-02-08*  
*Version: 1.0.0*  
*Maintainer: PeerPlay Analytics Team*