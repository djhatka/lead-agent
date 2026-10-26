r"""
Automatic checks for the data rules in app/schemas.py.

Run from the backend folder with:
    .\.venv\Scripts\python.exe -m pytest tests -v

Each function starting with `test_` is one check. `pytest` runs them all
and prints PASSED or FAILED for each.
`pytest.raises(ValidationError)` means "this SHOULD be rejected".
"""

import pytest
from pydantic import ValidationError

from app.schemas import BusinessCreate, LeadCreate, LeadUpdate, MessageCreate


# ----- Businesses -----------------------------------------------------------
def test_good_business_is_accepted():
    b = BusinessCreate(name="  Redox Gym ", industry="Gym", services=["Zumba", "", "Zumba"], phone="98110 00000")
    assert b.name == "Redox Gym"            # spaces trimmed
    assert b.industry == "gym"              # "Gym" → "gym"
    assert b.services == ["Zumba"]          # blanks and duplicates removed
    assert b.phone == "+919811000000"       # phone cleaned into one format


def test_unknown_industry_is_rejected():
    with pytest.raises(ValidationError):
        BusinessCreate(name="Pizza Planet", industry="spaceship")


def test_missing_name_is_rejected():
    with pytest.raises(ValidationError):
        BusinessCreate(industry="gym")


def test_unknown_field_is_rejected():
    with pytest.raises(ValidationError):
        BusinessCreate(name="Redox Gym", industry="gym", favourite_colour="red")


# ----- Phone numbers ---------------------------------------------------------
@pytest.mark.parametrize(
    "raw, expected",
    [
        ("9811000000", "+919811000000"),
        ("098110-00000", "+919811000000"),
        ("+91 98110 00000", "+919811000000"),
        ("919811000000", "+919811000000"),
        ("+1 415 555 0100", "+14155550100"),
    ],
)
def test_phone_numbers_are_cleaned(raw, expected):
    lead = LeadCreate(business_id=1, source="whatsapp", phone=raw)
    assert lead.phone == expected


@pytest.mark.parametrize("bad", ["12345", "abcdefghij", "1234567890"])
def test_fake_phone_numbers_are_rejected(bad):
    with pytest.raises(ValidationError):
        LeadCreate(business_id=1, source="whatsapp", phone=bad)


# ----- Leads -----------------------------------------------------------------
def test_good_lead_is_accepted():
    lead = LeadCreate(
        business_id=1, source="Instagram", handle="@priya.fit",
        service="Zumba", details={"batch": "evening"}, first_message="Fees?",
    )
    assert lead.source == "instagram"
    assert lead.handle == "priya.fit"       # @ removed


def test_lead_without_business_is_rejected():
    with pytest.raises(ValidationError):
        LeadCreate(source="whatsapp", phone="9811000000")


def test_unknown_source_is_rejected():
    with pytest.raises(ValidationError):
        LeadCreate(business_id=1, source="carrier_pigeon", phone="9811000000")


def test_lead_nobody_can_contact_is_rejected():
    with pytest.raises(ValidationError, match="at least a name, phone or handle"):
        LeadCreate(business_id=1, source="website", first_message="hello")


# ----- Lead updates ----------------------------------------------------------
def test_marking_lead_won_with_money_is_accepted():
    update = LeadUpdate(status="WON", job_value=12000)
    assert update.status == "won"


def test_money_on_a_lost_lead_is_rejected():
    with pytest.raises(ValidationError, match="only be set when status is 'won'"):
        LeadUpdate(status="lost", job_value=5000)


def test_negative_money_is_rejected():
    with pytest.raises(ValidationError):
        LeadUpdate(job_value=-100)


def test_unknown_status_is_rejected():
    with pytest.raises(ValidationError):
        LeadUpdate(status="maybe")


# ----- Messages --------------------------------------------------------------
def test_empty_message_is_rejected():
    with pytest.raises(ValidationError):
        MessageCreate(text="   ")
