from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.core.mysql_client import get_db
from backend.repositories.customer import get_or_create_customer, mark_verified
from backend.schemas.customer import CustomerResponse, OtpRequest, OtpVerify
from backend.services.otp_service import send_otp, verify_otp

router = APIRouter(prefix="/customer", tags=["Customer Auth (Public)"])


@router.post("/otp/request", status_code=status.HTTP_202_ACCEPTED)
async def request_otp(payload: OtpRequest) -> dict:
    """Light login step 1 — send OTP to phone/email (CLAUDE.md §6.3.b)."""
    if not payload.phone and not payload.email:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="phone or email is required")
    send_otp(payload.phone, payload.email)
    return {"message": "OTP sent"}


@router.post("/otp/verify", response_model=CustomerResponse)
async def verify_otp_code(payload: OtpVerify, db: Session = Depends(get_db)) -> CustomerResponse:
    """Light login step 2 — verify OTP and create/return the Customer record."""
    if not verify_otp(payload.phone, payload.email, payload.otp_code):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired OTP")

    customer = get_or_create_customer(db, payload.phone, payload.email, payload.full_name)
    return mark_verified(db, customer)
