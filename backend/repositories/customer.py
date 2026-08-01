import uuid

from sqlalchemy.orm import Session

from backend.models.customer import Customer


def get_customer_by_contact(db: Session, phone: str | None, email: str | None) -> Customer | None:
    query = db.query(Customer)
    if phone:
        return query.filter(Customer.phone == phone).first()
    if email:
        return query.filter(Customer.email == email).first()
    return None


def get_or_create_customer(
    db: Session, phone: str | None, email: str | None, full_name: str | None = None
) -> Customer:
    customer = get_customer_by_contact(db, phone, email)
    if customer is not None:
        return customer

    customer = Customer(id=str(uuid.uuid4()), phone=phone, email=email, full_name=full_name)
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def mark_verified(db: Session, customer: Customer) -> Customer:
    customer.is_verified = True
    db.commit()
    db.refresh(customer)
    return customer
