-- Run as migration owner; create login credentials externally and grant this role.
CREATE ROLE partner_payout_runtime NOLOGIN;
GRANT USAGE ON SCHEMA public TO partner_payout_runtime;
GRANT SELECT,INSERT ON ALL TABLES IN SCHEMA public TO partner_payout_runtime;
GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO partner_payout_runtime;
GRANT UPDATE ON partners,users,payouts,payout_queue,payout_reservations,payout_webhook_events,
 webhook_endpoints,browser_sessions,rate_buckets,api_credentials,opening_reviews,correction_reviews,
 payment_workers,payout_wallets,payout_devices,payout_attempts,wallet_reservations,
 reconciliation_cases,payment_controls,execution_containment_reviews,fee_reversal_reviews TO partner_payout_runtime;
GRANT UPDATE(reserved_minor) ON ledger_accounts TO partner_payout_runtime;
GRANT DELETE ON rate_buckets TO partner_payout_runtime;
-- No ledger cache updates, history edits/deletes/TRUNCATE, schema ownership, or
-- permissions to disable triggers. SECURITY DEFINER triggers update caches.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
