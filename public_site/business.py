"""The single reviewed public business configuration. Never put secrets here."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator, field_validator
from urllib.parse import urlsplit


class ContactDetails(BaseModel):
    model_config=ConfigDict(frozen=True,extra='forbid')
    email: str|None=None
    phone: str|None=None
    whatsapp_url: str|None=None
    address: str|None=None
    hours: str|None=None
    timezone: str|None=None


class ReceivingMethod(BaseModel):
    model_config=ConfigDict(frozen=True,extra='forbid')
    code: str
    country: str
    network: str|None=None
    commercial_partner: bool=False
    requirements: tuple[str,...]=()
    restrictions: str|None=None


class BusinessConfig(BaseModel):
    model_config=ConfigDict(frozen=True,extra='forbid')
    brand: str='Hubaal'
    legal_entity: str|None=None
    contact: ContactDetails=Field(default_factory=ContactDetails)
    receiving_focus: str='SO'  # User confirmed Somalia as initial design focus.
    sending_countries: tuple[str,...]=()
    receiving_countries: tuple[str,...]=()
    payout_methods: tuple[ReceivingMethod,...]=()
    approved_fees: tuple[str,...]=()
    approved_currencies: tuple[str,...]=()
    approved_limits: tuple[str,...]=()
    delivery_estimates: tuple[str,...]=()
    licensing_disclosure: str|None=None
    approved_partners: tuple[str,...]=()
    portal_url: str|None='/login'  # Existing authenticated portal, not retail sending.
    api_documentation_url: str|None=None
    quote_api: str|None=None
    tracking_api: str|None=None
    tracking_verification_url: str|None=None
    enquiry_integration: str|None=None
    retail_next_step: str|None=None
    service_mode: Literal['retail','partner_payouts','both']='partner_payouts'
    launch_mode: Literal['preview','live']='preview'
    website_url: str|None=None
    privacy_content: tuple[str,...]=()
    terms_content: tuple[str,...]=()
    complaints_content: tuple[str,...]=()

    @field_validator('portal_url','api_documentation_url','quote_api','tracking_api',
        'tracking_verification_url','enquiry_integration','retail_next_step','website_url')
    @classmethod
    def safe_url(cls,value):
        if value is None:return value
        p=urlsplit(value)
        if (value.startswith('/') and not value.startswith('//') and not p.netloc) or (
            p.scheme in ('https','http') and p.hostname and not p.username and not p.password):
            return value
        raise ValueError('Use a same-origin path or complete HTTP(S) destination')

    @model_validator(mode='after')
    def live_readiness(self):
        if self.launch_mode=='live':
            required=(self.legal_entity,self.contact.email,self.contact.hours,self.contact.timezone,
              self.receiving_countries,self.payout_methods,self.licensing_disclosure,self.website_url,
              self.privacy_content,self.terms_content,self.complaints_content)
            if not all(required):
                raise ValueError('Live launch requires approved identity, coverage, support, disclosures and policies')
        # Retail activation requires an implemented adapter, not just a URL.
        if self.service_mode!='partner_payouts':
            raise ValueError('Retail journey is not integrated in this payout-only project')
        return self


# The user supplied these company service details for the public website.
BUSINESS=BusinessConfig(
    brand='Hubaal',
    contact=ContactDetails(email='hello@hubaal.so',address='Mogadishu, Somalia'),
    licensing_disclosure='Hubaal is in the process of obtaining approval. Our payout service is not live yet.',
    enquiry_integration='/api/partnerships',
    approved_currencies=('USD',),
    receiving_countries=('SO',),
    payout_methods=(
        ReceivingMethod(code='mobile_wallet',country='SO',network='EVC Plus'),
        ReceivingMethod(code='mobile_wallet',country='SO',network='ZAAD'),
        ReceivingMethod(code='mobile_wallet',country='SO',network='eDahab'),
        ReceivingMethod(code='bank_account',country='SO',network='Salaam Bank'),
        ReceivingMethod(code='bank_account',country='SO',network='Premier Bank'),
        ReceivingMethod(code='cash_pickup',country='SO',network='Cash pickup'),
    ),
)
