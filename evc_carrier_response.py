"""Strict grammar from user-supplied EVC screenshots; never use those images as live proof."""
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal

SUCCESS = re.compile(r'^<-EVCPLUS-\s*> \$([0-9]+(?:\.[0-9]{1,2})?) ayaad uwareejisay ([^()]+)\((6[0-9]{8})\), Tar: ([0-9]{2}/[0-9]{2}/[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}), Haraagaagu waa \$([0-9]+(?:\.[0-9]{1,2})?)\.(?: La soo deg App-ka WAAFI http://onelink\.to/waafi)?$')


def normalize(text):
    return ' '.join(text.split())


def success_response(text, job, earliest, latest):
    if not isinstance(text, str) or len(text) > 4096:
        raise ValueError('Unrecognized carrier response')
    match = SUCCESS.fullmatch(normalize(text))
    if not match:
        raise ValueError('Unrecognized carrier response')
    amount, name, number, date, balance = match.groups()
    when = datetime.strptime(date, '%d/%m/%y %H:%M:%S').replace(tzinfo=timezone(timedelta(hours=3)))
    if (int(Decimal(amount)*100) != job['amount_minor'] or '+252'+number != job['recipient']
            or normalize(name).casefold() != normalize(job['recipient_name']).casefold()
            or not earliest <= when <= latest):
        raise ValueError('Carrier recipient, amount or timestamp mismatch')
    return dict(amount_minor=int(Decimal(amount)*100), recipient='+252'+number,
                recipient_name=normalize(name), remaining_minor=int(Decimal(balance)*100),
                carrier_at=when, response_text=normalize(text))
