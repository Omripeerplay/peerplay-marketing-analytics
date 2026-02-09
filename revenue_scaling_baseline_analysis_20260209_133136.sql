-- Revenue Scaling Analysis: Baseline Analysis
-- Generated: 2026-02-09 13:31:36
-- Target: Scale to $95K daily revenue while maintaining ROAS


    WITH daily_performance AS (
      SELECT 
        install_date,
        country,
        platform,
        mediasource,
        SUM(cost) as daily_spend,
        SUM(installs) as daily_installs,
        SUM(d0_total_net_revenue) as d0_revenue,
        SUM(d1_total_net_revenue) as d1_revenue,
        SUM(d7_total_net_revenue) as d7_revenue,
        SAFE_DIVIDE(SUM(d0_total_net_revenue), SUM(cost)) as d0_roas,
        SAFE_DIVIDE(SUM(d1_total_net_revenue), SUM(cost)) as d1_roas,
        SAFE_DIVIDE(SUM(d7_total_net_revenue), SUM(cost)) as d7_roas
      FROM `yotam-395120.peerplay.ua_cohort`
      WHERE install_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
        AND install_date < CURRENT_DATE()
        AND cost > 0
        AND country NOT IN ('UA', 'IL', 'AM')
        AND currency != 'UAH'
      GROUP BY 1, 2, 3, 4
    ),
    daily_totals AS (
      SELECT 
        install_date,
        SUM(daily_spend) as total_daily_spend,
        SUM(d0_revenue) as total_d0_revenue,
        SUM(d1_revenue) as total_d1_revenue,
        SUM(d7_revenue) as total_d7_revenue,
        SAFE_DIVIDE(SUM(d0_revenue), SUM(daily_spend)) as overall_d0_roas,
        SAFE_DIVIDE(SUM(d1_revenue), SUM(daily_spend)) as overall_d1_roas,
        SAFE_DIVIDE(SUM(d7_revenue), SUM(daily_spend)) as overall_d7_roas
      FROM daily_performance
      GROUP BY 1
    )
    
    SELECT 
      'CURRENT_BASELINE' as metric_type,
      install_date,
      total_daily_spend as marketing_spend,
      total_d0_revenue as d0_revenue,
      total_d1_revenue as d1_revenue,
      total_d7_revenue as d7_revenue,
      overall_d0_roas as d0_roas,
      overall_d1_roas as d1_roas,
      overall_d7_roas as d7_roas,
      NULL as platform,
      NULL as country,
      NULL as mediasource
    FROM daily_totals
    ORDER BY install_date DESC;
    