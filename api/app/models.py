"""SQLAlchemy 2.0 models. Consignee name/phone are personal data (DPDP Act 2023)."""
import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _enum(e: type[enum.Enum]) -> Enum:
    return Enum(e, native_enum=False, length=24, values_callable=lambda x: [m.value for m in x])


class Role(str, enum.Enum):
    driver = "driver"
    billing = "billing"
    ops = "ops"
    md = "md"
    admin = "admin"


class PodStatus(str, enum.Enum):
    pending = "pending"
    uploaded = "uploaded"
    verified = "verified"
    needs_review = "needs_review"
    retake_requested = "retake_requested"
    rejected = "rejected"
    billed = "billed"


class TripState(str, enum.Enum):
    planned = "planned"
    in_transit = "in_transit"
    delivered = "delivered"
    cancelled = "cancelled"


class ExpenseCategory(str, enum.Enum):
    fuel = "fuel"
    toll = "toll"
    repair = "repair"
    loading = "loading"
    food = "food"
    fine = "fine"
    other = "other"


class ExpenseStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class LinkKind(str, enum.Enum):
    sms_upload = "sms_upload"
    client_view = "client_view"
    client_track = "client_track"


def pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


class Branch(Base):
    __tablename__ = "branches"
    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(String(120), unique=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(20), unique=True)
    email: Mapped[str | None] = mapped_column(String(160), unique=True)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    failed_logins: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    must_change_secret: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")  # set by an office PIN reset
    tracking_consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # DPDP: driver agreed to share location during trips
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # bumped on password change: older tokens die
    role: Mapped[Role] = mapped_column(_enum(Role))
    language: Mapped[str] = mapped_column(String(2), default="hi")
    branch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("branches.id"))
    created_at: Mapped[datetime] = now()


class Client(Base):
    __tablename__ = "clients"
    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(String(160), unique=True)
    segment: Mapped[str | None] = mapped_column(String(60))
    billing_cycle: Mapped[str] = mapped_column(String(16), default="weekly")
    tally_ledger: Mapped[str | None] = mapped_column(String(160))


class Vehicle(Base):
    __tablename__ = "vehicles"
    id: Mapped[uuid.UUID] = pk()
    reg_no: Mapped[str] = mapped_column(String(20), unique=True)
    is_hired: Mapped[bool] = mapped_column(Boolean, default=False)


class Invoice(Base):
    __tablename__ = "invoices"
    id: Mapped[uuid.UUID] = pk()
    invoice_no: Mapped[str] = mapped_column(String(40), unique=True)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"))
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    period_label: Mapped[str | None] = mapped_column(String(80))
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = now()


class Trip(Base):
    __tablename__ = "trips"
    __table_args__ = (
        CheckConstraint("retake_count <= 2", name="ck_trips_retake_cap"),
        Index("ix_trips_pod_status", "pod_status"),
        Index("ix_trips_client_status", "client_id", "pod_status"),
    )
    id: Mapped[uuid.UUID] = pk()
    trip_code: Mapped[str] = mapped_column(String(24), unique=True)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"))
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id"))
    driver_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    branch_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("branches.id"), index=True)
    lr_no: Mapped[str] = mapped_column(String(40))
    eway_bill_no: Mapped[str] = mapped_column(String(12))  # every trip links to an e-way bill
    origin: Mapped[str] = mapped_column(String(120))
    destination: Mapped[str] = mapped_column(String(120))
    freight_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    consignee_name: Mapped[str | None] = mapped_column(String(160))  # PII
    consignee_phone: Mapped[str | None] = mapped_column(String(20))  # PII
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    pod_status: Mapped[PodStatus] = mapped_column(_enum(PodStatus), default=PodStatus.pending)
    retake_count: Mapped[int] = mapped_column(Integer, default=0)
    pod_uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # latest upload
    first_pod_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # first ever upload (24 h KPI)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("invoices.id"))
    invoiced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    state: Mapped[TripState] = mapped_column(_enum(TripState), default=TripState.in_transit, server_default="in_transit")
    planned_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    planned_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = now()

    submissions: Mapped[list["PodSubmission"]] = relationship(back_populates="trip")


class PodSubmission(Base):
    __tablename__ = "pod_submissions"
    __table_args__ = (CheckConstraint("size_bytes <= 307200", name="ck_pod_size_300kb"),)
    id: Mapped[uuid.UUID] = pk()
    trip_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    storage_key: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lat: Mapped[float | None] = mapped_column(Float)
    lng: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(16), default="app")  # app | sms_link | office
    client_upload_id: Mapped[str] = mapped_column(String(64), unique=True)  # idempotency for offline retries
    ai_provider: Mapped[str | None] = mapped_column(String(32))
    ai_result: Mapped[dict | None] = mapped_column(JSONB)
    ai_confidence: Mapped[float | None] = mapped_column(Float)
    decision: Mapped[PodStatus] = mapped_column(_enum(PodStatus), default=PodStatus.uploaded)
    decision_reasons: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    corrected_fields: Mapped[dict | None] = mapped_column(JSONB)  # human overrides; image stays truth
    created_at: Mapped[datetime] = now()

    trip: Mapped[Trip] = relationship(back_populates="submissions")


class Expense(Base):
    """A cost the driver paid on the road (fuel, toll, repair...). Approved by the office before it counts in trip profit."""

    __tablename__ = "expenses"
    __table_args__ = (Index("ix_expenses_trip", "trip_id"), Index("ix_expenses_status", "status"), Index("ix_expenses_vehicle_time", "vehicle_id", "incurred_at"))
    id: Mapped[uuid.UUID] = pk()
    client_expense_id: Mapped[str] = mapped_column(String(64), unique=True)  # idempotency for retries
    trip_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("trips.id"))
    vehicle_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("vehicles.id"))
    driver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    category: Mapped[ExpenseCategory] = mapped_column(_enum(ExpenseCategory))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    litres: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    odometer_km: Mapped[int | None] = mapped_column(Integer)
    note: Mapped[str | None] = mapped_column(String(200))
    receipt_key: Mapped[str | None] = mapped_column(String(255))
    flags: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)  # e.g. low_mileage, odometer_backwards
    status: Mapped[ExpenseStatus] = mapped_column(_enum(ExpenseStatus), default=ExpenseStatus.pending)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_note: Mapped[str | None] = mapped_column(String(200))
    incurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = now()


class Advance(Base):
    """Cash given to a driver before/during a trip; settled against approved expenses."""

    __tablename__ = "advances"
    id: Mapped[uuid.UUID] = pk()
    driver_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), index=True)
    trip_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("trips.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    note: Mapped[str | None] = mapped_column(String(200))
    given_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    given_at: Mapped[datetime] = now()


class LocationPing(Base):
    """One GPS fix from a driver's phone during a trip. Personal data: kept for a limited time, office/MD only."""

    __tablename__ = "location_pings"
    __table_args__ = (UniqueConstraint("trip_id", "recorded_at", name="uq_ping_trip_time"), Index("ix_pings_trip_time", "trip_id", "recorded_at"))
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trip_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"))
    driver_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    lat: Mapped[float] = mapped_column(Float)
    lng: Mapped[float] = mapped_column(Float)
    accuracy_m: Mapped[float | None] = mapped_column(Float)
    speed_kmh: Mapped[float | None] = mapped_column(Float)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = now()


class AccessLink(Base):
    __tablename__ = "access_links"
    token: Mapped[str] = mapped_column(String(64), primary_key=True)
    trip_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"))
    kind: Mapped[LinkKind] = mapped_column(_enum(LinkKind))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = now()


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    action: Mapped[str] = mapped_column(String(60))
    entity: Mapped[str] = mapped_column(String(60))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    meta: Mapped[dict | None] = mapped_column(JSONB)
    at: Mapped[datetime] = now()
