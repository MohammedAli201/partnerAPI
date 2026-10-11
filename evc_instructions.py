"""Translate canonical payout data into EVC instructions without executing them."""
import re
from decimal import Decimal


def carrier_number(number):
    """Strip only Somalia's +252 prefix; never truncate an arbitrary number."""
    if not isinstance(number, str) or not re.fullmatch(r'\+2526[0-9]{8}', number):
        raise ValueError('EVC recipient must be a Somali mobile number such as +252615738865')
    return number[4:]


def transfer_instruction(payload):
    if payload.provider.strip().lower() not in {'evc', 'hormuud'}:
        raise ValueError('This USSD flow supports EVC/Hormuud only')
    if payload.currency != 'USD':
        raise ValueError('EVC USSD transfers require USD')
    recipient = payload.recipient.strip()
    local = carrier_number(recipient)
    beneficiary = payload.request_payload.get('beneficiary', {})
    if not isinstance(beneficiary, dict):
        raise ValueError('request_payload.beneficiary must be an object')
    mobile = beneficiary.get('mobile')
    if mobile is not None and (not isinstance(mobile, str) or mobile.strip() != recipient):
        raise ValueError('beneficiary.mobile must match the transaction recipient')
    name = beneficiary.get('name') or payload.request_payload.get('recipient_name')
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120 or any(ord(c) < 32 for c in name):
        raise ValueError('A beneficiary name is required')
    amount = Decimal(payload.amount)
    if not amount.is_finite() or amount <= 0 or amount != amount.quantize(Decimal('.01')):
        raise ValueError('A positive exact USD amount is required')
    command_amount = format(amount, 'f').rstrip('0').rstrip('.') if '.' in format(amount, 'f') else format(amount, 'f')
    return dict(provider='EVC', recipient=recipient, recipient_name=name.strip(),
                ussd_recipient=local, amount=format(amount, '.2f'), currency='USD',
                command=f'*712*{local}*{command_amount}#', payment_executed=False)
