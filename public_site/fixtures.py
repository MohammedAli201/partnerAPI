"""Synthetic website examples; never used as operational availability or pricing."""
TRACKING_EXAMPLES={
    'processing': {'reference':'HBX-DEMO-2041','status':'PROCESSING',
       'steps':[('RECEIVED','10:20'),('PROCESSING','10:22')]},
    'action': {'reference':'HBX-DEMO-2042','status':'UNKNOWN',
       'steps':[('RECEIVED','10:20'),('PROCESSING','10:22'),('UNKNOWN','10:24')]},
    'delivered': {'reference':'HBX-DEMO-2043','status':'SENT',
       'steps':[('RECEIVED','10:20'),('PROCESSING','10:22'),('SENT','10:26')]},
    'failed': {'reference':'HBX-DEMO-2044','status':'FAILED',
       'steps':[('RECEIVED','10:20'),('PROCESSING','10:22'),('FAILED','10:24')]},
}
