"""Validated local drafts. No sending adapter is configured or implied."""
import re
from typing import Literal
from urllib.parse import urlparse
from pydantic import BaseModel, ConfigDict, Field, field_validator


class Draft(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    name: str=Field(min_length=2,max_length=100)
    email: str=Field(min_length=5,max_length=254)
    message: str=Field(min_length=10,max_length=2000)

    @field_validator('email')
    @classmethod
    def email_address(cls,v):
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',v):
            raise ValueError('Valid email address required')
        return v


class PartnerDraft(Draft):
    company: str=Field(min_length=2,max_length=160)
    website: str=Field(min_length=8,max_length=500)
    countries: str=Field(min_length=2,max_length=200)
    volume: Literal['under_1000','1000_10000','10001_50000','over_50000']
    methods: list[Literal['mobile_wallet','other']]=Field(min_length=1,max_length=2)

    @field_validator('website')
    @classmethod
    def website_address(cls,v):
        p=urlparse(v)
        if p.scheme not in ('https','http') or not p.hostname or p.username or p.password:
            raise ValueError('Complete HTTP(S) website required')
        return v


class SupportDraft(Draft):
    topic: Literal['delivery','details','other']


def local_preview(draft):
    # Deliberately no database, email, analytics, logging or external HTTP call.
    return {'mode':'preview','sent':False,'stored':False,'draft':draft.model_dump()}
