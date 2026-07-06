from __future__ import annotations

import re
import smtplib
import socket
import uuid

import dns.exception
import dns.resolver


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_valid_email(email: str | None) -> bool:
    return bool(email and EMAIL_PATTERN.match(email))


def domain_has_mx_record(domain: str | None) -> bool:
    if not domain:
        return False

    return bool(get_mx_records(domain))


def get_mx_records(domain: str) -> list[str]:
    try:
        answers = dns.resolver.resolve(domain, "MX")
    except dns.exception.DNSException:
        return []

    records = sorted(
        answers,
        key=lambda answer: int(getattr(answer, "preference", 0)),
    )
    return [str(record.exchange).rstrip(".") for record in records]


def smtp_verify(email: str, mx_host: str, timeout: float = 10.0) -> bool | None:
    if not is_valid_email(email):
        return False

    try:
        with smtplib.SMTP(mx_host, 25, timeout=timeout) as smtp:
            smtp.ehlo_or_helo_if_needed()
            smtp.mail("verify@localhost")
            target_code, _ = smtp.rcpt(email)

            if 200 <= target_code < 300:
                if _accepts_random_address(smtp, email):
                    return None
                return True

            if 500 <= target_code < 600:
                return False

            return None
    except (OSError, smtplib.SMTPException, socket.timeout):
        return None


def _accepts_random_address(smtp: smtplib.SMTP, email: str) -> bool:
    domain = email.rsplit("@", 1)[1]
    random_email = f"no-such-user-{uuid.uuid4().hex}@{domain}"

    try:
        code, _ = smtp.rcpt(random_email)
    except smtplib.SMTPException:
        return False

    return 200 <= code < 300
