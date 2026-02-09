-- Revenue Scaling Analysis: Platform Breakdown
-- Generated: 2026-02-09 13:31:36
-- Target: Scale to $95K daily revenue while maintaining ROAS


    WITH platform_performance AS (
      SELECT 
        platform,
        install_date,
        SUM(cost) as daily_spend,
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
      GROUP BY 1, 2
    )
    
    SELECT 
      'PLATFORM_PERFORMANCE' as metric_type,
      install_date,
      daily_spend as marketing_spend,
      d0_revenue,
      d1_revenue,
      d7_revenue,
      d0_roas,
      d1_roas,
      d7_roas,
      platform,
      NULL as country,
      NULL as mediasource
    FROM platform_performance
    ORDER BY install_date DESC, daily_spend DESC;
    