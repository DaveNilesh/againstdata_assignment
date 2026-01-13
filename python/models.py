from pydantic import BaseModel
from typing import Optional, List

class CompanyData(BaseModel):
    id: str
    name: str
    domain: str
    generic_email: Optional[str] = None
    contact_email: Optional[str] = None
    privacy_email: Optional[str] = None
    delete_link: Optional[str] = None
    country: Optional[str] = None

class ProcessingRequest(BaseModel):
    id: str
    domain: str
    name: str

class ProcessingResponse(BaseModel):
    status: str
    message: str
    data: Optional[CompanyData] = None
