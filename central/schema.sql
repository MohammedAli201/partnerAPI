-- PostgreSQL 18. Never import legacy balances without reconciling them first.
CREATE SCHEMA central;
CREATE TABLE central.partners (
 id uuid PRIMARY KEY, name text NOT NULL, paused boolean NOT NULL DEFAULT false,
 corridors text[] NOT NULL, fee_minor bigint NOT NULL DEFAULT 60 CHECK(fee_minor >= 0),
 webhook_url text, webhook_secret text, destination_version integer NOT NULL DEFAULT 1,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE central.credentials (
 id uuid PRIMARY KEY, partner_id uuid REFERENCES central.partners(id), worker_id uuid,
 token_hash text NOT NULL UNIQUE, role text NOT NULL CHECK(role IN ('partner','worker','reviewer','admin')),
 revoked_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(),
 CHECK((role='partner') = (partner_id IS NOT NULL)), CHECK((role='worker') = (worker_id IS NOT NULL))
);
CREATE TABLE central.controls (
 scope text NOT NULL, identity text NOT NULL, paused boolean NOT NULL DEFAULT true,
 reason text NOT NULL, PRIMARY KEY(scope,identity)
);
INSERT INTO central.controls VALUES ('global','all',true,'Initial/recovery pause: reconcile before enabling');
CREATE TABLE central.workers (
 id uuid PRIMARY KEY, name text NOT NULL, enabled boolean NOT NULL DEFAULT true,
 heartbeat_at timestamptz NOT NULL DEFAULT now(), simulator boolean NOT NULL DEFAULT false
);
ALTER TABLE central.credentials ADD FOREIGN KEY(worker_id) REFERENCES central.workers(id);
CREATE TABLE central.accounts (
 id uuid PRIMARY KEY, business_key text NOT NULL UNIQUE, kind text NOT NULL CHECK(kind IN ('BANK','PARTNER_PAYABLE','WALLET_ASSET','FEES','SUSPENSE')),
 currency text NOT NULL CHECK(currency IN ('USD','EUR','GBP')), partner_id uuid REFERENCES central.partners(id),
 balance_minor bigint NOT NULL DEFAULT 0, reserved_minor bigint NOT NULL DEFAULT 0 CHECK(reserved_minor>=0),
 spendable boolean NOT NULL DEFAULT false,
 UNIQUE(id,currency), UNIQUE(id,partner_id,currency),
 CHECK(kind<>'PARTNER_PAYABLE' OR balance_minor>=reserved_minor)
);
CREATE TABLE central.wallets (
 id uuid PRIMARY KEY, provider text NOT NULL, provider_account_reference text NOT NULL,
 currency text NOT NULL, account_id uuid NOT NULL UNIQUE, enabled boolean NOT NULL DEFAULT true,
 observed_minor bigint, observed_at timestamptz, daily_limit_minor bigint NOT NULL CHECK(daily_limit_minor>0),
 max_payout_minor bigint NOT NULL CHECK(max_payout_minor>0),
 FOREIGN KEY(account_id,currency) REFERENCES central.accounts(id,currency),
 UNIQUE(provider,provider_account_reference), UNIQUE(id,currency)
);
CREATE TABLE central.devices (
 id uuid PRIMARY KEY, sim_identity text NOT NULL UNIQUE, worker_id uuid NOT NULL REFERENCES central.workers(id),
 wallet_id uuid NOT NULL REFERENCES central.wallets(id), networks text[] NOT NULL,
 quarantined boolean NOT NULL DEFAULT false, enabled boolean NOT NULL DEFAULT true
);
CREATE TABLE central.payouts (
 id uuid PRIMARY KEY, partner_id uuid NOT NULL REFERENCES central.partners(id),
 external_reference text NOT NULL CHECK(length(external_reference) BETWEEN 1 AND 128),
 canonical_hash text NOT NULL CHECK(canonical_hash ~ '^[0-9a-f]{64}$'), hash_version integer NOT NULL DEFAULT 1 CHECK(hash_version=1),
 amount_minor bigint NOT NULL CHECK(amount_minor>0), fee_minor bigint NOT NULL CHECK(fee_minor>=0),
 currency text NOT NULL CHECK(currency IN ('USD','EUR','GBP')), recipient text NOT NULL CHECK(recipient ~ '^\+[1-9][0-9]{7,14}$'),
 network text NOT NULL CHECK(length(network) BETWEEN 1 AND 64), corridor text NOT NULL CHECK(corridor IN ('EU-SO','GB-SO','US-SO')),
 status text NOT NULL CHECK(status IN ('QUEUED','CLAIMED','ARMED','PAID','FAILED','UNKNOWN','CANCELLED','ON_HOLD')),
 status_version integer NOT NULL DEFAULT 1 CHECK(status_version>0), hold_reason text,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(partner_id,external_reference), UNIQUE(id,partner_id), UNIQUE(id,partner_id,currency)
);
CREATE INDEX payouts_partner_status ON central.payouts(partner_id,status,created_at);
CREATE TABLE central.api_idempotency (
 partner_id uuid NOT NULL, operation text NOT NULL, idempotency_key text NOT NULL CHECK(length(idempotency_key) BETWEEN 1 AND 128 AND idempotency_key=btrim(idempotency_key)),
 request_hash text NOT NULL, payout_id uuid NOT NULL, response jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(partner_id,operation,idempotency_key),
 FOREIGN KEY(payout_id,partner_id) REFERENCES central.payouts(id,partner_id)
);
CREATE TABLE central.jobs (
 payout_id uuid PRIMARY KEY REFERENCES central.payouts(id),
 state text NOT NULL CHECK(state IN ('READY','LEASED','HELD','DONE')), priority integer NOT NULL DEFAULT 0,
 available_at timestamptz NOT NULL DEFAULT now(), lease_owner uuid REFERENCES central.workers(id),
 lease_until timestamptz, generation bigint NOT NULL DEFAULT 0 CHECK(generation>=0),
 dispatch_count integer NOT NULL DEFAULT 0 CHECK(dispatch_count>=0), created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX jobs_ready ON central.jobs(priority DESC,available_at,created_at) WHERE state='READY';
CREATE INDEX jobs_expired ON central.jobs(lease_until) WHERE state='LEASED';
CREATE TABLE central.attempts (
 id uuid PRIMARY KEY, payout_id uuid NOT NULL REFERENCES central.payouts(id),
 attempt_number integer NOT NULL CHECK(attempt_number>0), worker_id uuid NOT NULL REFERENCES central.workers(id),
 device_id uuid NOT NULL REFERENCES central.devices(id), wallet_id uuid NOT NULL REFERENCES central.wallets(id),
 generation bigint NOT NULL CHECK(generation>0), instruction_hash text NOT NULL, instructions jsonb NOT NULL,
 phase text NOT NULL CHECK(phase IN ('CLAIMED','ARMED','UNKNOWN','SUCCEEDED','NOT_SENT','CANCELLED')),
 armed_at timestamptz, may_have_submitted_at timestamptz, provider_reference text, evidence_ref text,
 created_at timestamptz NOT NULL DEFAULT now(), resolved_at timestamptz,
 UNIQUE(payout_id,attempt_number), UNIQUE(id,payout_id),
 CHECK((phase IN ('CLAIMED','ARMED','UNKNOWN'))=(resolved_at IS NULL))
);
CREATE UNIQUE INDEX attempt_unresolved ON central.attempts(payout_id) WHERE resolved_at IS NULL;
CREATE UNIQUE INDEX device_unresolved ON central.attempts(device_id) WHERE resolved_at IS NULL;
CREATE UNIQUE INDEX wallet_unresolved ON central.attempts(wallet_id) WHERE resolved_at IS NULL;
CREATE TABLE central.reservations (
 id uuid PRIMARY KEY, payout_id uuid NOT NULL, partner_id uuid NOT NULL, currency text NOT NULL,
 kind text NOT NULL CHECK(kind IN ('PARTNER','WALLET')), account_id uuid NOT NULL,
 amount_minor bigint NOT NULL CHECK(amount_minor>0), state text NOT NULL DEFAULT 'ACTIVE' CHECK(state IN ('ACTIVE','CAPTURED','RELEASED')),
 created_at timestamptz NOT NULL DEFAULT now(), resolved_at timestamptz,
 FOREIGN KEY(payout_id,partner_id,currency) REFERENCES central.payouts(id,partner_id,currency),
 FOREIGN KEY(account_id,currency) REFERENCES central.accounts(id,currency)
);
CREATE UNIQUE INDEX reservation_active ON central.reservations(payout_id,kind) WHERE state='ACTIVE';
CREATE TABLE central.journals (
 id uuid PRIMARY KEY, business_event_key text NOT NULL UNIQUE, event_type text NOT NULL,
 payout_id uuid REFERENCES central.payouts(id), evidence_ref text NOT NULL,
 reversal_of uuid REFERENCES central.journals(id), posted_at timestamptz NOT NULL DEFAULT now(),
 posting_transaction bigint NOT NULL DEFAULT txid_current()
);
CREATE TABLE central.entries (
 id uuid PRIMARY KEY, journal_id uuid NOT NULL REFERENCES central.journals(id),
 account_id uuid NOT NULL, currency text NOT NULL, amount_minor bigint NOT NULL CHECK(amount_minor<>0),
 FOREIGN KEY(account_id,currency) REFERENCES central.accounts(id,currency)
);
CREATE INDEX entries_account ON central.entries(account_id,journal_id);
CREATE FUNCTION central.empty_account() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.balance_minor<>0 OR NEW.reserved_minor<>0 THEN RAISE EXCEPTION 'New accounts start at zero; use ledger posting'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER account_zero BEFORE INSERT ON central.accounts FOR EACH ROW EXECUTE FUNCTION central.empty_account();
CREATE FUNCTION central.apply_entry() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog,central AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM central.journals WHERE id=NEW.journal_id AND posting_transaction=txid_current())
 THEN RAISE EXCEPTION 'Cannot append to a previously posted journal'; END IF;
 UPDATE central.accounts SET balance_minor=balance_minor+
   CASE WHEN kind IN ('PARTNER_PAYABLE','FEES') THEN -NEW.amount_minor ELSE NEW.amount_minor END
   WHERE id=NEW.account_id;
 RETURN NEW;
END $$;
CREATE TRIGGER entry_cache BEFORE INSERT ON central.entries FOR EACH ROW EXECUTE FUNCTION central.apply_entry();
CREATE FUNCTION central.check_reservation_owner() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NEW.kind='PARTNER' AND NOT EXISTS(SELECT 1 FROM central.accounts WHERE id=NEW.account_id AND partner_id=NEW.partner_id AND kind='PARTNER_PAYABLE')
 THEN RAISE EXCEPTION 'Reservation belongs to another partner'; END IF;
 IF NEW.kind='WALLET' AND NOT EXISTS(SELECT 1 FROM central.wallets WHERE account_id=NEW.account_id)
 THEN RAISE EXCEPTION 'Wallet reservation requires wallet asset account'; END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER reservation_owner BEFORE INSERT ON central.reservations FOR EACH ROW EXECUTE FUNCTION central.check_reservation_owner();
CREATE FUNCTION central.immutable_instructions() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_TABLE_NAME='payouts' THEN
  IF ROW(OLD.partner_id,OLD.external_reference,OLD.canonical_hash,OLD.amount_minor,OLD.fee_minor,OLD.currency,OLD.recipient,OLD.network,OLD.corridor)
    IS DISTINCT FROM ROW(NEW.partner_id,NEW.external_reference,NEW.canonical_hash,NEW.amount_minor,NEW.fee_minor,NEW.currency,NEW.recipient,NEW.network,NEW.corridor)
  THEN RAISE EXCEPTION 'Payment instructions are immutable'; END IF;
  IF OLD.status IS DISTINCT FROM NEW.status THEN
   IF NEW.status_version<>OLD.status_version+1 OR NOT (
    (OLD.status='QUEUED' AND NEW.status IN ('CLAIMED','CANCELLED','ON_HOLD')) OR
    (OLD.status='CLAIMED' AND NEW.status IN ('ARMED','UNKNOWN','FAILED','CANCELLED','QUEUED')) OR
    (OLD.status='ARMED' AND NEW.status IN ('UNKNOWN','PAID')) OR
    (OLD.status='UNKNOWN' AND NEW.status IN ('PAID','FAILED')) OR
    (OLD.status='ON_HOLD' AND NEW.status IN ('CANCELLED','QUEUED'))
   ) THEN RAISE EXCEPTION 'Invalid payout transition'; END IF;
  ELSIF OLD.status_version<>NEW.status_version THEN
   RAISE EXCEPTION 'Version changes require status changes';
  END IF;
 ELSE
  IF ROW(OLD.payout_id,OLD.worker_id,OLD.device_id,OLD.wallet_id,OLD.generation,OLD.instruction_hash,OLD.instructions)
    IS DISTINCT FROM ROW(NEW.payout_id,NEW.worker_id,NEW.device_id,NEW.wallet_id,NEW.generation,NEW.instruction_hash,NEW.instructions)
  THEN RAISE EXCEPTION 'Attempt instructions are immutable'; END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER payout_instructions BEFORE UPDATE ON central.payouts FOR EACH ROW EXECUTE FUNCTION central.immutable_instructions();
CREATE TRIGGER attempt_instructions BEFORE UPDATE ON central.attempts FOR EACH ROW EXECUTE FUNCTION central.immutable_instructions();
CREATE FUNCTION central.append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'Posted ledger and evidence are append only'; END $$;
CREATE TRIGGER immutable_journals BEFORE UPDATE OR DELETE ON central.journals FOR EACH ROW EXECUTE FUNCTION central.append_only();
CREATE TRIGGER immutable_entries BEFORE UPDATE OR DELETE ON central.entries FOR EACH ROW EXECUTE FUNCTION central.append_only();
CREATE FUNCTION central.check_journal() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE jid uuid;
BEGIN
 IF TG_TABLE_NAME='journals' THEN jid:=NEW.id; ELSE jid:=NEW.journal_id; END IF;
 IF NOT EXISTS(SELECT 1 FROM central.entries WHERE journal_id=jid) OR EXISTS(
  SELECT currency FROM central.entries WHERE journal_id=jid GROUP BY currency HAVING sum(amount_minor)<>0 OR count(*)<2
 ) THEN RAISE EXCEPTION 'Unbalanced or empty journal'; END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER balanced_journal AFTER INSERT ON central.journals DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION central.check_journal();
CREATE CONSTRAINT TRIGGER balanced_entries AFTER INSERT ON central.entries DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION central.check_journal();
CREATE TABLE central.history (
 id uuid PRIMARY KEY, payout_id uuid NOT NULL REFERENCES central.payouts(id), status_version integer NOT NULL,
 old_status text, new_status text NOT NULL, actor text NOT NULL, reason text NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(payout_id,status_version)
);
CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE ON central.history FOR EACH ROW EXECUTE FUNCTION central.append_only();
CREATE TABLE central.outbox (
 id uuid PRIMARY KEY, partner_id uuid NOT NULL, payout_id uuid NOT NULL, status_version integer NOT NULL,
 event_type text NOT NULL, payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(payout_id,status_version,event_type), FOREIGN KEY(payout_id,partner_id) REFERENCES central.payouts(id,partner_id)
);
CREATE TABLE central.deliveries (
 event_id uuid PRIMARY KEY REFERENCES central.outbox(id), destination_version integer NOT NULL,
 destination_url text NOT NULL, signing_secret text NOT NULL,
 state text NOT NULL DEFAULT 'READY' CHECK(state IN ('READY','LEASED','DELIVERED')),
 attempts integer NOT NULL DEFAULT 0, next_attempt_at timestamptz NOT NULL DEFAULT now(),
 lease_until timestamptz, generation bigint NOT NULL DEFAULT 0, last_code integer, last_error text,
 accepted_at timestamptz
);
CREATE INDEX deliveries_due ON central.deliveries(next_attempt_at) WHERE state<>'DELIVERED';
CREATE TABLE central.inbox (
 id uuid PRIMARY KEY, source_type text NOT NULL, source_id uuid NOT NULL, event_id uuid NOT NULL,
 payload_hash text NOT NULL, evidence_ref text NOT NULL, protected_payload jsonb NOT NULL, processing_state text NOT NULL,
 response jsonb NOT NULL, received_at timestamptz NOT NULL DEFAULT now(), processed_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(source_type,source_id,event_id)
);
CREATE TABLE central.receipts (
 wallet_id uuid NOT NULL REFERENCES central.wallets(id), provider_reference text NOT NULL,
 payout_id uuid NOT NULL REFERENCES central.payouts(id), evidence_ref text NOT NULL,
 PRIMARY KEY(wallet_id,provider_reference), UNIQUE(payout_id)
);
CREATE TABLE central.cases (
 id uuid PRIMARY KEY, payout_id uuid NOT NULL REFERENCES central.payouts(id), reason text NOT NULL,
 state text NOT NULL DEFAULT 'OPEN' CHECK(state IN ('OPEN','PROPOSED','RESOLVED')),
 evidence_ref text, decision text CHECK(decision IN ('PAID','FAILED')),
 proposer uuid REFERENCES central.credentials(id), approver uuid REFERENCES central.credentials(id),
 provider_reference text, stale_execution_neutralized boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now(), resolved_at timestamptz,
 CHECK(approver IS NULL OR approver<>proposer)
);
CREATE UNIQUE INDEX case_open ON central.cases(payout_id) WHERE state<>'RESOLVED';
CREATE TABLE central.statement_imports (
 id uuid PRIMARY KEY, wallet_id uuid NOT NULL REFERENCES central.wallets(id), source_reference text NOT NULL,
 payload_hash text NOT NULL, evidence_ref text NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(wallet_id,source_reference), UNIQUE(id,wallet_id)
);
CREATE TABLE central.statement_items (
 id uuid PRIMARY KEY, import_id uuid NOT NULL,
 wallet_id uuid NOT NULL REFERENCES central.wallets(id), operator_reference text NOT NULL,
 amount_minor bigint NOT NULL CHECK(amount_minor<>0), currency text NOT NULL, recipient text NOT NULL,
 occurred_at timestamptz NOT NULL, payout_id uuid REFERENCES central.payouts(id),
 UNIQUE(wallet_id,operator_reference), FOREIGN KEY(import_id,wallet_id) REFERENCES central.statement_imports(id,wallet_id),
 FOREIGN KEY(wallet_id,currency) REFERENCES central.wallets(id,currency)
);
CREATE TABLE central.audit (
 id uuid PRIMARY KEY, actor text NOT NULL, action text NOT NULL, target text NOT NULL,
 evidence_ref text NOT NULL, correlation_id uuid NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TRIGGER immutable_audit BEFORE UPDATE OR DELETE ON central.audit FOR EACH ROW EXECUTE FUNCTION central.append_only();
CREATE TRIGGER immutable_inbox BEFORE UPDATE OR DELETE ON central.inbox FOR EACH ROW EXECUTE FUNCTION central.append_only();
CREATE TRIGGER immutable_admission BEFORE UPDATE OR DELETE ON central.api_idempotency FOR EACH ROW EXECUTE FUNCTION central.append_only();
CREATE TRIGGER immutable_outbox BEFORE UPDATE OR DELETE ON central.outbox FOR EACH ROW EXECUTE FUNCTION central.append_only();
CREATE FUNCTION central.check_payout_effects() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS(SELECT 1 FROM central.history WHERE payout_id=NEW.id AND status_version=NEW.status_version AND new_status=NEW.status)
 OR NOT EXISTS(SELECT 1 FROM central.outbox WHERE payout_id=NEW.id AND status_version=NEW.status_version)
 THEN RAISE EXCEPTION 'Payout state requires atomic history and outbox'; END IF;
 IF NEW.status='PAID' AND NOT EXISTS(SELECT 1 FROM central.journals WHERE payout_id=NEW.id AND event_type='PAYOUT')
 THEN RAISE EXCEPTION 'Paid payout requires posted journal'; END IF;
 RETURN NULL;
END $$;
CREATE CONSTRAINT TRIGGER payout_effects AFTER INSERT OR UPDATE ON central.payouts
 DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION central.check_payout_effects();
-- Runtime roles must not own tables. Grant only SELECT/INSERT on entries/journals/history/audit.
-- Do not grant TRUNCATE, DELETE, UPDATE or permission to disable triggers on financial evidence.
