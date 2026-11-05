"""Lorry receipt (LR) numbers: LR/<branch code>/<financial year>/<serial>, e.g. LR/MH20/26-27/000123.

The serial counts per branch code and financial year (April to March) and starts again at 000001 each April. It is taken with a
single database statement (insert-or-increment), so two people creating trips at the same moment can never get the same number,
and a number is never reused even if the trip is later cancelled: a gap in the sequence is normal, a duplicate is not."""
from datetime import UTC, datetime

from sqlalchemy import Column, Integer, String
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.billing.periods import financial_year
from app.config import get_settings
from app.db import Base
from app.models import Branch


class LrCounter(Base):
    __tablename__ = "lr_counters"
    code = Column(String(8), primary_key=True)
    fy = Column(String(5), primary_key=True)
    last_no = Column(Integer, nullable=False, default=0)


def lr_format(code: str, fy: str, serial: int) -> str:
    return f"LR/{code}/{fy}/{serial:06d}"


async def next_lr_no(session: AsyncSession, branch: Branch | None, when: datetime | None = None) -> str:
    code = (branch.code if branch is not None and branch.code else get_settings().default_branch_code).upper()
    fy = financial_year(when or datetime.now(UTC))
    stmt = insert(LrCounter).values(code=code, fy=fy, last_no=1)
    stmt = stmt.on_conflict_do_update(index_elements=[LrCounter.code, LrCounter.fy], set_={"last_no": LrCounter.last_no + 1}).returning(LrCounter.last_no)
    serial = (await session.execute(stmt)).scalar_one()
    return lr_format(code, fy, serial)
