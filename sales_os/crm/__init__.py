"""CRM + KPI persistence for the positive-reply pipeline dashboard (/crm).

Thin PostgREST layer over two Supabase tables (`crm_prospects`, `kpi_daily`),
same auth pattern as sales_os/integrations/instantly/supabase_writer.
"""
