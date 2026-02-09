
    WITH current_performance AS (
      SELECT 
        mediasource,
        platform,
        country,
        SUM(cost) as total_spend_7d,
        SUM(revenue_1d + revenue_3d + revenue_7d + revenue_14d + revenue_30d) as total_revenue_30d,
        COUNT(DISTINCT install_date) as active_days,
        SUM(cost) / COUNT(DISTINCT install_date) as avg_daily_spend,
        SUM(installs) as total_installs,
        SAFE_DIVIDE(SUM(revenue_1d + revenue_3d + revenue_7d + revenue_14d + revenue_30d), SUM(cost)) as roas_30d,
        SAFE_DIVIDE(SUM(cost), SUM(installs)) as cpi,
        SAFE_DIVIDE(SUM(revenue_1d + revenue_3d + revenue_7d + revenue_14d + revenue_30d), SUM(installs)) as ltv
      FROM `yotam-395120.peerplay.ua_cohort`
      WHERE install_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)
        AND cost > 0
        AND country NOT IN ('UA', 'IL', 'AM')  -- Exclude test countries
      GROUP BY 1, 2, 3
    ),
    scaling_potential AS (
      SELECT 
        mediasource,
        platform,
        country,
        total_spend_7d,
        total_revenue_30d,
        avg_daily_spend,
        roas_30d,
        cpi,
        ltv,
        -- Conservative scaling (50% increase)
        avg_daily_spend * 1.5 as conservative_target_spend,
        -- Aggressive scaling (100% increase) 
        avg_daily_spend * 2.0 as aggressive_target_spend,
        -- Proportional scaling for 68% total increase
        avg_daily_spend * 1.68 as proportional_target_spend,
        -- Scaling tier based on current performance
        CASE 
          WHEN roas_30d >= 1.2 AND avg_daily_spend >= 1000 THEN 'HIGH_PRIORITY'
          WHEN roas_30d >= 1.0 AND avg_daily_spend >= 500 THEN 'MEDIUM_PRIORITY'  
          WHEN roas_30d >= 0.8 AND avg_daily_spend >= 100 THEN 'LOW_PRIORITY'
          ELSE 'MONITOR_ONLY'
        END as scaling_tier
      FROM current_performance
      WHERE avg_daily_spend >= 50  -- Focus on meaningful volume
    ),
    
    -- Platform summary for scaling strategy
    platform_summary AS (
      SELECT 
        platform,
        SUM(avg_daily_spend) as total_platform_spend,
        AVG(roas_30d) as avg_platform_roas,
        COUNT(*) as num_sources,
        SUM(avg_daily_spend * 1.68) as proportional_target_platform_spend
      FROM scaling_potential
      GROUP BY 1
    ),
    
    -- Geographic summary for expansion strategy  
    geo_summary AS (
      SELECT 
        country,
        SUM(avg_daily_spend) as total_country_spend,
        AVG(roas_30d) as avg_country_roas,
        COUNT(*) as num_sources,
        SUM(avg_daily_spend * 1.68) as proportional_target_country_spend
      FROM scaling_potential
      GROUP BY 1
    ),
    
    -- Media source summary for budget allocation
    source_summary AS (
      SELECT 
        mediasource,
        SUM(avg_daily_spend) as total_source_spend,
        AVG(roas_30d) as avg_source_roas,
        COUNT(*) as num_combinations,
        SUM(avg_daily_spend * 1.68) as proportional_target_source_spend
      FROM scaling_potential
      GROUP BY 1
    )
    
    -- Main results with scaling recommendations
    SELECT 
      'DETAILED_SCALING' as analysis_type,
      scaling_tier,
      mediasource,
      platform,
      country,
      ROUND(avg_daily_spend, 2) as current_daily_spend,
      ROUND(roas_30d, 3) as current_roas,
      ROUND(cpi, 2) as current_cpi,
      ROUND(ltv, 2) as current_ltv,
      ROUND(conservative_target_spend, 2) as conservative_target,
      ROUND(aggressive_target_spend, 2) as aggressive_target,
      ROUND(proportional_target_spend, 2) as proportional_target,
      ROUND(conservative_target_spend - avg_daily_spend, 2) as additional_spend_conservative,
      ROUND(aggressive_target_spend - avg_daily_spend, 2) as additional_spend_aggressive,
      ROUND(proportional_target_spend - avg_daily_spend, 2) as additional_spend_proportional
    FROM scaling_potential
    
    UNION ALL
    
    -- Platform summary results
    SELECT 
      'PLATFORM_SUMMARY' as analysis_type,
      'SUMMARY' as scaling_tier,
      'ALL' as mediasource,
      platform,
      'ALL' as country,
      ROUND(total_platform_spend, 2) as current_daily_spend,
      ROUND(avg_platform_roas, 3) as current_roas,
      0 as current_cpi,
      0 as current_ltv,
      ROUND(total_platform_spend * 1.5, 2) as conservative_target,
      ROUND(total_platform_spend * 2.0, 2) as aggressive_target,
      ROUND(proportional_target_platform_spend, 2) as proportional_target,
      ROUND(total_platform_spend * 0.5, 2) as additional_spend_conservative,
      ROUND(total_platform_spend, 2) as additional_spend_aggressive,
      ROUND(proportional_target_platform_spend - total_platform_spend, 2) as additional_spend_proportional
    FROM platform_summary
    
    UNION ALL
    
    -- Geographic summary results  
    SELECT 
      'GEO_SUMMARY' as analysis_type,
      'SUMMARY' as scaling_tier,
      'ALL' as mediasource,
      'ALL' as platform,
      country,
      ROUND(total_country_spend, 2) as current_daily_spend,
      ROUND(avg_country_roas, 3) as current_roas,
      0 as current_cpi,
      0 as current_ltv,
      ROUND(total_country_spend * 1.5, 2) as conservative_target,
      ROUND(total_country_spend * 2.0, 2) as aggressive_target,
      ROUND(proportional_target_country_spend, 2) as proportional_target,
      ROUND(total_country_spend * 0.5, 2) as additional_spend_conservative,
      ROUND(total_country_spend, 2) as additional_spend_aggressive,
      ROUND(proportional_target_country_spend - total_country_spend, 2) as additional_spend_proportional
    FROM geo_summary
    
    UNION ALL
    
    -- Source summary results
    SELECT 
      'SOURCE_SUMMARY' as analysis_type,
      'SUMMARY' as scaling_tier,
      mediasource,
      'ALL' as platform,
      'ALL' as country,
      ROUND(total_source_spend, 2) as current_daily_spend,
      ROUND(avg_source_roas, 3) as current_roas,
      0 as current_cpi,
      0 as current_ltv,
      ROUND(total_source_spend * 1.5, 2) as conservative_target,
      ROUND(total_source_spend * 2.0, 2) as aggressive_target,
      ROUND(proportional_target_source_spend, 2) as proportional_target,
      ROUND(total_source_spend * 0.5, 2) as additional_spend_conservative,
      ROUND(total_source_spend, 2) as additional_spend_aggressive,
      ROUND(proportional_target_source_spend - total_source_spend, 2) as additional_spend_proportional
    FROM source_summary
    
    ORDER BY 
      analysis_type,
      CASE scaling_tier 
        WHEN 'HIGH_PRIORITY' THEN 1
        WHEN 'MEDIUM_PRIORITY' THEN 2  
        WHEN 'LOW_PRIORITY' THEN 3
        WHEN 'SUMMARY' THEN 4
        ELSE 5
      END,
      current_daily_spend DESC
    