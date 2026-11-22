"""Generate a tailored application email for a job.

Default: a clean template that personalizes on company/title (no API key).
Optional: if ANTHROPIC_API_KEY is set, use the model to write a sharper,
genuinely tailored message. Either way the output is a DRAFT for you to review.

The sender's name/email come from the signed-in user (passed in by the caller);
MY_NAME in config is only a fallback.
"""
from . import config


def _focus() -> str:
    tail = config.MY_HEADLINE.split("|")[-1].strip()
    return tail or "administrative support"


def template_draft(job: dict, sender_name: str, sender_email: str = "") -> tuple[str, str]:
    company = (job.get("company") or "your team").strip()
    title = (job.get("title") or "Virtual Assistant").strip()

    subject = f"Application: {title} — {sender_name}"

    extras = [x for x in (sender_email, config.MY_PHONE, config.MY_PORTFOLIO_URL) if x]
    contact_line = " · ".join(extras)

    body = f"""Hi {company} team,

I'm writing to apply for the {title} role. I'm a US-based virtual assistant
focused on {_focus()}, and I'd love to help lighten your team's day-to-day load.

A few things I can take off your plate right away:
- Inbox and calendar management, scheduling, and meeting coordination
- Data entry, document prep, CRM updates, and light research
- Customer/email follow-ups handled promptly and professionally

I'm reliable, communicate clearly, and work independently across US time zones.
I'd welcome the chance to share how I can support {company}. Thank you for your
time and consideration.

Best regards,
{sender_name}
{contact_line}
""".rstrip() + "\n"

    return subject, body


def llm_draft(job: dict, sender_name: str, sender_email: str = "") -> tuple[str, str]:
    """Use Anthropic to write a tailored draft. Falls back to template on error."""
    try:
        import anthropic  # type: ignore
    except ImportError:
        print("[drafts] anthropic SDK not installed; using template")
        return template_draft(job, sender_name, sender_email)

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    prompt = f"""Write a concise, warm, professional job-application email.

Applicant: {sender_name}
Headline: {config.MY_HEADLINE}
Contact: {sender_email} {config.MY_PHONE} {config.MY_PORTFOLIO_URL}

Job title: {job.get('title')}
Company: {job.get('company')}
Job description (may be truncated):
{(job.get('description') or '')[:1500]}

Rules:
- 120-170 words, specific to THIS role, not generic.
- No invented experience or fake metrics.
- Plain text. End with the applicant's name and contact line.
- First line must be: SUBJECT: <subject line>
"""
    try:
        msg = client.messages.create(
            model=config.ANTHROPIC_MODEL,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        text = msg.content[0].text.strip()
    except Exception as e:  # noqa: BLE001
        print(f"[drafts] LLM failed ({e}); using template")
        return template_draft(job, sender_name, sender_email)

    subject = f"Application: {job.get('title')} — {sender_name}"
    body = text
    if text.upper().startswith("SUBJECT:"):
        line, _, rest = text.partition("\n")
        subject = line.split(":", 1)[1].strip() or subject
        body = rest.strip() + "\n"
    return subject, body


def generate(job: dict, sender_name: str = "", sender_email: str = "") -> tuple[str, str]:
    sender_name = sender_name or config.MY_NAME
    if config.ANTHROPIC_API_KEY:
        return llm_draft(job, sender_name, sender_email)
    return template_draft(job, sender_name, sender_email)
