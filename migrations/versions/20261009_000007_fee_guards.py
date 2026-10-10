"""Guard fee postings and preserve approved reversal evidence."""
from alembic import op
revision='20261009_000007'
down_revision='20261009_000006'
branch_labels=None
depends_on=None

def upgrade():
    op.get_bind().exec_driver_sql('''
    CREATE INDEX financial_payout_events ON ledger_journals(payout_id,event_type,posted_at);
    CREATE FUNCTION approved_fee_review_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      IF TG_OP='DELETE' OR OLD.journal_id IS NOT NULL THEN RAISE EXCEPTION 'Fee reversal evidence is immutable'; END IF;
      IF (NEW.id,NEW.payout_id,NEW.business_reference,NEW.amount_minor,NEW.reason,NEW.evidence_ref,NEW.proposer,NEW.created_at)
        IS DISTINCT FROM (OLD.id,OLD.payout_id,OLD.business_reference,OLD.amount_minor,OLD.reason,OLD.evidence_ref,OLD.proposer,OLD.created_at)
      THEN RAISE EXCEPTION 'Fee reversal instructions are immutable'; END IF;
      RETURN NEW;
    END $$;
    CREATE TRIGGER fee_review_guard BEFORE UPDATE OR DELETE ON fee_reversal_reviews FOR EACH ROW EXECUTE FUNCTION approved_fee_review_guard();
    CREATE FUNCTION financial_fee_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE snap payout_fee_snapshots; actual bigint; original ledger_journals; reversed bigint;
    BEGIN
      IF NEW.event_type NOT IN ('PAYOUT','FEE_REVERSAL') THEN RETURN NEW; END IF;
      SELECT * INTO snap FROM payout_fee_snapshots WHERE payout_id=NEW.payout_id;
      IF snap.payout_id IS NULL OR snap.currency<>NEW.currency THEN RAISE EXCEPTION 'Immutable fee snapshot required'; END IF;
      SELECT COALESCE(sum(e.amount_minor),0) INTO actual FROM ledger_entries e JOIN ledger_accounts a ON a.id=e.account_id
        WHERE e.journal_id=NEW.id AND a.kind='FEES';
      IF NEW.event_type='PAYOUT' THEN
        IF actual<>-snap.fee_minor THEN RAISE EXCEPTION 'Recognized fee does not match admission snapshot'; END IF;
      ELSE
        SELECT * INTO original FROM ledger_journals WHERE id=NEW.reversal_of;
        IF original.id IS NULL OR original.event_type<>'PAYOUT' OR original.payout_id<>NEW.payout_id OR original.currency<>NEW.currency
          OR actual<=0 THEN RAISE EXCEPTION 'Linked positive fee compensation required'; END IF;
        SELECT COALESCE(sum(e.amount_minor),0) INTO reversed FROM ledger_journals j JOIN ledger_entries e ON e.journal_id=j.id
          JOIN ledger_accounts a ON a.id=e.account_id WHERE j.payout_id=NEW.payout_id AND j.event_type='FEE_REVERSAL' AND a.kind='FEES';
        IF reversed>snap.fee_minor OR NOT EXISTS(SELECT 1 FROM fee_reversal_reviews r WHERE r.journal_id=NEW.id
          AND r.payout_id=NEW.payout_id AND r.amount_minor=actual AND r.approved_at IS NOT NULL AND r.approver<>r.proposer)
        THEN RAISE EXCEPTION 'Independent approval and remaining fee required'; END IF;
      END IF;
      RETURN NEW;
    END $$;
    CREATE CONSTRAINT TRIGGER guarded_financial_fees AFTER INSERT ON ledger_journals
      DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION financial_fee_guard();
    ''')

def downgrade():
    raise RuntimeError('Financial fee guards must not be removed by destructive downgrade')
