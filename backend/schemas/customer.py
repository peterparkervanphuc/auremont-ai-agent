from datetime import datetime

from pydantic import BaseModel


class OtpRequest(BaseModel):
    phone: str | None = None
    email: str | None = None


class OtpVerify(BaseModel):
    phone: str | None = None
    email: str | None = None
    otp_code: str
    full_name: str | None = None


class CustomerResponse(BaseModel):
    id: str
    phone: str | None = None
    email: str | None = None
    full_name: str | None = None
    is_verified: bool
    created_at: datetime

    model_config = {"from_attributes": True}
