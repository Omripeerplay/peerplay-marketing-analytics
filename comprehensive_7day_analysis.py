#!/usr/bin/env python3
"""
Comprehensive 7-Day Marketing Performance Analysis
Tests the marketing analytics agent with full source, platform, and campaign analysis
"""

import sys
import os
sys.path.append('/Users/omrikapitulnik/peerplay-marketing-analytics')

from marketing_analytics_agent import MarketingAnalyticsAgent
from datetime import datetime, timedelta
import json
import pandas as pd
from typing import Dict, List

class Comprehensive7DayAnalysis:
    def __init__(self, project_id: str):
        """Initialize comprehensive analysis"""
        self.agent = MarketingAnalyticsAgent(project_id=project_id, dataset='peerplay')
        self.project_id = project_id
        
        # Analysis period - last 7 days
        self.end_date = datetime.now().date()
        self.start_date = self.end_date - timedelta(days=7)
        
        # Results storage
        self.results = {
            'analysis_period': {
                'start_date': str(self.start_date),
                'end_date': str(self.end_date),
                'generated_at': datetime.now().isoformat()
            },
            'daily_health_checks': [],
            'weekly_cohort_analysis': {},
            'source_deep_dives': {},
            'offerwall_analysis': {},
            'executive_summary': {},
            'action_items': []
        }
    
    def run_comprehensive_analysis(self) -> Dict:
        """Execute full 7-day analysis"""
        print("🚀 Starting Comprehensive 7-Day Marketing Performance Analysis")
        print(f"📅 Period: {self.start_date} to {self.end_date}")
        
        # 1. Daily Health Checks
        print("\n📊 Running Daily Health Checks...")
        self._run_daily_health_checks()
        
        # 2. Weekly Cohort Analysis
        print("\n📈 Executing Weekly Cohort Analysis...")
        self._run_weekly_cohort_analysis()
        
        # 3. Source Deep Dives
        print("\n🔍 Analyzing Top Sources...")
        self._run_source_deep_dives()
        
        # 4. Offerwall Chapter Analysis
        print("\n🎯 Offerwall Chapter Analysis...")
        self._run_offerwall_analysis()
        
        # 5. Generate Executive Summary
        print("\n📋 Generating Executive Summary...")
        self._generate_executive_summary()
        
        # 6. Create Action Items
        print("\n⚡ Creating Action Items...")
        self._generate_action_items()
        
        print("\n✅ Analysis Complete!")
        return self.results
    
    def _run_daily_health_checks(self):
        """Run health checks for each of the last 7 days"""
        for i in range(7):
            check_date = self.end_date - timedelta(days=i+1)
            try:
                daily_report = self.agent.daily_health_check(date=str(check_date))
                self.results['daily_health_checks'].append(daily_report)
                print(f"  ✓ {check_date}: {len(daily_report.get('critical_alerts', []))} alerts")
            except Exception as e:
                print(f"  ⚠️ {check_date}: Error - {str(e)}")
    
    def _run_weekly_cohort_analysis(self):
        """Execute weekly cohort comparison"""
        try:
            cohort_analysis = self.agent.weekly_cohort_analysis(week_end_date=str(self.end_date))
            self.results['weekly_cohort_analysis'] = cohort_analysis
            
            overall = cohort_analysis.get('overall_metrics', {})
            print(f"  ✓ Week 1 ROAS: {overall.get('week1_roas', 0):.3f}")
            print(f"  ✓ Week 2 ROAS: {overall.get('week2_roas', 0):.3f}")
            print(f"  ✓ ROAS Change: {((overall.get('week2_roas', 0) - overall.get('week1_roas', 0)) / overall.get('week1_roas', 1) * 100):.1f}%")
        except Exception as e:
            print(f"  ⚠️ Weekly cohort analysis failed: {str(e)}")
    
    def _run_source_deep_dives(self):
        """Analyze top performing sources in detail"""
        # Get top sources from daily health checks
        top_sources = self._identify_top_sources()
        
        for source in top_sources:
            try:
                source_analysis = self.agent.source_deep_dive(source=source, lookback_weeks=4)
                self.results['source_deep_dives'][source] = source_analysis
                
                current = source_analysis.get('current_week', {})
                print(f"  ✓ {source}: CPI ${current.get('cpi', 0):.2f}, D7 Retention {current.get('d7_retention', 0)*100:.1f}%")
            except Exception as e:
                print(f"  ⚠️ {source}: Analysis failed - {str(e)}")
    
    def _run_offerwall_analysis(self):
        """Analyze offerwall chapter progression"""
        try:
            offerwall_analysis = self.agent.offerwall_chapter_analysis(lookback_days=7)
            self.results['offerwall_analysis'] = offerwall_analysis
            
            sources_count = len(offerwall_analysis.get('by_source', {}))
            print(f"  ✓ Analyzed {sources_count} offerwall sources")
        except Exception as e:
            print(f"  ⚠️ Offerwall analysis failed: {str(e)}")
    
    def _identify_top_sources(self) -> List[str]:
        """Identify top sources from daily health checks"""
        source_performance = {}
        
        for daily_report in self.results['daily_health_checks']:
            for source_detail in daily_report.get('source_details', []):
                source = source_detail.get('source')
                if source:
                    if source not in source_performance:
                        source_performance[source] = {'total_installs': 0, 'total_spend': 0}
                    
                    source_performance[source]['total_installs'] += source_detail.get('current_installs', 0)
                    source_performance[source]['total_spend'] += source_detail.get('current_spend', 0)
        
        # Sort by total installs and return top 5
        top_sources = sorted(source_performance.items(), key=lambda x: x[1]['total_installs'], reverse=True)
        return [source[0] for source in top_sources[:5]]
    
    def _generate_executive_summary(self):
        """Create executive summary from all analyses"""
        summary = {
            'period_overview': self._summarize_period(),
            'performance_highlights': self._identify_highlights(),
            'critical_issues': self._identify_critical_issues(),
            'top_opportunities': self._identify_opportunities()
        }
        
        self.results['executive_summary'] = summary
    
    def _summarize_period(self) -> Dict:
        """Summarize overall period performance"""
        total_spend = 0
        total_installs = 0
        total_alerts = 0
        
        for daily_report in self.results['daily_health_checks']:
            overview = daily_report.get('overview', {})
            total_spend += overview.get('total_spend', 0)
            total_installs += overview.get('total_installs', 0)
            total_alerts += len(daily_report.get('critical_alerts', []))
        
        avg_cpi = total_spend / total_installs if total_installs > 0 else 0
        
        return {
            'total_spend': total_spend,
            'total_installs': total_installs,
            'average_cpi': avg_cpi,
            'total_alerts': total_alerts,
            'daily_avg_spend': total_spend / 7,
            'daily_avg_installs': total_installs / 7
        }
    
    def _identify_highlights(self) -> List[Dict]:
        """Identify top performing aspects"""
        highlights = []
        
        # Strong performers from daily reports
        for daily_report in self.results['daily_health_checks']:
            for performer in daily_report.get('strong_performers', []):
                highlights.append({
                    'type': 'strong_performer',
                    'date': daily_report.get('date'),
                    'source': performer.get('source'),
                    'performance': performer.get('performance')
                })
        
        # ROAS improvements from cohort analysis
        cohort = self.results.get('weekly_cohort_analysis', {})
        overall = cohort.get('overall_metrics', {})
        if overall.get('week2_roas', 0) > overall.get('week1_roas', 0):
            highlights.append({
                'type': 'roas_improvement',
                'improvement': ((overall.get('week2_roas', 0) - overall.get('week1_roas', 0)) / overall.get('week1_roas', 1) * 100),
                'week1_roas': overall.get('week1_roas', 0),
                'week2_roas': overall.get('week2_roas', 0)
            })
        
        return highlights[:10]  # Top 10 highlights
    
    def _identify_critical_issues(self) -> List[Dict]:
        """Identify critical issues requiring immediate attention"""
        issues = []
        
        # Collect all critical alerts
        for daily_report in self.results['daily_health_checks']:
            for alert in daily_report.get('critical_alerts', []):
                issues.append({
                    'date': daily_report.get('date'),
                    'severity': alert.get('severity'),
                    'source': alert.get('source'),
                    'issue': alert.get('issue'),
                    'recommendation': alert.get('recommendation')
                })
        
        # Add declining trends from source analysis
        for source, analysis in self.results.get('source_deep_dives', {}).items():
            trends = analysis.get('trends', {})
            declining_metrics = [k for k, v in trends.items() if 'declining' in str(v)]
            if declining_metrics:
                issues.append({
                    'type': 'declining_trend',
                    'source': source,
                    'declining_metrics': declining_metrics,
                    'recommendation': f"Investigate {source} performance decline"
                })
        
        return issues
    
    def _identify_opportunities(self) -> List[Dict]:
        """Identify scaling and optimization opportunities"""
        opportunities = []
        
        # High-performing sources for scaling
        for source, analysis in self.results.get('source_deep_dives', {}).items():
            current = analysis.get('current_week', {})
            trends = analysis.get('trends', {})
            
            if (current.get('d7_roas', 0) > 0.8 and 
                trends.get('roas_trend') == 'improving' and
                current.get('cpi', 100) < 6.0):
                opportunities.append({
                    'type': 'scale_opportunity',
                    'source': source,
                    'current_roas': current.get('d7_roas', 0),
                    'current_cpi': current.get('cpi', 0),
                    'recommendation': f"Scale {source} - strong ROAS with improving trend"
                })
        
        # Offerwall optimization opportunities
        offerwall = self.results.get('offerwall_analysis', {})
        for source, metrics in offerwall.get('by_source', {}).items():
            if metrics.get('chapter_3_cvr', 0) < 0.08:  # Below 8% target
                opportunities.append({
                    'type': 'offerwall_optimization',
                    'source': source,
                    'chapter_3_cvr': metrics.get('chapter_3_cvr', 0),
                    'recommendation': f"Optimize {source} chapter progression - CVR below target"
                })
        
        return opportunities[:10]  # Top 10 opportunities
    
    def _generate_action_items(self):
        """Generate prioritized action items"""
        action_items = []
        
        # High priority - Critical alerts
        critical_issues = self.results['executive_summary']['critical_issues']
        for issue in critical_issues[:5]:  # Top 5 critical
            action_items.append({
                'priority': 'HIGH',
                'category': 'Critical Issue',
                'action': issue.get('recommendation', 'Address critical issue'),
                'source': issue.get('source'),
                'timeline': 'Immediate',
                'details': issue
            })
        
        # Medium priority - Scaling opportunities
        opportunities = self.results['executive_summary']['top_opportunities']
        scale_opps = [opp for opp in opportunities if opp.get('type') == 'scale_opportunity']
        for opp in scale_opps[:3]:  # Top 3 scaling
            action_items.append({
                'priority': 'MEDIUM',
                'category': 'Scaling Opportunity',
                'action': f"Increase budget allocation for {opp.get('source')}",
                'source': opp.get('source'),
                'timeline': 'This week',
                'details': opp
            })
        
        # Low priority - Optimization opportunities
        optimization_opps = [opp for opp in opportunities if opp.get('type') == 'offerwall_optimization']
        for opp in optimization_opps[:3]:  # Top 3 optimizations
            action_items.append({
                'priority': 'LOW',
                'category': 'Optimization',
                'action': f"Optimize chapter progression for {opp.get('source')}",
                'source': opp.get('source'),
                'timeline': 'Next 2 weeks',
                'details': opp
            })
        
        self.results['action_items'] = action_items
    
    def export_results(self, filename: str = None):
        """Export results to JSON file"""
        if filename is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filename = f"7day_marketing_analysis_{timestamp}.json"
        
        filepath = f"/Users/omrikapitulnik/peerplay-marketing-analytics/{filename}"
        with open(filepath, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        
        print(f"📄 Results exported to: {filepath}")
        return filepath
    
    def print_executive_summary(self):
        """Print formatted executive summary"""
        print("\n" + "="*60)
        print("📊 EXECUTIVE SUMMARY - 7-DAY MARKETING PERFORMANCE")
        print("="*60)
        
        # Period Overview
        overview = self.results['executive_summary']['period_overview']
        print(f"\n📈 PERIOD OVERVIEW ({self.start_date} to {self.end_date})")
        print(f"Total Spend: ${overview['total_spend']:,.2f}")
        print(f"Total Installs: {overview['total_installs']:,}")
        print(f"Average CPI: ${overview['average_cpi']:.2f}")
        print(f"Critical Alerts: {overview['total_alerts']}")
        print(f"Daily Avg Spend: ${overview['daily_avg_spend']:,.2f}")
        print(f"Daily Avg Installs: {overview['daily_avg_installs']:,.0f}")
        
        # Critical Issues
        issues = self.results['executive_summary']['critical_issues']
        if issues:
            print(f"\n🚨 CRITICAL ISSUES ({len(issues)})")
            for i, issue in enumerate(issues[:3], 1):
                print(f"{i}. {issue.get('source', 'Unknown')}: {issue.get('issue', 'N/A')}")
        
        # Top Opportunities
        opportunities = self.results['executive_summary']['top_opportunities']
        if opportunities:
            print(f"\n🚀 TOP OPPORTUNITIES ({len(opportunities)})")
            for i, opp in enumerate(opportunities[:3], 1):
                if opp.get('type') == 'scale_opportunity':
                    print(f"{i}. Scale {opp.get('source')}: ROAS {opp.get('current_roas', 0):.3f}, CPI ${opp.get('current_cpi', 0):.2f}")
                else:
                    print(f"{i}. {opp.get('recommendation', 'N/A')}")
        
        # Action Items
        actions = self.results['action_items']
        if actions:
            print(f"\n⚡ ACTION ITEMS ({len(actions)})")
            for i, action in enumerate(actions[:5], 1):
                print(f"{i}. [{action['priority']}] {action['action']} ({action['timeline']})")
        
        print("\n" + "="*60)

def main():
    """Main execution function"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Comprehensive 7-Day Marketing Analysis')
    parser.add_argument('--project-id', required=True, help='BigQuery project ID')
    parser.add_argument('--export', help='Export filename (optional)')
    
    args = parser.parse_args()
    
    # Run comprehensive analysis
    analyzer = Comprehensive7DayAnalysis(project_id=args.project_id)
    results = analyzer.run_comprehensive_analysis()
    
    # Print executive summary
    analyzer.print_executive_summary()
    
    # Export results
    export_file = analyzer.export_results(filename=args.export)
    
    print(f"\n🎯 Analysis complete! Results saved to: {export_file}")
    
    return results

if __name__ == '__main__':
    main()