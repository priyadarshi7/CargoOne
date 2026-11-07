"""SQLAlchemy 2.0 models. Consignee name/phone are personal data (DPDP Act 2023)."""
import enum
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
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
    client = "client"  # a shipper's own login: sees only their own shipments and requests


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
    code: Mapped[str | None] = mapped_column(String(8), unique=True)  # prefix of this branch's LR numbers, e.g. MH20


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
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")  # false = left the company: cannot sign in, not offered for planning
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vendors.id"))  # set for a hired driver
    client_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("clients.id"))  # set for a client's own login (role client)
    licence_no: Mapped[str | None] = mapped_column(String(30))  # driver only
    licence_expiry: Mapped[date | None] = mapped_column(Date)
    employment_type: Mapped[str | None] = mapped_column(String(16))  # company | contract | hired (driver only)
    assigned_vehicle_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vehicles.id"))  # the truck this driver normally drives
    created_at: Mapped[datetime] = now()


class Vendor(Base):
    """A transporter we hire trucks (and their drivers) from."""
    __tablename__ = "vendors"
    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(String(160), unique=True)
    contact_name: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(20))
    notes: Mapped[str | None] = mapped_column(String(300))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = now()


class Client(Base):
    __tablename__ = "clients"
    id: Mapped[uuid.UUID] = pk()
    name: Mapped[str] = mapped_column(String(160), unique=True)
    segment: Mapped[str | None] = mapped_column(String(60))
    billing_cycle: Mapped[str] = mapped_column(String(16), default="weekly")
    tally_ledger: Mapped[str | None] = mapped_column(String(160))
    contact_name: Mapped[str | None] = mapped_column(String(120))
    contact_phone: Mapped[str | None] = mapped_column(String(20))
    email: Mapped[str | None] = mapped_column(String(160))  # where invoices are sent (PII)
    gstin: Mapped[str | None] = mapped_column(String(15))
    language: Mapped[str] = mapped_column(String(2), default="en", server_default="en")  # what their shipment messages are written in
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Vehicle(Base):
    __tablename__ = "vehicles"
    id: Mapped[uuid.UUID] = pk()
    reg_no: Mapped[str] = mapped_column(String(20), unique=True)
    is_hired: Mapped[bool] = mapped_column(Boolean, default=False)
    vendor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("vendors.id"))  # who we hired it from
    vehicle_type: Mapped[str | None] = mapped_column(String(40))
    capacity_tonnes: Mapped[Decimal | None] = mapped_column(Numeric(5, 1))
    insurance_expiry: Mapped[date | None] = mapped_column(Date)
    fitness_expiry: Mapped[date | None] = mapped_column(Date)
    permit_expiry: Mapped[date | None] = mapped_column(Date)
    puc_expiry: Mapped[date | None] = mapped_column(Date)
    owner_name: Mapped[str | None] = mapped_column(String(160))  # registered owner on the RC
    rc_no: Mapped[str | None] = mapped_column(String(30))
    registration_date: Mapped[date | None] = mapped_column(Date)
    chassis_no: Mapped[str | None] = mapped_column(String(30))
    engine_no: Mapped[str | None] = mapped_column(String(30))
    insurance_no: Mapped[str | None] = mapped_column(String(40))
    availability: Mapped[str] = mapped_column(String(16), default="available", server_default="available")  # available | maintenance | breakdown
    availability_note: Mapped[str | None] = mapped_column(String(200))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")


class Document(Base):
    """A photo or PDF of a paper (driving licence, RC, insurance...). Personal data: private storage, role-checked access only."""

    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("owner_type", "owner_id", "kind", name="uq_document_slot"), Index("ix_documents_owner", "owner_type", "owner_id"))
    id: Mapped[uuid.UUID] = pk()
    owner_type: Mapped[str] = mapped_column(String(16))  # vehicle | driver
    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    kind: Mapped[str] = mapped_column(String(24))
    storage_key: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(40))
    size_bytes: Mapped[int] = mapped_column(Integer)
    uploaded_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = now()


class Invoice(Base):
    __tablename__ = "invoices"
    id: Mapped[uuid.UUID] = pk()
    invoice_no: Mapped[str] = mapped_column(String(40), unique=True)
    client_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clients.id"))
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    period_label: Mapped[str | None] = mapped_column(String(80))
    exported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # a person marked it as sent to the client: never automatic
    sent_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    tally_pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # the voucher is in Tally
    tally_voucher_no: Mapped[str | None] = mapped_column(String(40))  # Tally's own number for it (our invoice number is its Reference)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # set once the payments recorded cover the total
    created_at: Mapped[datetime] = now()


class Payment(Base):
    """Money received against an invoice. An invoice is paid when these add up to its total."""
    __tablename__ = "payments"
    id: Mapped[uuid.UUID] = pk()
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    paid_on: Mapped[date] = mapped_column(Date)
    reference: Mapped[str | None] = mapped_column(String(80))  # UTR / cheque number
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = now()


class OnlinePayment(Base):
    """One Razorpay order for an invoice. A payment is applied once: the Razorpay payment id is unique, so the checkout return, the webhook and a retry can all arrive and only one counts."""
    __tablename__ = "online_payments"
    id: Mapped[uuid.UUID] = pk()
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    order_id: Mapped[str] = mapped_column(String(40), unique=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2))
    status: Mapped[str] = mapped_column(String(10), default="created", server_default="created")  # created | paid | review (money taken but it no longer fits the invoice)
    provider_payment_id: Mapped[str | None] = mapped_column(String(40), unique=True)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))  # the payment recorded on the invoice
    method: Mapped[str | None] = mapped_column(String(20))
    note: Mapped[str | None] = mapped_column(String(200))
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at: Mapped[datetime] = now()
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WebhookEvent(Base):
    """Razorpay sends the same event more than once; the id is remembered so each is handled once."""
    __tablename__ = "webhook_events"
    event_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    kind: Mapped[str] = mapped_column(String(40))
    received_at: Mapped[datetime] = now()


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
    origin_lat: Mapped[float | None] = mapped_column(Float)  # the exact place picked from the suggestions; None when it was typed freely
    origin_lng: Mapped[float | None] = mapped_column(Float)
    destination_lat: Mapped[float | None] = mapped_column(Float)
    destination_lng: Mapped[float | None] = mapped_column(Float)
    freight_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    consignee_name: Mapped[str | None] = mapped_column(String(160))  # PII
    consignee_phone: Mapped[str | None] = mapped_column(String(20))  # PII
    consignee_email: Mapped[str | None] = mapped_column(String(160))  # PII; the shipment link goes here too
    consignee_language: Mapped[str | None] = mapped_column(String(2))  # what the receiver's messages and page are written in; empty = the client's language
    material: Mapped[str | None] = mapped_column(String(160))  # goods description on the LR
    weight_tonnes: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    packages: Mapped[int | None] = mapped_column(Integer)
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
    arrived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # the driver said the truck is at the delivery point
    eway_valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # printed on the e-way bill: the load must arrive before it
    cancel_reason: Mapped[str | None] = mapped_column(String(300))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # the driver opened and accepted the job
    loaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    loading_photo_key: Mapped[str | None] = mapped_column(String(255))  # the loaded truck and LR, as the driver left the pickup
    delivery_code: Mapped[str | None] = mapped_column(String(4))  # the receiver reads this out to the driver: proof of who received
    delivery_code_tries: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    delivery_code_locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivery_override: Mapped[str | None] = mapped_column(String(200))  # why the office confirmed delivery without the receiver's code
    delivery_issue: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")  # shortage or damage noted at the door
    delivery_note: Mapped[str | None] = mapped_column(String(300))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # delivered, proven, invoiced and paid: nothing changes after this
    link_epoch: Mapped[int] = mapped_column(Integer, default=0, server_default="0")  # bumped to retire every shipment link of this trip
    late_alert_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = now()

    submissions: Mapped[list["PodSubmission"]] = relationship(back_populates="trip")


class TripEvent(Base):
    """What happened to a trip, in order. The shipment page shows the `public` ones; the rest is the office's audit trail."""
    __tablename__ = "trip_events"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    trip_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("trips.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(24))
    at: Mapped[datetime] = now()
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    note: Mapped[str | None] = mapped_column(String(300))
    public: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    meta: Mapped[dict | None] = mapped_column(JSONB)


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


class Notification(Base):
    """A message inside the app for one person (shown in the driver's inbox)."""

    __tablename__ = "notifications"
    __table_args__ = (Index("ix_notifications_user_time", "user_id", "created_at"),)
    id: Mapped[uuid.UUID] = pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(24))  # welcome | trip_assigned | trip_update
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(String(600))
    link: Mapped[str | None] = mapped_column(String(200))  # an in-app path, e.g. /driver?trip=...
    trip_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("trips.id", ondelete="SET NULL"))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = now()


class PushSubscription(Base):
    """One phone's permission to be alerted by Web Push. The endpoint is the address the browser's push service gave this phone."""

    __tablename__ = "push_subscriptions"
    id: Mapped[uuid.UUID] = pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    endpoint: Mapped[str] = mapped_column(String(600), unique=True)
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    user_agent: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = now()
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Message(Base):
    """A WhatsApp message we tried to send: what, to whom, and what the provider answered. Secrets in links are cut out of `body`."""

    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_time", "created_at"),)
    id: Mapped[uuid.UUID] = pk()
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    trip_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("trips.id", ondelete="SET NULL"))
    channel: Mapped[str] = mapped_column(String(12), default="whatsapp")
    template: Mapped[str] = mapped_column(String(40))
    provider: Mapped[str] = mapped_column(String(12))  # mock | meta
    status: Mapped[str] = mapped_column(String(12))  # sent | simulated | failed | skipped
    provider_id: Mapped[str | None] = mapped_column(String(80))
    error: Mapped[str | None] = mapped_column(String(200))
    to_masked: Mapped[str | None] = mapped_column(String(20))
    body: Mapped[str] = mapped_column(String(1200))
    created_at: Mapped[datetime] = now()


class OnboardingLink(Base):
    """One-time link that lets a newly registered driver choose their own PIN and open the app. Only the SHA-256 is stored."""

    __tablename__ = "onboarding_links"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = now()


class TransportRequest(Base):
    """A company asking for transport through the public request page. Ops reviews it, onboards the company as a client, and books a trip."""

    __tablename__ = "transport_requests"
    __table_args__ = (Index("ix_requests_status_time", "status", "created_at"),)
    id: Mapped[uuid.UUID] = pk()
    reference: Mapped[str] = mapped_column(String(16), unique=True)  # what the requester quotes, e.g. REQ-1001
    company_name: Mapped[str] = mapped_column(String(160))
    contact_name: Mapped[str] = mapped_column(String(120))  # PII
    phone: Mapped[str] = mapped_column(String(20))  # PII
    email: Mapped[str | None] = mapped_column(String(160))  # PII
    gstin: Mapped[str | None] = mapped_column(String(15))
    language: Mapped[str] = mapped_column(String(2), default="en")
    origin: Mapped[str] = mapped_column(String(120))
    destination: Mapped[str] = mapped_column(String(120))
    origin_lat: Mapped[float | None] = mapped_column(Float)  # the exact place picked from the suggestions; None when it was typed freely
    origin_lng: Mapped[float | None] = mapped_column(Float)
    destination_lat: Mapped[float | None] = mapped_column(Float)
    destination_lng: Mapped[float | None] = mapped_column(Float)
    material: Mapped[str] = mapped_column(String(160))
    weight_tonnes: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    truck_type: Mapped[str | None] = mapped_column(String(60))
    pickup_date: Mapped[date] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(12), default="new")  # new | accepted | booked | declined
    client_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("clients.id"))
    trip_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("trips.id", ondelete="SET NULL"))
    quote_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    quote_accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # the requester agreed to the quote (online or told to the office)
    quote_accepted_via: Mapped[str | None] = mapped_column(String(12))  # online | phone
    ops_note: Mapped[str | None] = mapped_column(String(300))  # shown to the requester
    declined_by: Mapped[str | None] = mapped_column(String(8))  # office | client (the client said no to the quote)
    decline_reason: Mapped[str | None] = mapped_column(String(300))
    decline_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # the office has looked at a client's no
    quote_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # when the current quote went to the client
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # agreed to be contacted about this request
    created_at: Mapped[datetime] = now()
