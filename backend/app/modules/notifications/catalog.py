"""Notification events and their default templates (English & Tamil).

Templates use Jinja2 syntax (``{{ title }}``) rendered in a sandbox. ``subject`` becomes the in-app title
and email subject; ``body`` the in-app text and email body. Parishes may override any template per
channel and language (``notification_templates``).
"""

from __future__ import annotations

from dataclasses import dataclass, field

IN_APP, EMAIL, SMS, WHATSAPP = "IN_APP", "EMAIL", "SMS", "WHATSAPP"
CHANNELS = (IN_APP, EMAIL)  # SMS / WhatsApp providers are a phase-2 integration
LANGUAGES = ("en", "ta")


@dataclass(frozen=True)
class EventDef:
    code: str
    description: str
    variables: tuple[str, ...]
    templates: dict[str, tuple[str, str]]  # language → (subject, body)
    default_channels: frozenset[str] = field(default_factory=lambda: frozenset({IN_APP}))
    important: bool = False


def _e(code: str, description: str, variables: tuple[str, ...], en: tuple[str, str], ta: tuple[str, str],
       email: bool = False, important: bool = False) -> EventDef:  # fmt: skip
    channels = frozenset({IN_APP, EMAIL} if email else {IN_APP})
    return EventDef(code, description, variables, {"en": en, "ta": ta}, channels, important)


EVENTS: dict[str, EventDef] = {
    e.code: e
    for e in (
        _e("activity.submitted", "An activity was submitted for approval", ("actor", "title", "org_unit"),
           ("New activity submitted: {{ title }}", "{{ actor }} submitted the activity “{{ title }}” of {{ org_unit }}."),
           ("புதிய செயல்பாடு சமர்ப்பிக்கப்பட்டது: {{ title }}", "{{ org_unit }} இன் “{{ title }}” செயல்பாட்டை {{ actor }} சமர்ப்பித்துள்ளார்.")),
        _e("review.pending", "A record is waiting for your review", ("entity_label", "title", "stage", "submitted_by"),
           ("Review needed: {{ title }}", "{{ entity_label }} “{{ title }}” from {{ submitted_by }} is waiting for your review ({{ stage }})."),
           ("பரிசீலனை தேவை: {{ title }}", "{{ submitted_by }} அனுப்பிய {{ entity_label }} “{{ title }}” உங்கள் பரிசீலனைக்காக காத்திருக்கிறது ({{ stage }})."),
           email=True),
        _e("approval.pending", "A record is waiting for your approval", ("entity_label", "title", "stage", "submitted_by"),
           ("Approval needed: {{ title }}", "{{ entity_label }} “{{ title }}” from {{ submitted_by }} is waiting for your approval ({{ stage }})."),
           ("ஒப்புதல் தேவை: {{ title }}", "{{ submitted_by }} அனுப்பிய {{ entity_label }} “{{ title }}” உங்கள் ஒப்புதலுக்காக காத்திருக்கிறது ({{ stage }})."),
           email=True),
        _e("workflow.approved", "Your submission was approved", ("entity_label", "title"),
           ("Approved: {{ title }}", "Your {{ entity_label }} “{{ title }}” has been approved."),
           ("ஒப்புதல் அளிக்கப்பட்டது: {{ title }}", "உங்கள் {{ entity_label }} “{{ title }}” ஒப்புதல் பெற்றது."), email=True),
        _e("workflow.rejected", "Your submission was rejected", ("entity_label", "title", "comment"),
           ("Rejected: {{ title }}", "Your {{ entity_label }} “{{ title }}” was rejected.{% if comment %} Comment: {{ comment }}{% endif %}"),
           ("நிராகரிக்கப்பட்டது: {{ title }}", "உங்கள் {{ entity_label }} “{{ title }}” நிராகரிக்கப்பட்டது.{% if comment %} குறிப்பு: {{ comment }}{% endif %}"),
           email=True),
        _e("workflow.returned", "Your submission was returned for rework", ("entity_label", "title", "comment"),
           ("Rework requested: {{ title }}", "Your {{ entity_label }} “{{ title }}” was returned for changes.{% if comment %} Comment: {{ comment }}{% endif %}"),
           ("திருத்தம் தேவை: {{ title }}", "உங்கள் {{ entity_label }} “{{ title }}” திருத்தத்திற்காக திருப்பி அனுப்பப்பட்டது.{% if comment %} குறிப்பு: {{ comment }}{% endif %}"),
           email=True),
        _e("workflow.reminder", "A task waiting for you is overdue", ("entity_label", "title", "stage"),
           ("Reminder: {{ title }} is waiting for you", "{{ entity_label }} “{{ title }}” is still waiting for your decision ({{ stage }})."),
           ("நினைவூட்டல்: {{ title }} உங்களுக்காகக் காத்திருக்கிறது", "{{ entity_label }} “{{ title }}” இன்னும் உங்கள் முடிவுக்காகக் காத்திருக்கிறது ({{ stage }})."),
           email=True),
        _e("finance.submitted", "A financial transaction was submitted", ("code", "amount", "org_unit"),
           ("Transaction {{ code }} submitted", "Transaction {{ code }} for {{ amount }} ({{ org_unit }}) was submitted for approval."),
           ("பரிவர்த்தனை {{ code }} சமர்ப்பிக்கப்பட்டது", "{{ org_unit }} இன் {{ amount }} மதிப்புள்ள {{ code }} பரிவர்த்தனை ஒப்புதலுக்கு சமர்ப்பிக்கப்பட்டது.")),
        _e("statement.ready", "A monthly statement is ready for approval", ("period",),
           ("Monthly statement ready: {{ period }}", "The financial statement for {{ period }} is ready for approval."),
           ("மாதாந்திர அறிக்கை தயார்: {{ period }}", "{{ period }} க்கான நிதி அறிக்கை ஒப்புதலுக்குத் தயாராக உள்ளது."), email=True),
        _e("statement.released", "A monthly statement was released", ("period",),
           ("Monthly statement released: {{ period }}", "The financial statement for {{ period }} has been officially released."),
           ("மாதாந்திர அறிக்கை வெளியிடப்பட்டது: {{ period }}", "{{ period }} க்கான நிதி அறிக்கை அதிகாரப்பூர்வமாக வெளியிடப்பட்டது."), email=True),
        _e("notice.published", "A notice was published", ("title",),
           ("New notice: {{ title }}", "A new parish notice “{{ title }}” has been published."),
           ("புதிய அறிவிப்பு: {{ title }}", "“{{ title }}” என்ற புதிய பங்கு அறிவிப்பு வெளியிடப்பட்டது.")),
        _e("meeting.scheduled", "A meeting was scheduled", ("title", "when", "place"),
           ("Meeting scheduled: {{ title }}", "“{{ title }}” is scheduled on {{ when }}{% if place %} at {{ place }}{% endif %}."),
           ("கூட்டம் திட்டமிடப்பட்டது: {{ title }}", "“{{ title }}” கூட்டம் {{ when }} அன்று{% if place %} {{ place }} இல்{% endif %} நடைபெறும்."), email=True),
        _e("meeting.reminder", "Reminder of an upcoming meeting", ("title", "when", "place"),
           ("Reminder: {{ title }}", "Reminder: “{{ title }}” on {{ when }}{% if place %} at {{ place }}{% endif %}."),
           ("நினைவூட்டல்: {{ title }}", "நினைவூட்டல்: “{{ title }}” {{ when }}{% if place %}, {{ place }}{% endif %}."), email=True),
        _e("action_item.assigned", "An action item was assigned to you", ("title", "due_date", "source"),
           ("Action item for you: {{ title }}", "You are responsible for “{{ title }}”{% if due_date %} (due {{ due_date }}){% endif %}{% if source %} – {{ source }}{% endif %}."),
           ("உங்களுக்கான செயல் பணி: {{ title }}", "“{{ title }}” உங்கள் பொறுப்பு{% if due_date %} (கெடு {{ due_date }}){% endif %}{% if source %} – {{ source }}{% endif %}.")),
        _e("meeting.cancelled", "A meeting was cancelled", ("title", "when", "reason"),
           ("Meeting cancelled: {{ title }}", "The meeting “{{ title }}” on {{ when }} has been cancelled.{% if reason %} {{ reason }}{% endif %}"),
           ("கூட்டம் ரத்து: {{ title }}", "{{ when }} அன்று நடைபெறவிருந்த “{{ title }}” கூட்டம் ரத்து செய்யப்பட்டது.{% if reason %} {{ reason }}{% endif %}")),
        _e("action_item.due", "An action item assigned to you is due", ("title", "due_date"),
           ("Action item due: {{ title }}", "The action item “{{ title }}” assigned to you is due on {{ due_date }}."),
           ("செயல் பணி நிலுவை: {{ title }}", "உங்களுக்கு ஒதுக்கப்பட்ட “{{ title }}” பணி {{ due_date }} அன்று முடிக்கப்பட வேண்டும்."), email=True),
        _e("festival.update", "Festival update", ("festival", "message"),
           ("{{ festival }}: update", "{{ message }}"),
           ("{{ festival }}: புதுப்பிப்பு", "{{ message }}")),
        _e("donation.received", "A donation was received", ("amount", "purpose", "donor"),
           ("Donation received: {{ amount }}", "A donation of {{ amount }} for {{ purpose }} was received from {{ donor }}."),
           ("நன்கொடை பெறப்பட்டது: {{ amount }}", "{{ purpose }} க்காக {{ donor }} இடமிருந்து {{ amount }} நன்கொடை பெறப்பட்டது."), email=True),
        _e("general.message", "General message from the parish office", ("title", "message"),
           ("{{ title }}", "{{ message }}"), ("{{ title }}", "{{ message }}"), important=True),
    )
}  # fmt: skip
