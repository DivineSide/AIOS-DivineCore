"""Cold Call Dialer module.

A standalone dialing workspace: import US lead CSVs, auto-sort by time zone into
calling blocks, work one big queue, log call dispositions + notes, and schedule
follow-ups. Separate from sales_os/crm (own tables call_prospects/call_logs, own
router sales_os/web/dialer_routes.py, own page /dialer). Pang calls from OpenPhone;
this app only queues, tracks, and reminds.
"""
