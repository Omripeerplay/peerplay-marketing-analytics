-- Revenue Scaling Analysis: Scaling Calculations
-- Generated: 2026-02-09 13:31:36
-- Target: Scale to $95K daily revenue while maintaining ROAS


    WITH current_performance AS (
      SELECT 
        AVG(SUM(cost)) as avg_daily_spend,
        AVG(SUM(d1_total_net_revenue)) as avg_daily_d1_revenue,
        AVG(SUM(d7_total_net_revenue)) as avg_daily_d7_revenue,
        AVG(SAFE_DIVIDE(SUM(d1_total_net_revenue), SUM(cost))) as avg_d1_roas,
        AVG(SAFE_DIVIDE(SUM(d7_total_net_revenue), SUM(cost))) as avg_d7_roas
      FROM `yotam-395120.peerplay.ua_cohort`
      WHERE install_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
        AND install_date < CURRENT_DATE()
        AND cost > 0
        AND country NOT IN ('UA', 'IL', 'AM')
        AND currency != 'UAH'
      GROUP BY install_date
    )
    
    SELECT 
      'SCALING_REQUIREMENTS' as metric_type,
      avg_daily_spend as current_daily_spend,
      avg_daily_d1_revenue as current_daily_d1_revenue,
      avg_daily_d7_revenue as current_daily_d7_revenue,
      avg_d1_roas as current_d1_roas,
      avg_d7_roas as current_d7_roas,
      
      -- Calculate scaling requirements to reach $95K daily revenue
      CASE 
        WHEN avg_daily_d1_revenue > 0 THEN 
          ROUND((95000 - avg_daily_d1_revenue) / avg_d1_roas, 0)
        ELSE NULL 
      END as additional_spend_needed_d1,
      
      CASE 
        WHEN avg_daily_d7_revenue > 0 THEN 
          ROUND((95000 - avg_daily_d7_revenue) / avg_d7_roas, 0)
        ELSE NULL 
      END as additional_spend_needed_d7,
      
      CASE 
        WHEN avg_daily_d1_revenue > 0 THEN 
          ROUND(((95000 - avg_daily_d1_revenue) / avg_d1_roas + avg_daily_spend), 0)
        ELSE NULL 
      END as target_daily_spend_d1,
      
      CASE 
        WHEN avg_daily_d7_revenue > 0 THEN 
          ROUND(((95000 - avg_daily_d7_revenue) / avg_d7_roas + avg_daily_spend), 0)
        ELSE NULL 
      END as target_daily_spend_d7,
      
      ROUND((95000 / avg_daily_d1_revenue - 1) * 100, 1) as revenue_increase_percent_needed
      
    FROM current_performance;
    