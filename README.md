# PeerPlay Marketing Analytics Agent

Comprehensive User Acquisition (UA) performance analysis system for Merge Cruise mobile game with real-time monitoring, cohort tracking, and automated alerting.

## 🚀 Quick Start

```bash
# Clone the repository
git clone https://github.com/[your-username]/peerplay-marketing-analytics.git
cd peerplay-marketing-analytics

# Install dependencies
pip install -r requirements.txt

# Run daily health check
python3 marketing_analytics_agent.py --project-id your-project-id --action daily

# Weekly cohort analysis
python3 marketing_analytics_agent.py --project-id your-project-id --action weekly
```

## 📊 Features

- **Daily Health Monitoring**: Automated alerts for CPI spikes, volume drops
- **Weekly Cohort Analysis**: ROAS decomposition and trend analysis
- **Source Deep Dive**: 8-week historical performance tracking
- **Offerwall Chapter Analysis**: Progression and monetization tracking
- **BigQuery Integration**: Direct connection to your analytics warehouse
- **CLI & Python API**: Flexible usage for automation and integration

## 📚 Documentation

See [MARKETING_ANALYTICS_DOCUMENTATION.md](MARKETING_ANALYTICS_DOCUMENTATION.md) for comprehensive usage guide, API reference, and examples.

## 🔗 Related Projects

This agent integrates with other PeerPlay analytics tools:
- **ASO Agent**: [merge-cruise-aso-agent](https://github.com/Omripeerplay/merge-cruise-aso-agent) - App Store Optimization
- **BigQuery Analytics Executor**: For data processing and analysis
- **Support Ticket Investigator**: For customer issue analysis

## 🎯 KPI Targets

- **Offerwall**: 100% ROAS by D90, 8% Chapter 3 CVR
- **Non-Offerwall**: 100% ROAS by D365, 15-20% D7 retention
- **Alert Thresholds**: 20% CPI spike, 30% volume drop detection

## 🛠️ Requirements

- Python 3.8+
- Google Cloud BigQuery access
- Required BigQuery tables: `ua_daily_summary`, `cohort_retention`, `cohort_revenue`, `offerwall_chapters`

## 📋 Usage

```python
from marketing_analytics_agent import MarketingAnalyticsAgent

# Initialize
agent = MarketingAnalyticsAgent(project_id='your-project')

# Daily monitoring
health = agent.daily_health_check()

# Source analysis
report = agent.source_deep_dive('facebook')
```

## 🔧 Configuration

Set up BigQuery authentication:
```bash
export GOOGLE_APPLICATION_CREDENTIALS="path/to/service-account.json"
```

## 📈 Output Examples

Daily alerts, performance trends, and actionable insights delivered in JSON format for easy integration with dashboards and alerting systems.

---

**Maintainer**: PeerPlay Analytics Team  
**Last Updated**: 2026-02-08