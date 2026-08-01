"""OTP issuance/verification for the Customer light-login (CLAUDE.md §6.3.b, §8).

TODO:
- Generate a numeric OTP, store it (Redis or a DB table with TTL = settings.otp_expire_minutes),
  and send it via SMS/email provider.
- Verify the submitted code against the stored value, respecting expiry and a max-attempts limit.
- Treat phone/email as personal data: never log the raw OTP or contact info at INFO level.
"""


def send_otp(phone: str | None, email: str | None) -> None:
    raise NotImplementedError("TODO: implement OTP generation + delivery")


def verify_otp(phone: str | None, email: str | None, otp_code: str) -> bool:
    raise NotImplementedError("TODO: implement OTP verification")
