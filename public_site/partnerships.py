"""Durable public enquiries; this module never admits or moves payout funds."""
import hashlib
import json
import re
from typing import Literal
from uuid import UUID,uuid4

from fastapi import APIRouter,Depends,Header,HTTPException,Query,Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel,ConfigDict,Field,field_validator
from sqlalchemy import text

class PartnershipEnquiry(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    company_name:str=Field(min_length=2,max_length=160)
    country:str=Field(min_length=2,max_length=100)
    contact_name:str=Field(min_length=2,max_length=100)
    email:str=Field(min_length=5,max_length=254)
    monthly_volume:Literal['Under $10k / month','$10k – $100k / month','$100k – $1M / month','Over $1M / month']
    channels:Literal['All channels','Wallets only','Banks only','Cash pickup only','Wallets + banks','Wallets + banks + cash pickup']

    @field_validator('email')
    @classmethod
    def valid_email(cls,value):
        if not re.fullmatch(r'[^\s@<>"\x00-\x1f]+@[^\s@<>"\x00-\x1f]+\.[^\s@<>"\x00-\x1f]+',value):
            raise ValueError('Enter a valid business email')
        return value

    @field_validator('company_name','country','contact_name')
    @classmethod
    def plain_text(cls,value):
        if any(ord(c)<32 for c in value):
            raise ValueError('Use plain text without control characters')
        return value

def make_router(get_db,require_role):
    router=APIRouter()
    templates=Jinja2Templates(directory='templates')

    @router.post('/api/partnerships',status_code=201)
    def create_enquiry(request:Request,body:PartnershipEnquiry,
        idempotency_key:UUID|None=Header(None),db=Depends(get_db)):
        from quotas import take
        ip=request.client.host if request.client else 'unknown'
        take(db,'website:'+hashlib.sha256(ip.encode()).hexdigest(),'partnership-enquiry',10,60)
        values=body.model_dump()
        payload_hash=hashlib.sha256(json.dumps(values,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        identifier=idempotency_key or uuid4()
        reference='HB-P-'+identifier.hex[:12].upper()
        db.execute(text('''INSERT INTO public_partnership_enquiries
            (id,reference,payload_hash,company_name,country,contact_name,email,monthly_volume,channels)
            VALUES(:id,:reference,:payload_hash,:company_name,:country,:contact_name,:email,:monthly_volume,:channels)
            ON CONFLICT(id) DO NOTHING'''),dict(id=identifier,reference=reference,payload_hash=payload_hash,**values))
        stored=db.execute(text('SELECT reference,payload_hash FROM public_partnership_enquiries WHERE id=:id'),{'id':identifier}).mappings().one()
        if stored['payload_hash']!=payload_hash:
            raise HTTPException(409,'This submission reference was used for different enquiry details')
        db.commit()
        return JSONResponse({'reference':stored['reference'],'received':True},status_code=201,headers={'Cache-Control':'no-store'})

    @router.get('/admin/partnerships',include_in_schema=False)
    def admin_enquiries(request:Request,page:int=Query(1,ge=1,le=10000),
        user=Depends(require_role('admin')),db=Depends(get_db)):
        limit=50
        rows=db.execute(text('''SELECT reference,company_name,country,contact_name,email,monthly_volume,channels,created_at
            FROM public_partnership_enquiries ORDER BY created_at DESC,id DESC LIMIT :limit OFFSET :offset'''),
            {'limit':limit+1,'offset':(page-1)*limit}).mappings().all()
        return templates.TemplateResponse(request=request,name='partnership_enquiries.html',context={
            'rows':rows[:limit],'page':page,'more':len(rows)>limit,'username':user['username']},
            headers={'Cache-Control':'no-store','X-Robots-Tag':'noindex, nofollow'})

    return router
