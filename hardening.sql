-- Additive migration of the EXISTING authoritative public payout tables.
ALTER TABLE partners ADD COLUMN funding_currency text NOT NULL DEFAULT 'USD' CHECK(funding_currency IN ('USD','EUR','GBP'));
ALTER TABLE partners ADD COLUMN ledger_enabled boolean NOT NULL DEFAULT false;
ALTER TABLE partners ADD COLUMN paused boolean NOT NULL DEFAULT false;
ALTER TABLE payouts ADD COLUMN canonical_hash text;
ALTER TABLE payouts ADD COLUMN status_version integer NOT NULL DEFAULT 1;
ALTER TABLE payouts ADD COLUMN hold_reason text;
ALTER TABLE payouts ADD CONSTRAINT payout_tenant_identity UNIQUE(id,partner_id);
ALTER TABLE payout_queue ADD COLUMN generation bigint NOT NULL DEFAULT 0;
ALTER TABLE payout_queue ADD COLUMN dispatch_count integer NOT NULL DEFAULT 0;
ALTER TABLE payout_queue ADD COLUMN available_at timestamptz NOT NULL DEFAULT now();
CREATE INDEX payout_ready ON payout_queue(available_at,created_at) WHERE status='PENDING';
CREATE TABLE payout_idempotency (
 partner_id integer NOT NULL, operation text NOT NULL, idempotency_key text NOT NULL CHECK(length(idempotency_key) BETWEEN 1 AND 128),
 payload_hash text NOT NULL, payout_id uuid NOT NULL, response jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(partner_id,operation,idempotency_key), FOREIGN KEY(payout_id,partner_id) REFERENCES payouts(id,partner_id)
);
CREATE TABLE payout_reference_aliases (
 partner_id integer NOT NULL, external_reference text NOT NULL, payout_id uuid NOT NULL,
 PRIMARY KEY(partner_id,external_reference), FOREIGN KEY(payout_id,partner_id) REFERENCES payouts(id,partner_id)
);
INSERT INTO payout_reference_aliases
 SELECT partner_id,lower(right(partner_tx_id,36)),min(id::text)::uuid FROM payouts
 WHERE right(partner_tx_id,36) ~* '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
 GROUP BY partner_id,lower(right(partner_tx_id,36)) HAVING count(*)=1;
ALTER TABLE balance_transactions ADD COLUMN ledger_journal_id uuid;
CREATE TABLE webhook_endpoints (
 id uuid PRIMARY KEY, partner_id integer NOT NULL REFERENCES partners(id), url text NOT NULL,
 approved_addresses text[] NOT NULL CHECK(cardinality(approved_addresses)>0), signing_secret text NOT NULL,
 version integer NOT NULL, enabled boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(partner_id,version), UNIQUE(id,partner_id)
);
CREATE UNIQUE INDEX webhook_current ON webhook_endpoints(partner_id) WHERE enabled;
ALTER TABLE payout_webhook_events ADD COLUMN partner_id integer REFERENCES partners(id);
ALTER TABLE payout_webhook_events ADD COLUMN endpoint_id uuid;
ALTER TABLE payout_webhook_events ADD COLUMN state text NOT NULL DEFAULT 'BLOCKED' CHECK(state IN ('BLOCKED','READY','LEASED','DELIVERED'));
ALTER TABLE payout_webhook_events ADD COLUMN lease_until timestamptz;
ALTER TABLE payout_webhook_events ADD COLUMN lease_owner uuid;
ALTER TABLE payout_webhook_events ADD COLUMN generation bigint NOT NULL DEFAULT 0;
ALTER TABLE payout_webhook_events ADD COLUMN status_version integer;
ALTER TABLE payout_webhook_events ADD FOREIGN KEY(endpoint_id,partner_id) REFERENCES webhook_endpoints(id,partner_id);
ALTER TABLE payout_webhook_events ADD CONSTRAINT webhook_status_identity UNIQUE(payout_id,status_version);
UPDATE payout_webhook_events e SET partner_id=p.partner_id FROM payouts p WHERE p.id=e.payout_id;
UPDATE payout_webhook_events SET state='DELIVERED' WHERE accepted_at IS NOT NULL;
-- Historical unregistered destinations remain BLOCKED, never sent with global secrets.
CREATE INDEX webhook_work ON payout_webhook_events(next_attempt_at) WHERE state IN ('READY','LEASED');
CREATE TABLE browser_sessions (
 id uuid PRIMARY KEY, user_id integer NOT NULL REFERENCES users(id), csrf_hash text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL,
 last_seen_at timestamptz NOT NULL DEFAULT now(), revoked_at timestamptz
);
CREATE INDEX browser_session_user ON browser_sessions(user_id) WHERE revoked_at IS NULL;
CREATE TABLE rate_buckets (
 identity text NOT NULL, operation text NOT NULL, bucket bigint NOT NULL,
 requests integer NOT NULL CHECK(requests>0), expires_at timestamptz NOT NULL,
 PRIMARY KEY(identity,operation,bucket)
);
CREATE TABLE api_credentials (
 id uuid PRIMARY KEY, partner_id integer NOT NULL REFERENCES partners(id), prefix text NOT NULL UNIQUE,
 verifier text NOT NULL, revoked_at timestamptz, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE ledger_accounts (
 id uuid PRIMARY KEY, business_key text NOT NULL UNIQUE, partner_id integer REFERENCES partners(id),
 currency text NOT NULL CHECK(currency IN ('USD','EUR','GBP')),
 kind text NOT NULL CHECK(kind IN ('PARTNER','BANK','WALLET','FEES','SUSPENSE','OPENING')),
 balance_minor bigint NOT NULL DEFAULT 0, reserved_minor bigint NOT NULL DEFAULT 0 CHECK(reserved_minor>=0),
 UNIQUE(id,currency), CHECK(kind<>'PARTNER' OR balance_minor>=reserved_minor)
);
CREATE UNIQUE INDEX partner_account ON ledger_accounts(partner_id,currency) WHERE kind='PARTNER';
CREATE TABLE ledger_journals (
 id uuid PRIMARY KEY, business_event_key text NOT NULL UNIQUE, currency text NOT NULL,
 payout_id uuid REFERENCES payouts(id), event_type text NOT NULL, evidence_ref text NOT NULL,
 reversal_of uuid REFERENCES ledger_journals(id), posted_at timestamptz NOT NULL DEFAULT now(),
 posting_transaction bigint NOT NULL DEFAULT txid_current(), UNIQUE(id,currency)
);
CREATE TABLE ledger_entries (
 id uuid PRIMARY KEY, journal_id uuid NOT NULL, account_id uuid NOT NULL, currency text NOT NULL,
 amount_minor bigint NOT NULL CHECK(amount_minor<>0),
 FOREIGN KEY(journal_id,currency) REFERENCES ledger_journals(id,currency),
 FOREIGN KEY(account_id,currency) REFERENCES ledger_accounts(id,currency)
);
ALTER TABLE balance_transactions ADD FOREIGN KEY(ledger_journal_id) REFERENCES ledger_journals(id);
ALTER TABLE balance_transactions ADD CONSTRAINT balance_transaction_journal UNIQUE(ledger_journal_id);
CREATE INDEX ledger_account_entries ON ledger_entries(account_id,journal_id);
CREATE TABLE opening_reviews (
 id uuid PRIMARY KEY, partner_id integer NOT NULL REFERENCES partners(id), currency text NOT NULL,
 available_minor bigint NOT NULL CHECK(available_minor>=0), reserved_minor bigint NOT NULL CHECK(reserved_minor>=0),
 evidence_ref text NOT NULL, proposer integer NOT NULL REFERENCES users(id), approver integer REFERENCES users(id),
 approved_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), CHECK(approver IS NULL OR proposer<>approver)
);
CREATE TABLE correction_reviews (
 id uuid PRIMARY KEY, partner_id integer NOT NULL REFERENCES partners(id), currency text NOT NULL,
 delta_minor bigint NOT NULL CHECK(delta_minor<>0), business_reference text NOT NULL, evidence_ref text NOT NULL,
 proposer integer NOT NULL REFERENCES users(id), approver integer REFERENCES users(id), approved_at timestamptz,
 UNIQUE(partner_id,business_reference), CHECK(approver IS NULL OR proposer<>approver)
);
CREATE TABLE payment_workers (
 id uuid PRIMARY KEY, name text NOT NULL, token_hash text NOT NULL UNIQUE, enabled boolean NOT NULL DEFAULT true,
 simulator boolean NOT NULL DEFAULT false, heartbeat_at timestamptz
);
CREATE TABLE payout_wallets (
 id uuid PRIMARY KEY, provider_account text NOT NULL UNIQUE, currency text NOT NULL,
 account_id uuid NOT NULL UNIQUE, enabled boolean NOT NULL DEFAULT true,
 observed_minor bigint NOT NULL CHECK(observed_minor>=0), observed_at timestamptz NOT NULL,
 FOREIGN KEY(account_id,currency) REFERENCES ledger_accounts(id,currency)
);
CREATE TABLE payout_devices (
 id uuid PRIMARY KEY, sim_identity text NOT NULL UNIQUE, worker_id uuid NOT NULL REFERENCES payment_workers(id),
 wallet_id uuid NOT NULL REFERENCES payout_wallets(id), provider text NOT NULL, network text NOT NULL,
 quarantined boolean NOT NULL DEFAULT true, enabled boolean NOT NULL DEFAULT true
);
CREATE TABLE payout_attempts (
 id uuid PRIMARY KEY, payout_id uuid NOT NULL REFERENCES payouts(id), attempt_number integer NOT NULL,
 worker_id uuid NOT NULL REFERENCES payment_workers(id), device_id uuid NOT NULL REFERENCES payout_devices(id),
 wallet_id uuid NOT NULL REFERENCES payout_wallets(id), generation bigint NOT NULL,
 instructions jsonb NOT NULL, instruction_hash text NOT NULL,
 phase text NOT NULL CHECK(phase IN ('CLAIMED','ARMED','UNKNOWN','SUCCESS','NOT_SENT','CANCELLED')),
 armed_at timestamptz, provider_reference text, evidence_ref text, created_at timestamptz NOT NULL DEFAULT now(),
 resolved_at timestamptz, UNIQUE(payout_id,attempt_number), CHECK((resolved_at IS NULL)=(phase IN ('CLAIMED','ARMED','UNKNOWN')))
);
CREATE UNIQUE INDEX unresolved_payout ON payout_attempts(payout_id) WHERE resolved_at IS NULL;
CREATE UNIQUE INDEX unresolved_device ON payout_attempts(device_id) WHERE resolved_at IS NULL;
CREATE UNIQUE INDEX unresolved_wallet ON payout_attempts(wallet_id) WHERE resolved_at IS NULL;
CREATE TABLE wallet_reservations (
 attempt_id uuid PRIMARY KEY REFERENCES payout_attempts(id), wallet_id uuid NOT NULL REFERENCES payout_wallets(id),
 amount_minor bigint NOT NULL CHECK(amount_minor>0), state text NOT NULL DEFAULT 'ACTIVE' CHECK(state IN ('ACTIVE','CAPTURED','RELEASED'))
);
CREATE TABLE worker_inbox (
 worker_id uuid NOT NULL REFERENCES payment_workers(id), event_id uuid NOT NULL, payload_hash text NOT NULL,
 protected_payload jsonb NOT NULL, response jsonb NOT NULL, received_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(worker_id,event_id)
);
CREATE TABLE payout_history (
 id uuid PRIMARY KEY, payout_id uuid NOT NULL REFERENCES payouts(id), version integer NOT NULL,
 old_status text, new_status text NOT NULL, actor text NOT NULL, reason text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(payout_id,version)
);
CREATE TABLE reconciliation_cases (
 id uuid PRIMARY KEY, payout_id uuid NOT NULL REFERENCES payouts(id), reason text NOT NULL,
 decision text CHECK(decision IN ('SENT','FAILED')), evidence_ref text, provider_reference text,
 proposer integer REFERENCES users(id), approver integer REFERENCES users(id), stale_stopped boolean NOT NULL DEFAULT false,
 resolved_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), CHECK(approver IS NULL OR proposer<>approver)
);
CREATE UNIQUE INDEX unresolved_case ON reconciliation_cases(payout_id) WHERE resolved_at IS NULL;
CREATE TABLE provider_receipts (
 wallet_id uuid NOT NULL REFERENCES payout_wallets(id), reference text NOT NULL,
 payout_id uuid NOT NULL UNIQUE REFERENCES payouts(id), evidence_ref text NOT NULL,
 PRIMARY KEY(wallet_id,reference)
);
CREATE TABLE payment_controls (
 scope text NOT NULL, identity text NOT NULL, paused boolean NOT NULL, reason text NOT NULL,
 PRIMARY KEY(scope,identity)
);
INSERT INTO payment_controls VALUES ('global','all',true,'Initial migration/recovery pause; inspect legacy executions');
CREATE TABLE payment_audit (
 id uuid PRIMARY KEY, actor text NOT NULL, action text NOT NULL, target text NOT NULL,
 evidence_ref text NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE FUNCTION payment_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Financial/evidence history is append only'; END $$;
CREATE TRIGGER journals_immutable BEFORE UPDATE OR DELETE ON ledger_journals FOR EACH ROW EXECUTE FUNCTION payment_immutable();
CREATE TRIGGER entries_immutable BEFORE UPDATE OR DELETE ON ledger_entries FOR EACH ROW EXECUTE FUNCTION payment_immutable();
CREATE TRIGGER history_immutable BEFORE UPDATE OR DELETE ON payout_history FOR EACH ROW EXECUTE FUNCTION payment_immutable();
CREATE TRIGGER audit_immutable BEFORE UPDATE OR DELETE ON payment_audit FOR EACH ROW EXECUTE FUNCTION payment_immutable();
CREATE TRIGGER inbox_immutable BEFORE UPDATE OR DELETE ON worker_inbox FOR EACH ROW EXECUTE FUNCTION payment_immutable();
CREATE FUNCTION payment_balanced() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE journal uuid;
BEGIN
 IF TG_TABLE_NAME='ledger_journals' THEN journal:=NEW.id; ELSE journal:=NEW.journal_id; END IF;
 IF NOT EXISTS(SELECT 1 FROM ledger_entries WHERE journal_id=journal) OR
  (SELECT COALESCE(sum(amount_minor),1) FROM ledger_entries WHERE journal_id=journal)<>0
 THEN RAISE EXCEPTION 'Unbalanced or empty journal'; END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER journals_balanced AFTER INSERT ON ledger_journals DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION payment_balanced();
CREATE CONSTRAINT TRIGGER entries_balanced AFTER INSERT ON ledger_entries DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION payment_balanced();
CREATE FUNCTION payment_projection() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
BEGIN
 IF NEW.kind='PARTNER' THEN
  UPDATE public.partners SET balance_available=(NEW.balance_minor-NEW.reserved_minor)::numeric/100,
   balance_reserved=NEW.reserved_minor::numeric/100,updated_at=now()
   WHERE id=NEW.partner_id AND ledger_enabled AND funding_currency=NEW.currency;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER account_projection AFTER UPDATE ON ledger_accounts FOR EACH ROW EXECUTE FUNCTION payment_projection();
CREATE FUNCTION payment_apply_entry() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,public AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM public.ledger_journals WHERE id=NEW.journal_id AND posting_transaction=txid_current())
 THEN RAISE EXCEPTION 'Cannot append to a posted journal'; END IF;
 UPDATE public.ledger_accounts SET balance_minor=balance_minor+CASE WHEN kind IN ('PARTNER','FEES','OPENING') THEN -NEW.amount_minor ELSE NEW.amount_minor END WHERE id=NEW.account_id;
 RETURN NEW;
END $$;
CREATE TRIGGER entry_projection BEFORE INSERT ON ledger_entries FOR EACH ROW EXECUTE FUNCTION payment_apply_entry();
CREATE FUNCTION payment_balance_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.ledger_enabled AND NOT EXISTS(SELECT 1 FROM ledger_accounts WHERE partner_id=NEW.id AND currency=NEW.funding_currency AND kind='PARTNER'
  AND (balance_minor-reserved_minor)::numeric/100=NEW.balance_available AND reserved_minor::numeric/100=NEW.balance_reserved)
 THEN RAISE EXCEPTION 'Partner balances must be ledger projections'; END IF;
 IF OLD.ledger_enabled AND (NOT NEW.ledger_enabled OR OLD.funding_currency<>NEW.funding_currency) THEN RAISE EXCEPTION 'Cannot disable financial source of truth'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER partner_balance_guard BEFORE UPDATE ON partners FOR EACH ROW EXECUTE FUNCTION payment_balance_guard();
CREATE FUNCTION payment_zero_account() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN IF NEW.balance_minor<>0 OR NEW.reserved_minor<>0 THEN RAISE EXCEPTION 'New ledger accounts must start at zero'; END IF; RETURN NEW; END $$;
CREATE TRIGGER zero_account BEFORE INSERT ON ledger_accounts FOR EACH ROW EXECUTE FUNCTION payment_zero_account();
CREATE FUNCTION payment_instruction_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF ROW(OLD.partner_id,OLD.partner_tx_id,OLD.amount,OLD.currency,OLD.recipient,OLD.provider,OLD.request_payload,OLD.canonical_hash)
  IS DISTINCT FROM ROW(NEW.partner_id,NEW.partner_tx_id,NEW.amount,NEW.currency,NEW.recipient,NEW.provider,NEW.request_payload,NEW.canonical_hash)
 THEN RAISE EXCEPTION 'Payout instructions are immutable'; END IF;
 IF OLD.status IN ('SENT','FAILED','REJECTED','CANCELLED') AND NEW.status<>OLD.status THEN RAISE EXCEPTION 'Final status cannot regress'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER immutable_payout_instructions BEFORE UPDATE ON payouts FOR EACH ROW EXECUTE FUNCTION payment_instruction_guard();
-- Preserve all legacy executions, conservatively quarantine risk; never reclaim them.
UPDATE payouts p SET status='UNKNOWN',hold_reason='Legacy execution needs reconciliation'
 WHERE status='PROCESSING' OR EXISTS(SELECT 1 FROM payout_queue q WHERE q.payout_id=p.id AND q.status='IN_PROGRESS');
UPDATE payout_queue SET status='HELD' WHERE payout_id IN (SELECT id FROM payouts WHERE status='UNKNOWN');
UPDATE payout_queue SET status='HELD' WHERE payout_id IN (SELECT id FROM payouts WHERE canonical_hash IS NULL AND status='RECEIVED');
INSERT INTO reconciliation_cases(id,payout_id,reason)
 SELECT md5('legacy-case:'||id::text)::uuid,id,'Legacy execution has no durable submission boundary' FROM payouts WHERE status='UNKNOWN';
-- Preserve possible legacy anomalies for review while fencing every new write.
ALTER TABLE payout_reservations ADD CONSTRAINT reservation_tenant
 FOREIGN KEY(payout_id,partner_id) REFERENCES payouts(id,partner_id) NOT VALID;
CREATE FUNCTION payment_attempt_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF ROW(OLD.payout_id,OLD.attempt_number,OLD.worker_id,OLD.device_id,OLD.wallet_id,OLD.generation,OLD.instructions,OLD.instruction_hash)
 IS DISTINCT FROM ROW(NEW.payout_id,NEW.attempt_number,NEW.worker_id,NEW.device_id,NEW.wallet_id,NEW.generation,NEW.instructions,NEW.instruction_hash)
 THEN RAISE EXCEPTION 'Execution commands are immutable'; END IF;
 IF OLD.resolved_at IS NOT NULL AND NEW IS DISTINCT FROM OLD
 THEN RAISE EXCEPTION 'Resolved attempts are immutable'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER immutable_execution_command BEFORE UPDATE ON payout_attempts FOR EACH ROW EXECUTE FUNCTION payment_attempt_guard();
CREATE FUNCTION payment_settlement_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF OLD.status IS DISTINCT FROM NEW.status AND NEW.canonical_hash IS NOT NULL THEN
  IF NEW.status_version<>OLD.status_version+1 OR NOT EXISTS(
   SELECT 1 FROM payout_history WHERE payout_id=NEW.id AND version=NEW.status_version AND new_status=NEW.status)
  THEN RAISE EXCEPTION 'Status transition requires matching durable history'; END IF;
  IF NEW.status='SENT' AND (
   NOT EXISTS(SELECT 1 FROM ledger_journals WHERE payout_id=NEW.id AND event_type='PAYOUT') OR
   NOT EXISTS(SELECT 1 FROM provider_receipts WHERE payout_id=NEW.id) OR
   NOT EXISTS(SELECT 1 FROM payout_reservations WHERE payout_id=NEW.id AND status='CAPTURED') OR
   NOT EXISTS(SELECT 1 FROM payout_webhook_events WHERE payout_id=NEW.id AND status_version=NEW.status_version))
  THEN RAISE EXCEPTION 'Settlement requires journal, receipt, capture and outbox'; END IF;
 END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER atomic_settlement AFTER UPDATE ON payouts DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION payment_settlement_guard();
