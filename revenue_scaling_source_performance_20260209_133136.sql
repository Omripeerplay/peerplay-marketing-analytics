-- Revenue Scaling Analysis: Source Performance
-- Generated: 2026-02-09 13:31:36
-- Target: Scale to $95K daily revenue while maintaining ROAS


    WITH source_performance AS (
      SELECT 
        mediasource,
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
    ),
    source_totals AS (
      SELECT 
        mediasource,
        SUM(daily_spend) as total_7d_spend,
        AVG(daily_spend) as avg_daily_spend,
        AVG(d1_roas) as avg_d1_roas,
        AVG(d7_roas) as avg_d7_roas
      FROM source_performance
      GROUP BY 1
      HAVING SUM(daily_spend) > 1000  -- Focus on sources with meaningful spend
    )
    
    SELECT 
      'SOURCE_PERFORMANCE' as metric_type,
      NULL as install_date,
      avg_daily_spend as marketing_spend,
      NULL as d0_revenue,
      NULL as d1_revenue,
      NULL as d7_revenue,
      NULL as d0_roas,
      avg_d1_roas as d1_roas,
      avg_d7_roas as d7_roas,
      NULL as platform,
      NULL as country,
      mediasource,
      total_7d_spend,
      CASE 
        WHEN avg_d1_roas > 1.2 AND total_7d_spend > 5000 THEN 'HIGH_SCALE_POTENTIAL'
        WHEN avg_d1_roas > 0.8 AND total_7d_spend > 2000 THEN 'MEDIUM_SCALE_POTENTIAL'
        ELSE 'LOW_SCALE_POTENTIAL'
      END as scaling_tier
    FROM source_totals
    ORDER BY total_7d_spend DESC;
    