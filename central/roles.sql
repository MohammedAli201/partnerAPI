-- Run as migrator/table owner once. Provision LOGIN credentials externally;
-- grant payout_runtime to that login. NEVER grant the owner role to the API.
CREATE ROLE payout_runtime NOLOGIN;
GRANT USAGE ON SCHEMA central TO payout_runtime;
GRANT SELECT ON ALL TABLES IN SCHEMA central TO payout_runtime;
GRANT INSERT ON ALL TABLES IN SCHEMA central TO payout_runtime;
GRANT UPDATE ON central.partners,central.controls,central.workers,central.devices,
 central.wallets,central.payouts,central.jobs,central.attempts,central.reservations,
 central.deliveries,central.cases,central.statement_items TO payout_runtime;
GRANT UPDATE(reserved_minor) ON central.accounts TO payout_runtime;
-- apply_entry is SECURITY DEFINER with a fixed search path. It alone updates
-- financial balance caches; posted-journal triggers enforce balancing at commit.
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA central FROM PUBLIC;
-- No DELETE, TRUNCATE, journal edits, financial-cache writes, or schema ownership.
