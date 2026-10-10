"""Mount signed synthetic payouts into the existing local partner FastAPI app.

Launch from the original partner app directory with the private simulator config
and JUBATECH_SIMULATOR_ENVIRONMENT=Development/Test in the environment.
"""
import importlib
import json
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

if os.environ.get('JUBATECH_SIMULATOR_ENVIRONMENT') not in {'Development', 'Test'}:
    raise RuntimeError('SIMULATOR_ENVIRONMENT_REQUIRED')
original_path = Path(os.environ['JUBATECH_PARTNER_APP_DIR']).resolve(strict=True)
if Path.cwd().resolve() != original_path or not (original_path/'main.py').is_file():
    raise RuntimeError('ORIGINAL_PARTNER_WORKING_DIRECTORY_REQUIRED')
sys.path.insert(0, str(original_path))
from config import get_settings
if get_settings().environment.lower() not in {'development', 'test'}:
    raise RuntimeError('ORIGINAL_PARTNER_DEVELOPMENT_ENVIRONMENT_REQUIRED')
if urlsplit(get_settings().database_url).hostname not in {'localhost', '127.0.0.1', '::1'}:
    raise RuntimeError('ORIGINAL_PARTNER_LOCAL_DATABASE_REQUIRED')

from fastapi import HTTPException, Request
from auth_session import get_session
from database import SessionLocal
from models import User, Payout, Partner
from protocol import Simulator
from fastapi_extension import install
from partner_dashboard import install as install_dashboard
from original_admin_reader import OriginalAdminReader
from original_admin_api import install as install_original_admin_api
from original_admin_api import install_partner

original_module = importlib.import_module('main')
app = original_module.app
settings = json.loads(Path(os.environ['JUBATECH_SIMULATOR_CONFIG']).read_text(encoding='utf-8-sig'))
simulator = Simulator(settings['database'], settings['apiKey'], settings['hmacSecret'],
    os.environ['JUBATECH_SIMULATOR_ENVIRONMENT'], settings['wallets'], settings.get('callbackUrl',''),
    settings.get('callbackSecret',''), settings.get('skipRecipientVerification',False))

def require_active_admin(request: Request):
    session = get_session(request)
    with SessionLocal() as db:
        user = db.query(User).filter(User.id == session.get('uid')).first()
        if not user or not user.is_active or user.role != 'admin' or session.get('role') != 'admin':
            raise HTTPException(403, detail='ACTIVE_ADMIN_REQUIRED')
        return user.id


def require_active_partner(request: Request):
    session = get_session(request)
    with SessionLocal() as db:
        user = db.query(User).filter(User.id == session.get('uid')).first()
        if not user or not user.is_active or user.role != 'partner' or session.get('role') != 'partner':
            raise HTTPException(403, detail='ACTIVE_PARTNER_REQUIRED')
        partner = db.query(Partner).filter(Partner.id == user.partner_id, Partner.is_active == True).first()
        if not partner:
            raise HTTPException(403, detail='ACTIVE_PARTNER_REQUIRED')
        return {'uid': user.id, 'role': 'partner', 'partner_id': partner.id}


install(app, simulator)
install_dashboard(app, simulator, require_active_admin)
reader = OriginalAdminReader(original_module, SessionLocal, Payout)
partner_id = settings.get('originalPartnerId')
install_original_admin_api(app, simulator, require_active_admin, reader, partner_id)
if partner_id is not None:
    with SessionLocal() as db:
        if type(partner_id) is not int or not db.query(Partner).filter(Partner.id == partner_id, Partner.is_active == True).first():
            raise RuntimeError('SIMULATOR_PARTNER_BINDING_INVALID')
    install_partner(app, simulator, require_active_partner, reader, partner_id)

if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=8000, access_log=False)
