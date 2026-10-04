from agents.knowledge_based.information_retrieval.document_understanding.ocr_engine import MockOCREngine
from agents.orchestration.document_input import (
    AadhaarDocumentExtractor,
    AadhaarDocumentInput,
    AadhaarDocumentService,
    ExtractionStatus,
    FieldProvenance,
)


DOCUMENT_TEXT = """UIDAI Aadhaar
Name: Ramesh Kumar
DOB: 15/08/1985
Gender: MALE
1234 5678 9012
Address: 12 Main Street, Chennai 600001
"""


def service_with_text(text=DOCUMENT_TEXT):
    extractor = AadhaarDocumentExtractor(ocr_engine=MockOCREngine(text, 0.98))
    return AadhaarDocumentService(extractor)


def document(filename="aadhaar.png", content=b"image-bytes"):
    return AadhaarDocumentInput(filename=filename, content=content)


def test_valid_document_extraction():
    result = service_with_text().extract(document())

    assert result.status == ExtractionStatus.SUCCESS
    assert result.data is not None
    assert result.data.name is not None
    assert result.data.existing_address is not None
    assert result.data.name.provenance == FieldProvenance.EXTRACTED_FROM_DOCUMENT


def test_missing_field_is_reported_without_fabrication():
    result = service_with_text(DOCUMENT_TEXT.replace("Address: 12 Main Street, Chennai 600001", "")).extract(document())

    assert result.status == ExtractionStatus.MISSING_REQUIRED_FIELDS
    assert "existing_address" in result.missing_fields
    assert result.data.existing_address is None


def test_extraction_failure_when_ocr_is_unavailable():
    result = AadhaarDocumentService().extract(document())

    assert result.status == ExtractionStatus.EXTRACTION_FAILED
    assert result.data is None


def test_malformed_document():
    result = service_with_text().extract(document(filename="aadhaar.pdf", content=b"not-a-pdf"))

    assert result.status == ExtractionStatus.MALFORMED_DOCUMENT
    assert result.data is None


def test_aadhaar_number_is_masked():
    result = service_with_text().extract(document())

    assert result.data.masked_aadhaar.value == "XXXX-XXXX-9012"
    assert "1234 5678 9012" not in result.model_dump_json()
    assert "123456789012" not in result.model_dump_json()


def test_extracted_data_is_not_confirmed_automatically():
    result = service_with_text().extract(document())

    assert result.data.name.provenance == FieldProvenance.EXTRACTED_FROM_DOCUMENT
    assert result.data.name.provenance != FieldProvenance.USER_CONFIRMED


def test_explicit_confirmation_produces_confirmed_context():
    service = service_with_text()
    extracted = service.extract(document())

    confirmed = service.confirm(extracted)
    context = confirmed.to_execution_context("session-1")

    assert confirmed.name.provenance == FieldProvenance.USER_CONFIRMED
    assert context.facts["name"].status.value == "confirmed"
    assert context.facts["name"].allowed_for_execution is True
    assert context.facts["name"].provenance == "user_confirmed"


def test_user_correction_produces_corrected_provenance():
    service = service_with_text()
    extracted = service.extract(document())

    confirmed = service.confirm(extracted, {"existing_address": "99 Corrected Road"})

    assert confirmed.existing_address.value == "99 Corrected Road"
    assert confirmed.existing_address.provenance == FieldProvenance.USER_CORRECTED
    assert confirmed.name.provenance == FieldProvenance.USER_CONFIRMED


def test_downstream_context_contains_only_confirmed_facts():
    service = service_with_text()
    extracted = service.extract(document())
    confirmed = service.confirm(extracted)

    context = confirmed.to_execution_context("session-1")

    assert set(context.facts) == {"name", "date_of_birth", "gender", "masked_aadhaar", "existing_address"}
    assert all(fact.allowed_for_execution for fact in context.facts.values())
    assert all(fact.status.value == "confirmed" for fact in context.facts.values())
    assert all("1234 5678 9012" not in str(fact.value) for fact in context.facts.values())


def test_name_extraction_variations():
    # 1. Card front with Government header + DOB
    t1 = """Unique Identification Authority of India
Government of India
John Doe
जन्म तिथि / DOB: 15/08/1985
लिंग / Gender: पुरुष / MALE
XXXX-XXXX-9671
Address: 12 Main St, City 560001
"""
    r1 = service_with_text(t1).extract(document())
    assert r1.data.name.value == "John Doe"

    # 2. Card front with Hindi name above English name
    t2 = """भारत सरकार
GOVERNMENT OF INDIA
रोहन शर्मा
Rohan Sharma
जन्म तारीख / DOB : 01/01/1992
पुरुष / MALE
9123 4567 8901
Address: 12 Main St, City 560001
"""
    r2 = service_with_text(t2).extract(document())
    assert r2.data.name.value == "Rohan Sharma"

    # 3. e-Aadhaar "To," layout
    t3 = """UIDAI
To,
Jane Smith
W/O: Robert Smith
DOB: 22/11/1990
Gender: FEMALE
1234 5678 9012
Address: 12 Main St, City 560001
"""
    r3 = service_with_text(t3).extract(document())
    assert r3.data.name.value == "Jane Smith"


def test_dob_extraction_variations():
    # Slash formatted DOB
    t1 = """UIDAI Aadhaar
Name: Ramesh Kumar
जन्म तिथि / DOB: 15/08/1985
Gender: MALE
1234 5678 9012
Address: 12 Main Street, Chennai 600001
"""
    assert service_with_text(t1).extract(document()).data.date_of_birth.value == "15/08/1985"

    # Hyphen formatted DOB
    t2 = """UIDAI Aadhaar
Name: Ramesh Kumar
DOB : 15-08-1985
Gender: MALE
1234 5678 9012
Address: 12 Main Street, Chennai 600001
"""
    assert service_with_text(t2).extract(document()).data.date_of_birth.value == "15/08/1985"

    # Year of Birth only
    t3 = """UIDAI Aadhaar
Name: Ramesh Kumar
Year of Birth / जन्म का वर्ष: 1985
Gender: MALE
1234 5678 9012
Address: 12 Main Street, Chennai 600001
"""
    assert service_with_text(t3).extract(document()).data.date_of_birth.value == "1985"


def test_gender_extraction_variations():
    # Hindi + English gender
    t1 = """UIDAI Aadhaar
Name: Ramesh Kumar
DOB: 15/08/1985
लिंग / Gender: पुरुष / MALE
1234 5678 9012
Address: 12 Main Street, Chennai 600001
"""
    assert service_with_text(t1).extract(document()).data.gender.value == "MALE"

    # Female gender
    t2 = """UIDAI Aadhaar
Name: Sita Sharma
DOB: 15/08/1985
Gender: FEMALE
1234 5678 9012
Address: 12 Main Street, Chennai 600001
"""
    assert service_with_text(t2).extract(document()).data.gender.value == "FEMALE"


def test_masked_aadhaar_extraction_variations():
    # 12 digits space separated
    t1 = """UIDAI Aadhaar
Name: Ramesh Kumar
DOB: 15/08/1985
Gender: MALE
1234 5678 9012
Address: 12 Main Street, Chennai 600001
"""
    assert service_with_text(t1).extract(document()).data.masked_aadhaar.value == "XXXX-XXXX-9012"

    # Already masked
    t2 = """UIDAI Aadhaar
Name: Ramesh Kumar
DOB: 15/08/1985
Gender: MALE
XXXX-XXXX-9671
Address: 12 Main Street, Chennai 600001
"""
    assert service_with_text(t2).extract(document()).data.masked_aadhaar.value == "XXXX-XXXX-9671"


def test_multiline_address_extraction():
    # Multi-line address with S/O and PIN code
    t1 = """Unique Identification Authority of India
Government of India
John Doe
जन्म तिथि / DOB: 15/08/1985
लिंग / Gender: पुरुष / MALE
XXXX-XXXX-9671
Address:
S/O: Richard Doe, #42 Baker Street,
Near Clock Tower, Sector 5,
Bengaluru, Karnataka - 560001
"""
    r1 = service_with_text(t1).extract(document())
    assert r1.status == ExtractionStatus.SUCCESS
    assert "560001" in r1.data.existing_address.value
    assert "Baker Street" in r1.data.existing_address.value
    assert "Bengaluru" in r1.data.existing_address.value

    # Multilingual address (Hindi & English)
    t2 = """UIDAI Aadhaar
Name: Rohan Sharma
DOB: 01/01/1992
Gender: MALE
9123 4567 8901
पता:
एस/ओ: मोहन शर्मा, गांधी नगर, नई दिल्ली - 110001
Address:
S/O: Mohan Sharma, House No 12, Gandhi Nagar, New Delhi - 110001
"""
    r2 = service_with_text(t2).extract(document())
    assert r2.status == ExtractionStatus.SUCCESS
    assert "110001" in r2.data.existing_address.value
    assert "New Delhi" in r2.data.existing_address.value


def test_common_pdf_ocr_line_break_variations():
    # Extra whitespace, tab characters, and split delimiters
    t = """UIDAI\tAadhaar
\tName :\t  Ramesh Kumar
  DOB :   15 / 08 / 1985
\tGender :\t MALE
  1234   5678   9012
  Address :
  12 Main Street,
  Chennai - 600001
"""
    r = service_with_text(t).extract(document())
    assert r.status == ExtractionStatus.SUCCESS
    assert r.data.name.value == "Ramesh Kumar"
    assert r.data.date_of_birth.value == "15/08/1985"
    assert r.data.gender.value == "MALE"
    assert r.data.masked_aadhaar.value == "XXXX-XXXX-9012"
    assert "600001" in r.data.existing_address.value


def test_missing_field_behavior():
    # Missing DOB
    t_no_dob = """UIDAI Aadhaar
Name: Ramesh Kumar
Gender: MALE
1234 5678 9012
Address: 12 Main Street, Chennai 600001
"""
    r = service_with_text(t_no_dob).extract(document())
    assert r.status == ExtractionStatus.MISSING_REQUIRED_FIELDS
    assert "date_of_birth" in r.missing_fields
    assert r.data.date_of_birth is None


def test_ambiguous_text_must_not_be_guessed():
    # Random text that cannot form a valid name or address
    t_noise = """UIDAI Aadhaar
1234 5678 9012
Gender: MALE
DOB: 15/08/1985
"""
    r = service_with_text(t_noise).extract(document())
    assert r.data.name is None
    assert r.data.existing_address is None
    assert "name" in r.missing_fields
    assert "existing_address" in r.missing_fields


def test_provenance_and_confidence_preservation():
    r = service_with_text().extract(document())
    assert r.data.name.provenance == FieldProvenance.EXTRACTED_FROM_DOCUMENT
    assert r.data.name.confidence >= 0.75
    assert r.data.name.source_document_id is not None
    assert r.data.date_of_birth.provenance == FieldProvenance.EXTRACTED_FROM_DOCUMENT
    assert r.data.date_of_birth.confidence >= 0.75
    assert r.data.existing_address.provenance == FieldProvenance.EXTRACTED_FROM_DOCUMENT
    assert r.data.existing_address.confidence >= 0.75


def test_name_candidate_mobile_rejected():
    # 1. "Mobile" label on line preceding Gender must NOT become name
    t1 = """Unique Identification Authority of India
Government of India
Ramesh Kumar
Mobile: 9876543210
जन्म तिथि / DOB: 15/08/1985
लिंग / Gender: पुरुष / MALE
XXXX-XXXX-9671
Address: 12 Main Street, Bengaluru 560001
"""
    r1 = service_with_text(t1).extract(document())
    assert r1.data.name.value == "Ramesh Kumar"
    assert r1.data.name.value != "Mobile"

    # 2. Standalone "Mobile" keyword must be rejected as candidate name
    t2 = """Unique Identification Authority of India
Mobile
DOB: 15/08/1985
Gender: MALE
XXXX-XXXX-9671
"""
    r2 = service_with_text(t2).extract(document())
    assert r2.data.name is None


def test_footer_instruction_text_not_address():
    # Footer disclaimer must NOT become existing_address
    t = """Unique Identification Authority of India
Government of India
Ramesh Kumar
DOB: 15/08/1985
Gender: MALE
XXXX-XXXX-9671
Aadhaar is a proof of identity, not of citizenship.
It should be updated in Aadhaar after every 10 years from date of enrolment.
Keep your mobile number and email updated in Aadhaar.
Help: help@uidai.gov.in, Toll Free: 1947
"""
    r = service_with_text(t).extract(document())
    assert r.data.existing_address is None
    assert "existing_address" in r.missing_fields
    assert r.status == ExtractionStatus.MISSING_REQUIRED_FIELDS


def test_realistic_aadhaar_with_footer_and_multiline_address():
    # Address extracted cleanly and stops before the footer text
    t = """Unique Identification Authority of India
Government of India
Pooja Devi
जन्म तिथि / DOB:
12 / 04 / 1991
Gender / लिंग: FEMALE / महिला
XXXX-XXXX-9671
Address:
D/O: Rajesh Devi, Flat 301, Sunshine Heights,
MG Road, Near Central Park,
Bengaluru, Karnataka - 560001
Aadhaar is a proof of identity, not of citizenship.
It should be updated in Aadhaar after every 10 years from date of enrolment.
"""
    r = service_with_text(t).extract(document())
    assert r.status == ExtractionStatus.SUCCESS
    assert r.data.name.value == "Pooja Devi"
    assert r.data.date_of_birth.value == "12/04/1991"
    assert r.data.gender.value == "FEMALE"
    assert r.data.masked_aadhaar.value == "XXXX-XXXX-9671"
    assert "560001" in r.data.existing_address.value
    assert "Sunshine Heights" in r.data.existing_address.value
    assert "should be updated" not in r.data.existing_address.value
    assert "proof of identity" not in r.data.existing_address.value


