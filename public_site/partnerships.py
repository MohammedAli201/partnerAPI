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

BusinessType=Literal['Remittance / MTO','Payment institution / EMI','Fintech platform','Bank','Other']
ChannelName=Literal['EVC Plus','ZAAD','eDahab','Bank transfer']

class PartnershipEnquiry(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    company_name:str=Field(min_length=2,max_length=160)
    country:str=Field(min_length=2,max_length=100)
    contact_name:str=Field(min_length=2,max_length=100)
    email:str=Field(min_length=5,max_length=254)
    monthly_volume:Literal['Under $10k / month','$10k – $100k / month','$100k – $1M / month','Over $1M / month']
    channels:Literal['All channels','Wallets only','Banks only','Cash pickup only','Wallets + banks','Wallets + banks + cash pickup']

    business_type:BusinessType|None=None
    message:str|None=Field(default=None,max_length=4096)
    selected_channels:list[ChannelName]|None=Field(default=None,min_length=1,max_length=4)

    @field_validator('message')
    @classmethod
    def message_text(cls,value):
        if value is not None and '\x00' in value:raise ValueError('Message cannot contain null characters')
        return value

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

class LandingEnquiry(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    full_name:str=Field(min_length=2,max_length=100)
    work_email:str=Field(min_length=5,max_length=254)
    company:str=Field(min_length=2,max_length=160)
    business_type:BusinessType
    country:str=Field(min_length=2,max_length=100)
    monthly_volume:Literal['Under $10k / month','$10k \u2013 $100k / month','$100k \u2013 $1M / month','Over $1M / month']
    channels:list[ChannelName]=Field(min_length=1,max_length=4)
    message:str=Field(default='',max_length=4096)

    @field_validator('message')
    @classmethod
    def message_text(cls,value):return PartnershipEnquiry.message_text(value)

    @field_validator('work_email')
    @classmethod
    def valid_email(cls,value):return PartnershipEnquiry.valid_email(value)

    @field_validator('full_name','company','country')
    @classmethod
    def plain_text(cls,value):return PartnershipEnquiry.plain_text(value)

    @field_validator('channels')
    @classmethod
    def unique_channels(cls,value):
        if len(set(value))!=len(value):raise ValueError('Select each channel only once')
        return sorted(value)

    def partnership(self):
        wallets=any(c!='Bank transfer' for c in self.channels)
        banks='Bank transfer' in self.channels
        summary='Wallets + banks' if wallets and banks else 'Wallets only' if wallets else 'Banks only'
        return PartnershipEnquiry(company_name=self.company,country=self.country,contact_name=self.full_name,
            email=self.work_email,monthly_volume=self.monthly_volume,channels=summary,
            business_type=self.business_type,message=self.message,selected_channels=self.channels)

def make_router(get_db,require_role):
    router=APIRouter()
    templates=Jinja2Templates(directory='templates')

    def store_enquiry(request,body,idempotency_key,db):
        from quotas import take
        ip=request.client.host if request.client else 'unknown'
        take(db,'website:'+hashlib.sha256(ip.encode()).hexdigest(),'partnership-enquiry',10,60)
        values=body.model_dump(exclude_none=True)
        payload_hash=hashlib.sha256(json.dumps(values,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        identifier=idempotency_key or uuid4()
        reference='HB-P-'+identifier.hex[:12].upper()
        db.execute(text('''INSERT INTO public_partnership_enquiries
            (id,reference,payload_hash,company_name,country,contact_name,email,monthly_volume,channels,business_type,message,selected_channels)
            VALUES(:id,:reference,:payload_hash,:company_name,:country,:contact_name,:email,:monthly_volume,:channels,:business_type,:message,CAST(:selected_channels AS jsonb))
            ON CONFLICT(id) DO NOTHING'''),dict(id=identifier,reference=reference,payload_hash=payload_hash,**{**values,'business_type':body.business_type,'message':body.message or '', 'selected_channels':json.dumps(body.selected_channels or [])}))
        stored=db.execute(text('SELECT reference,payload_hash FROM public_partnership_enquiries WHERE id=:id'),{'id':identifier}).mappings().one()
        if stored['payload_hash']!=payload_hash:
            raise HTTPException(409,'This submission reference was used for different enquiry details')
        db.commit()
        return JSONResponse({'reference':stored['reference'],'received':True},status_code=201,headers={'Cache-Control':'no-store'})

    @router.post('/api/partnerships',status_code=201)
    def create_enquiry(request:Request,body:PartnershipEnquiry,idempotency_key:UUID|None=Header(None),db=Depends(get_db)):
        return store_enquiry(request,body,idempotency_key,db)

    @router.post('/api/enquiries',status_code=201)
    def landing_enquiry(request:Request,body:LandingEnquiry,idempotency_key:UUID|None=Header(None),db=Depends(get_db)):
        return store_enquiry(request,body.partnership(),idempotency_key,db)

    @router.get('/admin/partnerships',include_in_schema=False)
    def admin_enquiries(request:Request,page:int=Query(1,ge=1,le=10000),
        user=Depends(require_role('admin')),db=Depends(get_db)):
        limit=50
        rows=db.execute(text('''SELECT reference,company_name,country,contact_name,email,monthly_volume,channels,business_type,message,selected_channels,created_at
            FROM public_partnership_enquiries ORDER BY created_at DESC,id DESC LIMIT :limit OFFSET :offset'''),
            {'limit':limit+1,'offset':(page-1)*limit}).mappings().all()
        return templates.TemplateResponse(request=request,name='partnership_enquiries.html',context={
            'rows':rows[:limit],'page':page,'more':len(rows)>limit,'username':user['username']},
            headers={'Cache-Control':'no-store','X-Robots-Tag':'noindex, nofollow'})

    return router
