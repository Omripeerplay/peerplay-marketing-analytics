#!/usr/bin/env python3
"""
Check ua_cohort table schema to fix currency field issue
"""

from google.cloud import bigquery

def check_table_schema():
    """Check the schema of ua_cohort table"""
    
    try:
        client = bigquery.Client()
        
        # Get table schema
        table_ref = client.dataset('peerplay', project='yotam-395120').table('ua_cohort')
        table = client.get_table(table_ref)
        
        print("🔍 UA_COHORT TABLE SCHEMA")
        print("=" * 50)
        
        for field in table.schema:
            print(f"   {field.name}: {field.field_type}")
        
        # Check for currency-related fields
        currency_fields = [field.name for field in table.schema if 'currency' in field.name.lower()]
        print(f"\n💰 CURRENCY-RELATED FIELDS: {currency_fields}")
        
        # Sample data query to understand structure
        sample_query = """
        SELECT *
        FROM `yotam-395120.peerplay.ua_cohort`
        WHERE cost > 0
        LIMIT 5
        """
        
        print(f"\n📊 SAMPLE DATA")
        df = client.query(sample_query).to_dataframe()
        print(df.columns.tolist())
        print(df.head())
        
        return table.schema
        
    except Exception as e:
        print(f"❌ Error checking schema: {e}")
        return None

if __name__ == "__main__":
    check_table_schema()