#!/usr/bin/env python3
"""Generate synthetic rows in the same 10 document shapes as
sample_dataset.jsonl, for stress-testing beyond the original 10 rows.

Ground-truth spans are computed directly while building each string (not
derived from redactor.py), so scoring against this file is a real test,
not a circular one.

USAGE:
    python generate_synthetic_dataset.py [n] [output.jsonl]
"""

import json
import random
import sys

FIRST_NAMES = [
    "Sarah", "Mark", "Patricia", "James", "Linda", "Marcus", "Rachel", "Wei",
    "David", "Jonathan", "Helen", "Eleanor", "Theodore", "Maya", "Chris",
    "John", "Emily", "Michael", "Taylor", "Grace", "Daniel", "Olivia",
    "Noah", "Ava", "Ethan", "Sophia", "Liam", "Isabella", "Lucas", "Mia",
    "Henry", "Amelia", "Benjamin", "Charlotte", "Samuel", "Zoe", "Nathan",
    "Claire", "Owen", "Ruby",
]
LAST_NAMES = [
    "Chen", "Liu", "Alvarez", "Whitaker", "Park", "Holloway", "Kim",
    "Zhang", "Reyes", "Reeves", "Pritchard", "Brennan", "Smith", "Johnson",
    "Brown", "Davis", "Baldwin", "Swift", "Garcia", "Martinez", "Nguyen",
    "Patel", "Robinson", "Clark", "Lewis", "Walker", "Hall", "Young",
    "King", "Wright",
]
TITLES = ["Dr.", "Mr.", "Mrs.", "Ms."]
SUFFIXES = ["Jr.", "III", "II"]
EMAIL_DOMAINS = [
    "acmecorp.com", "globex.io", "northwind.co", "stratosphere.com",
    "example.org", "protonmail.com", "gmail.com", "carolinawellness.org",
    "brennanlaw.com", "outlook.com",
]
STREET_NAMES = [
    "Cypress", "Birchwood", "Oakridge", "Sand Hill", "Lakeshore", "Maple",
    "Willow", "Cedar", "Riverside", "Highland", "Sunset", "Meadow",
    "Fairview", "Elm", "Pinecrest",
]
STREET_SUFFIXES = [
    "Lane", "Drive", "Boulevard", "Road", "Street", "Avenue", "Court",
    "Way", "Circle", "Place",
]
CITY_STATE_ZIP = [
    ("Austin", "TX", "78704"), ("Denver", "CO", "80202"),
    ("Seattle", "WA", "98109"), ("Menlo Park", "CA", "94025"),
    ("Chicago", "IL", "60601"), ("Portland", "OR", "97205"),
    ("Phoenix", "AZ", "85004"), ("Boston", "MA", "02108"),
    ("Atlanta", "GA", "30301"), ("Miami", "FL", "33101"),
]
UNIT_TYPES = ["Apt", "Suite", "Unit"]
MONTHS = [
    "January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December",
]
DEPARTMENTS = [
    "procurement", "legal", "engineering", "finance", "operations",
    "marketing", "sales", "HR",
]


class Builder:
    def __init__(self):
        self.parts = []
        self.pos = 0
        self.spans = []

    def text(self, s):
        self.parts.append(s)
        self.pos += len(s)

    def field(self, value, label):
        start = self.pos
        self.text(value)
        self.spans.append((start, self.pos, label))
        return value

    def build(self):
        return "".join(self.parts)


def apply_placeholders(text, spans):
    pieces = []
    last_end = 0
    for start, end, label in sorted(spans):
        pieces.append(text[last_end:start])
        pieces.append(f"[{label}]")
        last_end = end
    pieces.append(text[last_end:])
    return "".join(pieces)


def full_name(rng, with_title=False, with_suffix=False):
    first = rng.choice(FIRST_NAMES)
    last = rng.choice(LAST_NAMES)
    name = f"{first} {last}"
    if with_suffix:
        name = f"{name} {rng.choice(SUFFIXES)}"
    if with_title:
        name = f"{rng.choice(TITLES)} {name}"
    return first, last, name


def email_for(rng, first, last, domain=None):
    domain = domain or rng.choice(EMAIL_DOMAINS)
    return f"{first.lower()}.{last.lower()}@{domain}"


def phone(rng):
    area = rng.randint(200, 989)
    exch = rng.randint(200, 989)
    line = rng.randint(0, 9999)
    fmt = rng.choice(["paren", "dash", "dot", "intl"])
    if fmt == "paren":
        return f"({area}) 555-{line:04d}"
    if fmt == "dash":
        return f"{area}-555-{line:04d}"
    if fmt == "dot":
        return f"{area}.555.{line:04d}"
    return f"+1-{area}-555-{line:04d}"


def ssn(rng):
    area = rng.choice([a for a in range(100, 900) if a != 666])
    group = rng.randint(1, 99)
    serial = rng.randint(1, 9999)
    return f"{area:03d}-{group:02d}-{serial:04d}"


def dob(rng, textual=False):
    year = rng.randint(1950, 2000)
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)
    if textual:
        return f"{MONTHS[month - 1]} {day}, {year}"
    if rng.random() < 0.5:
        return f"{month:02d}/{day:02d}/{year}"
    return f"{month}/{day}/{year}"


def other_date(rng):
    year = rng.randint(2024, 2026)
    month = rng.randint(1, 12)
    day = rng.randint(1, 28)
    return f"{month:02d}/{day:02d}/{year}"


def address(rng, with_unit=None):
    number = rng.randint(1, 9999)
    street = rng.choice(STREET_NAMES)
    suffix = rng.choice(STREET_SUFFIXES)
    city, state, zip_ = rng.choice(CITY_STATE_ZIP)
    if with_unit is None:
        with_unit = rng.random() < 0.5
    if with_unit:
        unit_type = rng.choice(UNIT_TYPES)
        unit_num = rng.choice([str(rng.randint(1, 20)), f"{rng.randint(1, 20)}{rng.choice('ABC')}"])
        return f"{number} {street} {suffix}, {unit_type} {unit_num}, {city}, {state} {zip_}"
    return f"{number} {street} {suffix}, {city}, {state} {zip_}"


def t01(rng, id_):
    b = Builder()
    b.text("Subject: Account access issue\n\nHi support team,\n\nI'm writing on behalf of my colleague ")
    first, last, colleague = full_name(rng)
    b.field(colleague, "PERSON_NAME")
    b.text(", who is locked out of her account. Her email is ")
    b.field(email_for(rng, first, last), "EMAIL")
    b.text(" and her direct line is ")
    b.field(phone(rng), "PHONE_NUMBER")
    b.text(". Could you reset her credentials and call her back?\n\nThanks,\n")
    _, _, sender = full_name(rng)
    b.field(sender, "PERSON_NAME")
    return finalize(id_, b)


def t02(rng, id_):
    b = Builder()
    b.text("New hire onboarding record:\n\nName: ")
    first, last, name = full_name(rng, with_title=rng.random() < 0.5)
    b.field(name, "PERSON_NAME")
    b.text("\nDate of Birth: ")
    b.field(dob(rng), "DATE_OF_BIRTH")
    b.text("\nSocial Security Number: ")
    b.field(ssn(rng), "SSN")
    b.text("\nMailing Address: ")
    b.field(address(rng), "STREET_ADDRESS")
    b.text("\nPersonal Email: ")
    b.field(email_for(rng, first, last), "EMAIL")
    b.text("\n\nWelcome to the team!")
    return finalize(id_, b)


def t03(rng, id_):
    b = Builder()
    b.text("[Call transcript — %02d:%02d]\n\n" % (rng.randint(9, 17), rng.randint(0, 59)))
    b.text("Rep: Hi, is this ")
    first, last, contact = full_name(rng, with_title=True)
    b.field(contact, "PERSON_NAME")
    b.text("?\nCustomer: Yes, this is ")
    b.text(first)
    b.text(".\nRep: Great, I'm calling about the proposal we sent over. Is now a good time?\n")
    b.text("Customer: Sure. Can you send the follow-up to ")
    b.field(email_for(rng, first, last), "EMAIL")
    b.text("? My assistant ")
    _, _, assistant = full_name(rng)
    b.field(assistant, "PERSON_NAME")
    b.text(" can also be reached at ")
    b.field(phone(rng), "PHONE_NUMBER")
    b.text(".")
    return finalize(id_, b)


def t04(rng, id_):
    b = Builder()
    b.text(f"Ticket #{rng.randint(1000, 9999)}: Insurance verification request\n\nCustomer: ")
    first, last, name = full_name(rng)
    b.field(name, "PERSON_NAME")
    b.text("\nDOB: ")
    b.field(dob(rng), "DATE_OF_BIRTH")
    b.text("\nSSN on file: ")
    b.field(ssn(rng), "SSN")
    b.text("\nPhone: ")
    b.field(phone(rng), "PHONE_NUMBER")
    b.text("\nAddress: ")
    b.field(address(rng), "STREET_ADDRESS")
    b.text("\n\nCustomer is requesting confirmation that their dependent coverage is active "
           "for the upcoming surgery on ")
    b.text(other_date(rng))
    b.text(".")
    return finalize(id_, b)


def t05(rng, id_):
    b = Builder()
    b.text("Hey team,\n\nQuick heads up — ")
    first, last, name = full_name(rng)
    b.field(name, "PERSON_NAME")
    b.text(f" from {rng.choice(DEPARTMENTS)} is on vacation next week. "
           "If anything urgent comes up, reach out to ")
    b.field(email_for(rng, first, last), "EMAIL")
    b.text(" and her assistant will route it. For really urgent stuff, her cell is ")
    b.field(phone(rng), "PHONE_NUMBER")
    b.text(".\n\nThanks!")
    return finalize(id_, b)


def t06(rng, id_):
    b = Builder()
    b.text(f"Customer ID: {rng.randint(10000, 99999)}\nFull Name: ")
    first, last, name = full_name(rng)
    b.field(name, "PERSON_NAME")
    b.text("\nBorn: ")
    b.field(dob(rng, textual=True), "DATE_OF_BIRTH")
    b.text("\nPrimary Email: ")
    b.field(email_for(rng, first, last), "EMAIL")
    b.text("\nBackup Email: ")
    b.field(email_for(rng, first, last, domain=rng.choice(EMAIL_DOMAINS)), "EMAIL")
    b.text("\nPhone: ")
    b.field(phone(rng), "PHONE_NUMBER")
    b.text("\nHome Address: ")
    b.field(address(rng), "STREET_ADDRESS")
    return finalize(id_, b)


def t07(rng, id_):
    b = Builder()
    b.text("Forwarded message from ")
    first, last, name = full_name(rng)
    b.field(name, "PERSON_NAME")
    b.text(" — please add him to the distribution list. His email is ")
    b.field(email_for(rng, first, last), "EMAIL")
    b.text(" and the team should loop him in by EOW.")
    return finalize(id_, b)


def t08(rng, id_):
    b = Builder()
    b.text("Reminder: please ship the contract package to ")
    first, last, name = full_name(rng)
    b.field(name, "PERSON_NAME")
    b.text(", ")
    b.field(address(rng), "STREET_ADDRESS")
    b.text(". Confirm delivery by emailing ")
    b.field(email_for(rng, "legal", "team", domain=rng.choice(EMAIL_DOMAINS)), "EMAIL")
    b.text(". If you have questions about the routing, call ")
    b.field(rng.choice(FIRST_NAMES), "PERSON_NAME")
    b.text(" at ")
    b.field(phone(rng), "PHONE_NUMBER")
    b.text(".")
    return finalize(id_, b)


def t09(rng, id_):
    b = Builder()
    b.text("Patient intake note:\n\nPatient name: ")
    first, last, name = full_name(rng, with_title=True)
    b.field(name, "PERSON_NAME")
    b.text("\nDOB: ")
    b.field(dob(rng), "DATE_OF_BIRTH")
    b.text(f"\nInsurance ID: {rng.choice(LAST_NAMES)[:3].upper()}-{rng.randint(100,999)}-{rng.randint(1000,9999)}")
    b.text("\nContact: ")
    b.field(phone(rng), "PHONE_NUMBER")
    b.text("\nEmail: ")
    b.field(email_for(rng, first, last), "EMAIL")
    b.text("\n\nScheduled for follow-up consultation. Please confirm 24 hours before appointment.")
    return finalize(id_, b)


def t10(rng, id_):
    b = Builder()
    b.text("Loan application — Applicant details\n\nPrimary Applicant: ")
    first1, last1, name1 = full_name(rng, with_suffix=rng.random() < 0.3)
    b.field(name1, "PERSON_NAME")
    b.text("\nDate of Birth: ")
    b.field(dob(rng), "DATE_OF_BIRTH")
    b.text("\nSSN: ")
    b.field(ssn(rng), "SSN")
    b.text("\nCurrent Address: ")
    b.field(address(rng), "STREET_ADDRESS")
    b.text("\nMailing Address (if different): same as above\nPhone: ")
    b.field(phone(rng), "PHONE_NUMBER")
    b.text("\nEmail: ")
    b.field(email_for(rng, first1, last1), "EMAIL")
    b.text("\n\nCo-Applicant: ")
    first2, last2, name2 = full_name(rng)
    b.field(name2, "PERSON_NAME")
    b.text("\nDOB: ")
    b.field(dob(rng), "DATE_OF_BIRTH")
    b.text("\nSSN: ")
    b.field(ssn(rng), "SSN")
    b.text("\nEmail: ")
    b.field(email_for(rng, first2, last2), "EMAIL")
    b.text("\nPhone: ")
    b.field(phone(rng), "PHONE_NUMBER")
    b.text("\n\nApplication submitted on ")
    b.text(other_date(rng))
    b.text(" for review.")
    return finalize(id_, b)


def finalize(id_, b):
    source_text = b.build()
    target_text = apply_placeholders(source_text, b.spans)
    privacy_mask = [
        {"value": source_text[start:end], "start": start, "end": end, "label": label}
        for start, end, label in sorted(b.spans)
    ]
    span_labels = [[start, end, label] for start, end, label in sorted(b.spans)]
    return {
        "id": id_,
        "source_text": source_text,
        "target_text": target_text,
        "privacy_mask": privacy_mask,
        "span_labels": span_labels,
    }


TEMPLATES = [t01, t02, t03, t04, t05, t06, t07, t08, t09, t10]


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    output_path = sys.argv[2] if len(sys.argv) > 2 else "synthetic_dataset.jsonl"
    with open(output_path, "w") as f:
        for i in range(n):
            rng = random.Random(1000 + i)
            template = TEMPLATES[i % len(TEMPLATES)]
            row = template(rng, f"syn-{i + 1:03d}")
            f.write(json.dumps(row) + "\n")
    print(f"Wrote {n} rows to {output_path}")


if __name__ == "__main__":
    main()
