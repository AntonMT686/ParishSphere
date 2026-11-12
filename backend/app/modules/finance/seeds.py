"""Default finance categories (from the product brief) and a parish cash account."""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.finance.models import FinAccount, FinCategory
from app.tenancy.seed import register_seeder

CATEGORIES: tuple[tuple[str, str, str, str], ...] = (
    ("INCOME", "DONATION", "Donations", "நன்கொடைகள்"),
    ("INCOME", "OFFERING", "Offerings / Sunday collection", "காணிக்கை"),
    ("INCOME", "MEMBERSHIP", "Membership contributions", "உறுப்பினர் சந்தா"),
    ("INCOME", "FESTIVAL_COLLECTION", "Festival collections", "திருவிழா வசூல்"),
    ("INCOME", "SPECIAL_CONTRIBUTION", "Special contributions", "சிறப்பு பங்களிப்பு"),
    ("INCOME", "OTHER_INCOME", "Other income", "பிற வரவு"),
    ("EXPENSE", "MAINTENANCE", "Church maintenance", "ஆலயப் பராமரிப்பு"),
    ("EXPENSE", "FESTIVAL_EXPENSE", "Festival expenses", "திருவிழா செலவு"),
    ("EXPENSE", "CHARITY", "Charity", "அறப்பணி"),
    ("EXPENSE", "ADMINISTRATIVE", "Administrative expenses", "நிர்வாகச் செலவு"),
    ("EXPENSE", "SOCIETY_EXPENSE", "Society expenses", "சங்கச் செலவு"),
    ("EXPENSE", "ANBIYAM_EXPENSE", "Anbiyam expenses", "அன்பியச் செலவு"),
    ("EXPENSE", "OTHER_EXPENSE", "Other expenses", "பிற செலவு"),
)


@register_seeder("finance.defaults", order=70)
def seed_finance(session: Session, _: dict[str, Any]) -> None:
    have = set(session.scalars(select(FinCategory.code)))
    for i, (kind, code, name, local) in enumerate(CATEGORIES):
        if code not in have:
            session.add(
                FinCategory(
                    code=code, name=name, name_local=local, kind=kind, sort_order=(i + 1) * 10, is_system=True
                )
            )
    if session.scalar(select(FinAccount.id).limit(1)) is None:
        today = date.today()
        session.add(
            FinAccount(code="CASH", name="Parish cash", kind="CASH", opening_date=date(today.year, 1, 1))
        )
