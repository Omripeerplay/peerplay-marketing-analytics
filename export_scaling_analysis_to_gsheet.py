#!/usr/bin/env python3
"""
Export Revenue Scaling Analysis to Google Sheets
Creates comprehensive dashboard with all key metrics and recommendations
"""

import pandas as pd
import json
from datetime import datetime

def prepare_scaling_analysis_data():
    """Prepare all scaling analysis data for Google Sheets export"""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    
    # Executive Summary Sheet
    executive_summary = pd.DataFrame([
        {"Metric": "Current Daily Marketing Spend", "Value": "$55,230", "Status": "BASELINE"},
        {"Metric": "Current Daily D1 Revenue", "Value": "$3,611", "Status": "CRITICAL"},
        {"Metric": "Current Daily D7 Revenue", "Value": "$6,285", "Status": "CRITICAL"},
        {"Metric": "Current D1 ROAS", "Value": "0.065", "Status": "UNPROFITABLE"},
        {"Metric": "Current D7 ROAS", "Value": "0.113", "Status": "UNPROFITABLE"},
        {"Metric": "Target Daily Revenue", "Value": "$95,000", "Status": "GOAL"},
        {"Metric": "Revenue Gap", "Value": "$91,389", "Status": "CHALLENGE"},
        {"Metric": "Required ROAS for Profitability", "Value": ">1.0", "Status": "TARGET"},
        {"Metric": "Recommended Strategy", "Value": "Optimize First", "Status": "APPROACH"},
        {"Metric": "Risk Level", "Value": "HIGH", "Status": "WARNING"}
    ])
    
    # Media Source Performance Analysis
    media_sources = pd.DataFrame([
        {"Media Source": "almedia", "7D Spend": "$141,873", "D1 ROAS": "0.117", "Action": "SCALE IMMEDIATELY", "Priority": "1"},
        {"Media Source": "adjoe", "7D Spend": "$53,891", "D1 ROAS": "0.092", "Action": "OPTIMIZE THEN SCALE", "Priority": "2"},
        {"Media Source": "cashcow", "7D Spend": "$8,500", "D1 ROAS": "0.093", "Action": "OPTIMIZE THEN SCALE", "Priority": "3"},
        {"Media Source": "exmox", "7D Spend": "$11,473", "D1 ROAS": "0.062", "Action": "TEST OPTIMIZATION", "Priority": "4"},
        {"Media Source": "scrambly", "7D Spend": "$7,012", "D1 ROAS": "0.072", "Action": "TEST OPTIMIZATION", "Priority": "5"},
        {"Media Source": "applovin", "7D Spend": "$69,105", "D1 ROAS": "0.025", "Action": "PAUSE OR REDUCE", "Priority": "6"},
        {"Media Source": "facebook", "7D Spend": "$31,968", "D1 ROAS": "0.031", "Action": "PAUSE OR REDUCE", "Priority": "7"},
        {"Media Source": "prodege", "7D Spend": "$22,388", "D1 ROAS": "NO DATA", "Action": "INVESTIGATE DATA", "Priority": "8"},
        {"Media Source": "prime", "7D Spend": "$20,157", "D1 ROAS": "NO DATA", "Action": "INVESTIGATE DATA", "Priority": "9"},
        {"Media Source": "vybs", "7D Spend": "$5,001", "D1 ROAS": "NO DATA", "Action": "INVESTIGATE DATA", "Priority": "10"}
    ])
    
    # Platform Performance
    platform_performance = pd.DataFrame([
        {"Platform": "Android", "Avg Daily Spend": "$33,500", "D1 ROAS": "0.066", "Scale Potential": "LOW", "Recommendation": "Optimize First"},
        {"Platform": "Apple", "Avg Daily Spend": "$21,718", "D1 ROAS": "0.065", "Scale Potential": "LOW", "Recommendation": "Optimize First"},
        {"Platform": "Web", "Avg Daily Spend": "$17", "D1 ROAS": "NO DATA", "Scale Potential": "UNKNOWN", "Recommendation": "Investigate"},
        {"Platform": "Unknown", "Avg Daily Spend": "$5", "D1 ROAS": "NO DATA", "Scale Potential": "UNKNOWN", "Recommendation": "Fix Tracking"}
    ])
    
    # Geographic Performance
    geographic_performance = pd.DataFrame([
        {"Region": "US", "7D Total Spend": "$252,078", "D1 ROAS": "0.113", "Scale Priority": "1", "Action": "Scale Cautiously"},
        {"Region": "Tier1_English", "7D Total Spend": "$69,711", "D1 ROAS": "0.070", "Scale Priority": "2", "Action": "Optimize First"},
        {"Region": "Tier1_EU", "7D Total Spend": "$29,720", "D1 ROAS": "0.067", "Scale Priority": "3", "Action": "Optimize First"},
        {"Region": "APAC_Premium", "7D Total Spend": "$11,656", "D1 ROAS": "0.054", "Scale Priority": "4", "Action": "Pause/Reduce"},
        {"Region": "Other_International", "7D Total Spend": "$23,444", "D1 ROAS": "0.036", "Scale Priority": "5", "Action": "Pause/Reduce"}
    ])
    
    # Scaling Scenarios
    scaling_scenarios = pd.DataFrame([
        {"Scenario": "Conservative (Month 1-2)", "Target D1 ROAS": "0.150", "Daily Spend": "$82,845", "Projected Revenue": "$12,427", "Net Result": "-$70,418", "Profitable": "NO"},
        {"Scenario": "Moderate (Month 3-4)", "Target D1 ROAS": "0.250", "Daily Spend": "$110,460", "Projected Revenue": "$27,615", "Net Result": "-$82,845", "Profitable": "NO"},
        {"Scenario": "Aggressive (Month 6+)", "Target D1 ROAS": "0.500", "Daily Spend": "$165,690", "Projected Revenue": "$82,845", "Net Result": "-$82,845", "Profitable": "NO"},
        {"Scenario": "Breakeven Target", "Target D1 ROAS": "1.000", "Daily Spend": "$55,230", "Projected Revenue": "$55,230", "Net Result": "$0", "Profitable": "BREAKEVEN"},
        {"Scenario": "Profitable Target", "Target D1 ROAS": "1.500", "Daily Spend": "$55,230", "Projected Revenue": "$82,845", "Net Result": "$27,615", "Profitable": "YES"}
    ])
    
    # Action Plan
    action_plan = pd.DataFrame([
        {"Timeline": "Week 1", "Priority": "CRITICAL", "Action": "Pause applovin and facebook (lowest ROAS)", "Owner": "UA Team", "Status": "PENDING"},
        {"Timeline": "Week 1", "Priority": "CRITICAL", "Action": "Investigate data issues for sources with no ROAS", "Owner": "Analytics Team", "Status": "PENDING"},
        {"Timeline": "Week 1", "Priority": "HIGH", "Action": "Implement improved tracking and attribution", "Owner": "Tech Team", "Status": "PENDING"},
        {"Timeline": "Week 2-4", "Priority": "HIGH", "Action": "A/B test creative assets on almedia", "Owner": "Creative Team", "Status": "PENDING"},
        {"Timeline": "Week 2-4", "Priority": "HIGH", "Action": "Optimize targeting and bidding on adjoe/cashcow", "Owner": "UA Team", "Status": "PENDING"},
        {"Timeline": "Week 2-4", "Priority": "HIGH", "Action": "Implement early monetization improvements", "Owner": "Product Team", "Status": "PENDING"},
        {"Timeline": "Month 2", "Priority": "MEDIUM", "Action": "Scale almedia by 25% if ROAS >0.1", "Owner": "UA Team", "Status": "PENDING"},
        {"Timeline": "Month 2", "Priority": "MEDIUM", "Action": "Test new creative formats", "Owner": "Creative Team", "Status": "PENDING"},
        {"Timeline": "Month 3+", "Priority": "MEDIUM", "Action": "Gradually scale winning combinations", "Owner": "UA Team", "Status": "PENDING"},
        {"Timeline": "Month 3+", "Priority": "LOW", "Action": "Test new media sources", "Owner": "UA Team", "Status": "PENDING"}
    ])
    
    # Success Metrics Tracking
    success_metrics = pd.DataFrame([
        {"Metric": "D1 ROAS", "Current": "0.065", "Target": ">0.8", "Timeline": "3 months", "Frequency": "Daily"},
        {"Metric": "D7 ROAS", "Current": "0.113", "Target": ">1.5", "Timeline": "3 months", "Frequency": "Daily"},
        {"Metric": "Cost Per Install", "Current": "TBD", "Target": "Decrease 20%", "Timeline": "2 months", "Frequency": "Daily"},
        {"Metric": "D1 Retention Rate", "Current": "TBD", "Target": "Increase 15%", "Timeline": "2 months", "Frequency": "Daily"},
        {"Metric": "Early ARPU", "Current": "TBD", "Target": "Increase 25%", "Timeline": "3 months", "Frequency": "Weekly"},
        {"Metric": "LTV Prediction Accuracy", "Current": "TBD", "Target": ">85%", "Timeline": "1 month", "Frequency": "Weekly"}
    ])
    
    # Critical Insights and Warnings
    critical_insights = pd.DataFrame([
        {"Category": "CRITICAL WARNING", "Insight": "Current D1 ROAS of 0.065 means losing $0.935 per $1 spent", "Impact": "HIGH", "Action Required": "Immediate optimization needed"},
        {"Category": "SCALING RISK", "Insight": "Scaling current approach would require 2500%+ budget increase", "Impact": "HIGH", "Action Required": "DO NOT scale without ROAS improvement"},
        {"Category": "PROFITABILITY", "Insight": "Need 15x improvement in D1 ROAS to reach breakeven", "Impact": "HIGH", "Action Required": "Focus on unit economics first"},
        {"Category": "OPPORTUNITY", "Insight": "almedia shows highest ROAS at 0.117", "Impact": "MEDIUM", "Action Required": "Scale this source selectively"},
        {"Category": "DATA QUALITY", "Insight": "Multiple sources showing no ROAS data", "Impact": "MEDIUM", "Action Required": "Fix attribution tracking"},
        {"Category": "MARKET FOCUS", "Insight": "US market shows best ROAS performance", "Impact": "MEDIUM", "Action Required": "Concentrate scaling efforts on US"},
        {"Category": "TIMELINE", "Insight": "Reaching $95K revenue will take 6-12 months minimum", "Impact": "LOW", "Action Required": "Set realistic intermediate targets"}
    ])
    
    return {
        "Executive_Summary": executive_summary,
        "Media_Source_Performance": media_sources,
        "Platform_Performance": platform_performance,
        "Geographic_Performance": geographic_performance,
        "Scaling_Scenarios": scaling_scenarios,
        "Action_Plan": action_plan,
        "Success_Metrics": success_metrics,
        "Critical_Insights": critical_insights
    }

def create_dashboard_summary():
    """Create a single-sheet dashboard summary"""
    
    dashboard_data = []
    
    # Key metrics section
    dashboard_data.extend([
        ["REVENUE SCALING TO $95K DAILY - STRATEGIC ANALYSIS", "", "", ""],
        ["Analysis Date", datetime.now().strftime("%Y-%m-%d"), "", ""],
        ["", "", "", ""],
        ["CURRENT PERFORMANCE", "", "", ""],
        ["Daily Marketing Spend", "$55,230", "BASELINE", ""],
        ["Daily D1 Revenue", "$3,611", "CRITICAL - Need $91K+ more", ""],
        ["Daily D7 Revenue", "$6,285", "CRITICAL - Need $89K+ more", ""],
        ["D1 ROAS", "0.065", "UNPROFITABLE - Losing $0.935 per $1", ""],
        ["D7 ROAS", "0.113", "UNPROFITABLE - Losing $0.887 per $1", ""],
        ["", "", "", ""],
        ["CRITICAL FINDINGS", "", "", ""],
        ["Current Approach Scalable?", "NO", "Would amplify losses", ""],
        ["Recommended Strategy", "OPTIMIZE FIRST", "Improve ROAS before scaling", ""],
        ["Risk Level", "HIGH", "Scaling now = financial loss", ""],
        ["Timeline to $95K", "6-12 months", "With ROAS optimization", ""],
        ["", "", "", ""],
        ["IMMEDIATE ACTIONS (Week 1)", "", "", ""],
        ["1. Pause Low ROAS Sources", "applovin, facebook", "ROAS < 0.05", "CRITICAL"],
        ["2. Fix Data Issues", "prodege, prime, vybs", "No ROAS data", "HIGH"],
        ["3. Focus on Winners", "almedia", "Highest ROAS at 0.117", "HIGH"],
        ["", "", "", ""],
        ["SCALING TARGETS", "", "", ""],
        ["Month 1-2 Target ROAS", "0.15", "Still losing but improving", ""],
        ["Month 3-6 Target ROAS", "0.8", "Approaching breakeven", ""],
        ["Breakeven ROAS", "1.0", "No profit, no loss", ""],
        ["Profitable ROAS", "1.5+", "Sustainable scaling", ""],
        ["", "", "", ""],
        ["SUCCESS METRICS TO TRACK", "", "", ""],
        ["Daily D1 ROAS", "Target: >0.8 in 3 months", "", ""],
        ["Daily D7 ROAS", "Target: >1.5 in 3 months", "", ""],
        ["Cost Per Install by Source", "Track daily", "", ""],
        ["Early User Monetization", "D0-D1 revenue improvement", "", ""],
        ["", "", "", ""],
        ["MEDIA SOURCE PRIORITIES", "", "", ""],
        ["SCALE: almedia", "$141K spend, 0.117 ROAS", "Highest performer", ""],
        ["OPTIMIZE: adjoe, cashcow", "$62K spend, 0.09+ ROAS", "Good potential", ""],
        ["PAUSE: applovin, facebook", "$101K spend, <0.05 ROAS", "Major losses", ""],
        ["", "", "", ""],
        ["BOTTOM LINE", "", "", ""],
        ["DO NOT scale current approach", "Will lose $1M+ per day", "CRITICAL", ""],
        ["Focus on optimization first", "Achieve 0.8+ ROAS", "REQUIRED", ""],
        ["Set intermediate revenue targets", "$20K-30K daily first", "REALISTIC", ""]
    ])
    
    dashboard_df = pd.DataFrame(dashboard_data, columns=["Metric", "Value", "Notes", "Priority"])
    return dashboard_df

def main():
    """Export comprehensive scaling analysis to Google Sheets"""
    
    print("📊 PREPARING REVENUE SCALING ANALYSIS FOR GOOGLE SHEETS")
    print("=" * 60)
    
    # Prepare all data
    analysis_data = prepare_scaling_analysis_data()
    dashboard_summary = create_dashboard_summary()
    
    # Add dashboard as first sheet
    analysis_data["Dashboard_Summary"] = dashboard_summary
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    
    # Save locally first
    print("💾 SAVING DATA LOCALLY")
    for sheet_name, df in analysis_data.items():
        filename = f"scaling_analysis_{sheet_name.lower()}_{timestamp}.csv"
        df.to_csv(filename, index=False)
        print(f"   ✅ {filename}")
    
    print(f"\n📋 ANALYSIS SUMMARY")
    print(f"   📊 {len(analysis_data)} data sheets prepared")
    print(f"   🎯 Dashboard with key findings created")
    print(f"   📈 Media source, platform, and geo analysis ready")
    print(f"   ⏰ Action plan with timeline prepared")
    print(f"   📊 Success metrics tracking sheet ready")
    
    print(f"\n🚨 KEY FINDINGS TO HIGHLIGHT")
    print(f"   ❌ Current D1 ROAS of 0.065 is unprofitable")
    print(f"   ❌ Scaling now would require $1.4M+ daily spend")
    print(f"   ✅ almedia source shows best performance (0.117 ROAS)")
    print(f"   ✅ US market shows highest ROAS potential")
    print(f"   📈 Optimization-first strategy recommended")
    
    print(f"\n📊 Data ready for Google Sheets export via /export-to-gsheet skill")
    print(f"📁 Files saved with timestamp: {timestamp}")
    
    return analysis_data

if __name__ == "__main__":
    main()