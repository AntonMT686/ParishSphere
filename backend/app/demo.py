# ruff: noqa: E501  (demo data reads best one record per line)
"""Demo parish data (``ps-admin seed-demo``).

Builds a realistic, self-consistent parish by driving the real API in-process, so every record passes
the same validation, permissions, approval workflows, audit and notifications as in production:
staff and leaders with their roles (through office-bearer posts and the Parish Priest assignment),
Anbiyam / societies / committees, ~30 registered families, four months of approved finance with
released statements, activities, meetings with minutes, action items and notices, plus a few items
deliberately left waiting for approval so the dashboards and "My Approvals" have something to show.

Dates are relative to today. Safe to re-run: a parish that already has families is left untouched.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db.tenant import TenantDescriptor, tenant_session_scope

DEMO_USERS: tuple[tuple[str, str], ...] = (
    ("frjoseph", "Parish Priest – final approvals, everything"),
    ("raj", "Parish President (Council President)"),
    ("mary", "Parish Secretary (Council Secretary) – registers, notices, meetings"),
    ("peter", "Parish Treasurer (Council Treasurer) – accounts, statements"),
    ("anitha", "Anbiyam Leader – St. Joseph Anbiyam"),
    ("jerome", "Youth Society President – reviews the society's activities and minutes"),
    ("kevin", "Youth Society Secretary – society activities and meetings"),
    ("thomas", "Parishioner – own family, donations, notices"),
)

ANBIYAMS = (
    "St. Joseph Anbiyam",
    "St. Anne Anbiyam",
    "St. Thomas Anbiyam",
    "Holy Family Anbiyam",
    "St. Sebastian Anbiyam",
)
SURNAMES = (
    "Arokiasamy", "Fernando", "Dias", "Rayappan", "Savarimuthu", "Gnanaprakasam", "Pereira", "Amalraj",
    "Susai", "Irudayaraj", "Chinnappan", "D'Souza", "Antonysamy", "Lourdusamy", "Selvaraj", "Michael",
    "Xavier", "Britto", "Fernandez", "Joseph", "Arulanandam", "Maria Doss", "Ignatius", "Packiam",
    "Rozario", "Soosai", "Thangaraj", "Valan", "Yesudas", "Charles",
)  # fmt: skip
MEN = ("John", "Antony", "Xavier", "Joseph", "Arul", "Selvam", "Paul", "Michael", "Francis", "Raja", "Lourdu", "Charles", "Stephen", "Peter", "Vincent")  # fmt: skip
WOMEN = ("Mary", "Rita", "Anne", "Stella", "Grace", "Jasmine", "Lucy", "Rosy", "Jacintha", "Philomena", "Sahaya Mary", "Agnes")  # fmt: skip
SONS = ("Kevin", "Jerome", "Jude", "Ashwin", "Roshan", "Arun", "Benedict")
DAUGHTERS = ("Ann", "Merlin", "Sharon", "Jenifer", "Priya", "Teresa", "Angel")


class DemoError(RuntimeError):
    pass


class Api:
    """Thin wrapper over an in-process client: one cached sign-in per user, errors raised loudly."""

    def __init__(self, client: TestClient, parish_code: str, password: str) -> None:
        self.c = client
        self.base = {"X-Parish-Code": parish_code}
        self.password = password
        self.tokens: dict[str, str] = {}

    def h(self, user: str) -> dict[str, str]:
        if user not in self.tokens:
            pw = self.password
            r = self.c.post("/api/v1/auth/login", json={"username": user, "password": pw}, headers=self.base)
            if r.status_code != 200:
                raise DemoError(f"sign-in as {user} failed: {r.text}")
            self.tokens[user] = r.json()["access_token"]
        return {**self.base, "Authorization": f"Bearer {self.tokens[user]}"}

    def call(
        self, method: str, user: str, path: str, body: Any = None, ok: tuple[int, ...] = (200, 201, 204)
    ) -> Any:
        r = self.c.request(method, f"/api/v1{path}", json=body, headers=self.h(user))
        if r.status_code not in ok:
            raise DemoError(f"{method} {path} as {user} → {r.status_code}: {r.text[:500]}")
        return (
            r.json()
            if r.content and r.headers.get("content-type", "").startswith("application/json")
            else None
        )

    def get(self, user: str, path: str) -> Any:
        return self.call("GET", user, path)

    def post(self, user: str, path: str, body: Any = None) -> Any:
        return self.call("POST", user, path, body if body is not None else {})

    def put(self, user: str, path: str, body: Any) -> Any:
        return self.call("PUT", user, path, body)

    def approve(self, *users: str, rounds: int = 6) -> int:
        """Approve every task waiting with these users, repeatedly, until nothing is left."""
        done = 0
        for _ in range(rounds):
            acted = 0
            for u in users:
                for t in self.get(u, "/workflow/tasks?size=100")["items"]:
                    self.post(
                        u, f"/workflow/tasks/{t['id']}/act", {"action": "APPROVE", "comment": "Approved."}
                    )
                    acted += 1
            done += acted
            if not acted:
                break
        return done


def seed_demo(
    tenant: TenantDescriptor, admin_username: str, password: str, log: Callable[[str], None] = print
) -> bool:
    """Fill ``tenant`` with demo data. Returns False (and does nothing) if it already has families."""
    from app.main import create_app
    from app.modules.identity.models import User
    from app.modules.people.models import Family

    with tenant_session_scope(tenant) as s:
        if s.scalar(select(func.count()).select_from(Family)):
            log(f"{tenant.code} already has families – demo data not added")
            return False
        admin = s.scalar(select(User).where(User.username == admin_username.lower()))
        if admin is None:
            raise DemoError(f"Administrator {admin_username!r} not found in {tenant.code}")
    rnd = random.Random(2026)  # noqa: S311  (repeatable demo data, not security)
    today = date.today()
    with TestClient(create_app(), base_url="http://localhost") as client:
        api = Api(client, tenant.code, password)
        _build(api, tenant, admin_username.lower(), password, today, rnd, log)
    return True


def _build(
    api: Api,
    tenant: TenantDescriptor,
    admin: str,
    password: str,
    today: date,
    rnd: random.Random,
    log: Callable[[str], None],
) -> None:
    from app.common.ratelimit import counter
    from app.modules.identity.models import User
    from app.modules.people.models import Member

    _admin_password_check(api, admin)

    # ------------------------------------------------------------------ parish profile & users
    api.call("PATCH", admin, "/parish/profile", {
        "address_line1": "12 Santhome High Road", "city": "Chennai", "state": "Tamil Nadu", "postal_code": "600004",
        "phone": "+91 44 2498 0000", "email": "office@stmarys.example.org", "established_on": "1923-08-15", "patron_saint": "Our Lady of Good Health",
    })  # fmt: skip
    people = {
        "frjoseph": ("Fr. Joseph Antony", []),
        "raj": ("Raj Kumar", []),
        "mary": ("Mary Selvi", []),
        "peter": ("Peter Lourdu", []),
        "anitha": ("Anitha Xavier", []),
        "jerome": ("Jerome Fernando", []),
        "kevin": ("Kevin Britto", []),
        "thomas": ("Thomas Arokiasamy", ["GENERAL_MEMBER"]),
    }
    ids: dict[str, str] = {}
    for username, (name, roles) in people.items():
        u = api.post(
            admin,
            "/users",
            {"username": username, "full_name": name, "password": password, "role_codes": roles},
        )
        ids[username] = u["id"]
    with tenant_session_scope(tenant) as s:
        for u in s.scalars(select(User).where(User.username.in_(people.keys()))):
            u.must_change_password = False
    log("users created")

    # Clergy: the Parish Priest assignment grants frjoseph the Parish Priest role.
    pp = api.post(
        admin,
        "/priests",
        {"full_name": "Joseph Antony", "ordination_date": "2004-04-24", "home_diocese": "Madras-Mylapore"},
    )
    api.post(
        admin,
        f"/priests/{pp['id']}/assignments",
        {"role": "PARISH_PRIEST", "appointed_on": str(today - timedelta(days=900))},
    )
    api.post(admin, f"/priests/{pp['id']}/user", {"user_id": ids["frjoseph"]})
    ap = api.post(
        admin,
        "/priests",
        {
            "full_name": "Arul Raj",
            "ordination_date": "2019-05-01",
            "clergy_type": "RELIGIOUS",
            "congregation": "SDB",
        },
    )
    api.post(
        admin,
        f"/priests/{ap['id']}/assignments",
        {"role": "ASSISTANT_PRIEST", "appointed_on": str(today - timedelta(days=300))},
    )

    # ------------------------------------------------------------------ organisations & office bearers
    def unit(type_code: str, name: str, **kw: Any) -> str:
        return api.post(admin, "/org-units", {"type_code": type_code, "name": name, **kw})["id"]

    council = unit("COUNCIL", "Parish Council", meeting_schedule="First Sunday, after the 9 am Mass")
    anb = {n: unit("ANBIYAM", n, meeting_schedule="Second Friday, 7 pm") for n in ANBIYAMS}
    youth = unit("SOCIETY", "Youth Society", meeting_schedule="Every Saturday, 5 pm")
    legion = unit("SOCIETY", "Legion of Mary")
    vincent = unit("SOCIETY", "St. Vincent de Paul Society")
    women = unit("SABAI", "Women's Sabai")
    liturgy = unit("COMMITTEE", "Liturgy Committee")
    unit("COMMITTEE", "Festival Committee")
    for pos, user in (("PRESIDENT", "raj"), ("SECRETARY", "mary"), ("TREASURER", "peter")):
        api.post(admin, f"/org-units/{council}/office-bearers", {"position_code": pos, "user_id": ids[user]})
    api.post(
        admin,
        f"/org-units/{anb['St. Joseph Anbiyam']}/office-bearers",
        {"position_code": "PRESIDENT", "user_id": ids["anitha"]},
    )
    api.post(
        admin, f"/org-units/{youth}/office-bearers", {"position_code": "SECRETARY", "user_id": ids["kevin"]}
    )
    api.post(
        admin,
        f"/org-units/{youth}/office-bearers",
        {"position_code": "PRESIDENT", "user_id": ids["jerome"]},
    )
    log("organisations created")

    # ------------------------------------------------------------------ families & members
    def born(age: int) -> date:
        return today.replace(year=today.year - age) - timedelta(days=rnd.randint(1, 360))

    def after(d: date, years: int, spread_days: int = 120) -> str | None:
        """A date ``years`` after ``d`` (plus a little), or None if that is still in the future."""
        try:
            x = d.replace(year=d.year + years) + timedelta(days=rnd.randint(0, spread_days))
        except ValueError:  # 29 February
            x = d.replace(day=28, year=d.year + years)
        return str(x) if x <= today else None

    def person(dob: date, **kw: Any) -> dict[str, Any]:
        out: dict[str, Any] = {"date_of_birth": str(dob), **kw}
        place = "St. Mary's Church"
        for key, years, spread in (("baptism", 0, 90), ("communion", 9, 300), ("confirmation", 15, 300)):
            when = after(dob, years, spread) if years else str(dob + timedelta(days=rnd.randint(14, spread)))
            if when and when <= str(today):
                out |= {f"{key}_date": when, f"{key}_place": place}
        return out

    families: list[dict[str, Any]] = []
    youth_members: list[str] = []
    women_members: list[str] = []
    anb_ids = list(anb.values())
    for i, last in enumerate(SURNAMES):
        head_age = rnd.randint(30, 78)
        head = MEN[i % len(MEN)] if i != 1 else "Thomas"
        wife = WOMEN[i % len(WOMEN)]
        head_dob, wife_dob = born(head_age), born(head_age - 4)
        wedding = after(head_dob, rnd.randint(25, 30), 300) or str(today - timedelta(days=30))
        members = [
            person(head_dob, first_name=head, last_name=last, gender="M", relationship_to_head="HEAD",
                   phone=f"98400{50000 + i:05d}", occupation=rnd.choice(("Teacher", "Engineer", "Business", "Farmer", "Driver", "Accountant")),
                   marital_status="MARRIED", marriage_date=wedding, marriage_place="St. Mary's Church",
                   marriage_register_ref=f"M/{wedding[:4]}/{rnd.randint(1, 90):02d}"),
            person(wife_dob, first_name=wife, last_name=last, gender="F", relationship_to_head="SPOUSE",
                   marital_status="MARRIED", marriage_date=wedding, marriage_place="St. Mary's Church"),
        ]  # fmt: skip
        if head_age < 68:
            for k in range(rnd.randint(0, 3)):
                kid_age = rnd.randint(2, max(3, min(28, head_age - 26)))
                son = rnd.random() < 0.5
                members.append(person(born(kid_age), first_name=(SONS if son else DAUGHTERS)[(i + k) % 7], last_name=last,
                                      gender="M" if son else "F", relationship_to_head="SON" if son else "DAUGHTER"))  # fmt: skip
        elif rnd.random() < 0.5:
            members.pop(1)  # widower
            members[0]["marital_status"] = "WIDOWED"
        fam = api.post("mary", "/families", {
            "family_name": last, "phone": f"+91 98400{10000 + i:05d}", "address_line1": f"{i + 3}, {rnd.choice(('Church Street', 'Santhome High Road', 'Luz Avenue', 'Kutchery Road'))}",
            "city": "Chennai", "postal_code": "600004", "anbiyam_id": None if i in (28, 29) else anb_ids[i % len(anb_ids)],
            "registered_on": str(today - timedelta(days=rnd.randint(40, 2000))) if i < 26 else str(today - timedelta(days=rnd.randint(0, 10))),
            "members": members, "confirm_not_duplicate": True,
        })  # fmt: skip
        families.append(fam)
        for m in fam["members"]:
            age = m.get("age")
            if m["relationship_to_head"] in ("SON", "DAUGHTER") and age and 15 <= age <= 30:
                youth_members.append(m["id"])
            if m["gender"] == "F" and m["relationship_to_head"] == "SPOUSE" and len(women_members) < 14:
                women_members.append(m["id"])
    for mid in youth_members:
        api.post(
            admin,
            f"/org-units/{youth}/memberships",
            {"member_id": mid, "joined_on": str(today - timedelta(days=200))},
        )
    for mid in women_members:
        api.post(admin, f"/org-units/{women}/memberships", {"member_id": mid})
    for mid in women_members[:6]:
        api.post(admin, f"/org-units/{legion}/memberships", {"member_id": mid})
    for fam in families[:5]:
        api.post(admin, f"/org-units/{vincent}/memberships", {"member_id": fam["members"][0]["id"]})
    with tenant_session_scope(tenant) as s:  # the parishioner login belongs to the Fernando family's head
        thomas = s.scalar(select(Member).where(Member.first_name == "Thomas", Member.last_name == "Fernando"))
        user = s.scalar(select(User).where(User.username == "thomas"))
        if thomas and user:
            user.member_id = thomas.id
    log(f"{len(families)} families registered")

    # ------------------------------------------------------------------ finance: four months of history
    cats = {c["code"]: c["id"] for c in api.get("peter", "/finance/categories")}
    cash = next(a["id"] for a in api.get("peter", "/finance/accounts") if a["code"] == "CASH")
    start = (today.replace(day=1) - timedelta(days=95)).replace(day=1)
    bank = api.post("peter", "/finance/accounts", {
        "code": "IOB", "name": "Indian Overseas Bank – SB", "kind": "BANK", "bank_name": "Indian Overseas Bank",
        "account_number_masked": "XXXX4417", "opening_balance": "182500.00", "opening_date": str(start - timedelta(days=1)),
    })["id"]  # fmt: skip
    youth_cash = api.post("peter", "/finance/accounts", {
        "code": "YOUTH", "name": "Youth Society cash", "kind": "CASH", "org_unit_id": youth,
        "opening_balance": "3500.00", "opening_date": str(start - timedelta(days=1)),
    })["id"]  # fmt: skip

    def entry(kind: str, cat: str | None, acct: str, amount: int, when: date, text: str, **kw: Any) -> None:
        body = {"txn_date": str(when), "kind": kind, "category_id": cats.get(cat) if cat else None, "account_id": acct,
                "amount": str(amount), "description": text, "payment_method": kw.pop("method", "CASH"), **kw}  # fmt: skip
        t = api.post("peter", "/finance/transactions", body)
        api.post("peter", f"/finance/transactions/{t['id']}/submit")

    d, n = start, 0
    while d <= today:
        if d.weekday() == 6:
            entry("INCOME", "OFFERING", cash, rnd.randint(9, 16) * 500, d, "Sunday collection – all Masses")
            n += 1
            if rnd.random() < 0.7:
                fam = rnd.choice(families)
                entry("INCOME", "DONATION", bank, rnd.choice((1000, 2000, 2500, 5000, 10000)), d,
                      "Donation for the church renovation", family_id=fam["id"], payer_payee=f"{fam['family_name']} family", method="UPI")  # fmt: skip
                n += 1
            if rnd.random() < 0.6:
                cat = rnd.choice(("MAINTENANCE", "CHARITY", "ADMINISTRATIVE"))
                text = {
                    "MAINTENANCE": "Electrical repairs – church hall",
                    "CHARITY": "Assistance to needy families",
                    "ADMINISTRATIVE": "Office stationery and printing",
                }[cat]
                entry("EXPENSE", cat, cash, rnd.randint(8, 45) * 100, d, text, payer_payee="Local vendor")
                n += 1
        if d.day == 5:
            entry("INCOME", "MEMBERSHIP", cash, rnd.randint(30, 60) * 100, d, "Anbiyam monthly contributions")
            entry(
                "EXPENSE",
                "ADMINISTRATIVE",
                bank,
                18000,
                d,
                "Salary – parish office assistant",
                method="BANK_TRANSFER",
                payer_payee="Office staff",
            )
            n += 2
        if d.day == 15:
            entry(
                "EXPENSE",
                "SOCIETY_EXPENSE",
                youth_cash,
                rnd.randint(8, 20) * 100,
                d,
                "Youth Society – snacks and materials",
                org_unit_id=youth,
                payer_payee="Youth Society",
            )
            n += 1
        d += timedelta(days=1)
    api.approve("peter", "frjoseph", "raj", "mary")
    log(f"{n} finance entries approved")

    # Month end: the oldest two full months released, the last full month waiting with the Parish Priest.
    months = []
    m = start
    while m < today.replace(day=1):
        months.append(f"{m:%Y-%m}")
        m = (m.replace(day=28) + timedelta(days=5)).replace(day=1)
    for key in months[:-1]:  # the last full month is closed at the very end and left with the Priest
        api.post(
            "peter",
            f"/finance/periods/{key}/close",
            {"comment": "All entries checked against the cash book."},
        )
        api.approve("frjoseph")
        api.post("frjoseph", f"/finance/periods/{key}/release")
    log(f"statements released for {', '.join(months[:-1])}")

    # ------------------------------------------------------------------ activities, meetings, action items
    def activity(
        user: str,
        org: str | None,
        title: str,
        offset: int,
        cat: str,
        amount: int | None = None,
        submit: bool = True,
    ) -> str:
        a = api.post(user, "/activities", {
            "org_unit_id": org, "title": title, "category": cat, "activity_date": str(today + timedelta(days=offset)),
            "location": rnd.choice(("Parish hall", "Church grounds", "St. Mary's School auditorium")),
            "planned_details": f"{title}: programme, volunteers and logistics as discussed in the meeting.",
            "planned_amount": str(amount) if amount else None, "responsible_name": None,
        })["id"]  # fmt: skip
        if submit:
            api.post(user, f"/activities/{a}/submit")
        return a

    done = [
        activity("kevin", youth, "Career guidance camp", -25, "EDUCATIONAL", 12000),
        activity("anitha", anb["St. Joseph Anbiyam"], "Anbiyam family prayer and rosary", -12, "SPIRITUAL"),
        activity("mary", None, "Parish blood donation camp", -40, "SOCIAL", 8000),
    ]
    activity("kevin", youth, "Youth retreat at Kodaikanal", 12, "SPIRITUAL", 35000)
    activity("mary", None, "Parish feast novena", 20, "LITURGICAL", 60000)
    staff = ("jerome", "raj", "mary", "frjoseph", "anitha")
    api.approve(*staff)
    for a, (text, people_count, spent) in zip(done, (("68 youth attended; three career counsellors.", 68, 11200),
                                                     ("22 families attended.", 22, None), ("41 donors; 38 units collected.", 41, 7450)), strict=True):  # fmt: skip
        api.post("kevin" if a == done[0] else "anitha" if a == done[1] else "mary", f"/activities/{a}/complete",
                 {"actual_details": text, "participant_count": people_count, "actual_amount": str(spent) if spent else None})  # fmt: skip

    def meeting(user: str, org: str | None, title: str, offset_days: int, agenda: list[str]) -> str:
        when = datetime.combine(today + timedelta(days=offset_days), datetime.min.time()).replace(hour=18)
        return api.post(user, "/meetings", {"org_unit_id": org, "title": title, "scheduled_at": when.isoformat(),
                                            "location": "Parish hall", "agenda": [{"title": x} for x in agenda], "notify": offset_days > 0})["id"]  # fmt: skip

    council_mtg = meeting(
        "mary",
        council,
        "Parish Council monthly meeting",
        -6,
        ["Feast preparations", "Roof repair estimate", "Youth retreat"],
    )
    meeting(
        "mary",
        liturgy,
        "Liturgy Committee – Christmas planning",
        5,
        ["Christmas Mass schedule", "Choir practice"],
    )
    meeting("kevin", youth, "Youth Society monthly meeting", 9, ["Retreat registrations", "Christmas carols"])
    att = api.get("mary", f"/meetings/{council_mtg}/attendance")
    if att["rows"]:
        api.put(
            "mary",
            f"/meetings/{council_mtg}/attendance",
            {"rows": [{**r, "status": "PRESENT"} for r in att["rows"]]},
        )
    api.put("mary", f"/meetings/{council_mtg}/minutes", {
        "summary": "The meeting opened with a prayer led by the Parish Priest. 14 members were present.",
        "points": [{"topic": "Feast preparations", "discussion": "Novena preachers confirmed; decorations by the Youth Society."},
                   {"topic": "Roof repair estimate", "discussion": "Two quotations received; the lower one (₹62,000) recommended."}],
        "resolutions": [{"text": "Approve the roof repair at ₹62,000 subject to the Parish Priest's approval.", "decision": "PASSED"},
                        {"text": "Hold the youth retreat in Kodaikanal.", "decision": "PASSED"}],
    })  # fmt: skip
    api.post("mary", f"/meetings/{council_mtg}/minutes/submit")
    api.approve(*staff)
    for title, user, due, org in (
        ("Collect a third quotation for the roof", "peter", -3, council),
        ("Book buses for the youth retreat", "kevin", 6, youth),
        ("Print the feast novena booklet", "mary", 10, council),
    ):
        api.post("mary" if org == council else "kevin", "/action-items", {
            "title": title, "org_unit_id": org, "meeting_id": council_mtg if org == council else None,
            "owner_user_id": ids[user], "due_date": str(today + timedelta(days=due)),
        })  # fmt: skip
    log("activities, meetings and action items created")

    # ------------------------------------------------------------------ notices
    def notice(title: str, body: str, category: str, **kw: Any) -> str:
        n = api.post("mary", "/notices", {"title": title, "body": body, "category": category, **kw})["id"]
        api.post("mary", f"/notices/{n}/submit")
        return n

    notice("Christmas Mass timings", "Midnight Mass on 24 December at 11:30 pm.\nChristmas Day: 7 am (Tamil) and 9 am (English).\nConfessions on 23 December from 5 pm.",
           "WEEKLY", is_important=True, is_public=True, title_local="கிறிஸ்துமஸ் திருப்பலி நேரங்கள்",
           body_local="டிசம்பர் 24 இரவு 11:30 மணிக்கு நள்ளிரவு திருப்பலி.\nகிறிஸ்துமஸ் தினம்: காலை 7 மணி (தமிழ்), 9 மணி (ஆங்கிலம்).")  # fmt: skip
    notice(
        "Parish feast novena begins",
        "The novena for our parish feast begins on Friday at 6 pm. All families are invited.",
        "EVENT",
        is_public=True,
    )
    notice(
        "Youth retreat registrations open",
        "Register with Kevin before Sunday. Fee ₹500.",
        "EVENT",
        audience_all=False,
        audience_org_units=[youth],
    )
    notice("Catechism classes resume", "Sunday catechism classes resume next week after the 9 am Mass.", "ANNOUNCEMENT",
           publish_at=(datetime.combine(today + timedelta(days=3), datetime.min.time()).replace(hour=8)).isoformat())  # fmt: skip
    api.approve(*staff)
    log("notices published")

    # ------------------------------------------------------------------ left waiting, for the demo
    counter().reset()
    entry(
        "EXPENSE",
        "MAINTENANCE",
        bank,
        62000,
        today,
        "Church roof repair – advance to contractor",
        method="BANK_TRANSFER",
        payer_payee="Sri Balaji Constructions",
    )
    # Treasurer, then President & Secretary (₹50,000 and above); now with the Parish Priest.
    api.approve("peter", "raj", "mary")
    # Last month: closed by the Treasurer, statement waiting for the Parish Priest's approval.
    api.post(
        "peter",
        f"/finance/periods/{months[-1]}/close",
        {"comment": "All entries checked against the cash book."},
    )
    activity("kevin", youth, "Christmas carol rounds", 30, "CULTURAL", 6000)
    notice(
        "Volunteers needed for the feast",
        "Volunteers are needed for decoration and crowd management. Contact the parish office.",
        "ANNOUNCEMENT",
    )
    youth_mtg = meeting(
        "kevin", youth, "Youth Society planning meeting", -3, ["Carol rounds", "Retreat budget"]
    )
    api.put("kevin", f"/meetings/{youth_mtg}/minutes", {
        "summary": "Planning for Christmas carol rounds and the retreat budget.",
        "points": [{"topic": "Carol rounds", "discussion": "Four groups, one per Anbiyam zone."}],
        "resolutions": [{"text": "Request ₹6,000 for carol rounds.", "decision": "PASSED"}],
    })  # fmt: skip
    api.post("kevin", f"/meetings/{youth_mtg}/minutes/submit")
    api.approve("jerome")  # carol rounds → Parish Secretary; minutes → Parish Priest
    log(
        f"left waiting for the demo: roof repair (₹62,000), {months[-1]} statement, carol rounds, a notice, youth minutes"
    )


def _admin_password_check(api: Api, admin: str) -> None:
    """The administrator must be able to sign in with the demo password (the one given to provision-parish)."""
    api.h(admin)
