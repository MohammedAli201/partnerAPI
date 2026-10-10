"""Use the original app's read queries without changing its owned database."""


class OriginalAdminReader:
    def __init__(self, module, session_factory, payout_model):
        self.module, self.session_factory, self.payout_model = module, session_factory, payout_model

    def payouts(self, request, q, status, limit, offset):
        with self.session_factory() as db:
            return self.module.admin_list_payouts(request=request, _auth=None, db=db,
                q=q, status=status, limit=limit, offset=offset)

    def summary(self, request):
        with self.session_factory() as db:
            return self.module.admin_summary(request=request, _auth=None, db=db)

    def partner_payouts(self, request, session, q, status, limit, offset):
        with self.session_factory() as db:
            return self.module.partner_list_payouts(request=request, sess=session, db=db,
                q=q, status=status, limit=limit, offset=offset)

    def partner_summary(self, request, session):
        with self.session_factory() as db:
            return self.module.partner_summary(request=request, sess=session, db=db)

    def detail(self, payout_id):
        with self.session_factory() as db:
            payout = db.query(self.payout_model).filter(self.payout_model.id == payout_id).first()
            if payout is None:
                return None
            # Do not expose request_payload, credentials or raw provider data.
            return {name: getattr(payout, name) for name in (
                'id', 'partner_id', 'partner_tx_id', 'amount', 'currency',
                'recipient', 'provider', 'status', 'created_at', 'updated_at')}
