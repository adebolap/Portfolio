from drive_stripper import proprietary


def test_detects_email():
    matches = proprietary.detect("contact us at jane.doe@acme.com for details")
    assert any(m.label == "email" and m.value == "jane.doe@acme.com" for m in matches)


def test_detects_aws_key():
    matches = proprietary.detect("key=AKIAABCDEFGHIJKLMNOP rotate it")
    assert any(m.label == "aws_access_key" for m in matches)


def test_detects_custom_terms_case_insensitive():
    matches = proprietary.detect("Project SkyNet is confidential", custom_terms=["skynet"])
    assert any(m.label == "custom_term:skynet" and m.value == "SkyNet" for m in matches)


def test_categories_filter_restricts_scan():
    text = "email jane@acme.com and phone 555-123-4567"
    matches = proprietary.detect(text, categories=("email",))
    assert all(m.label == "email" for m in matches)
    assert matches  # sanity: still found the email


def test_redact_replaces_matches_with_placeholder():
    text = "email jane@acme.com now"
    matches = proprietary.detect(text, categories=("email",))
    redacted = proprietary.redact(text, matches)
    assert "jane@acme.com" not in redacted
    assert "[REDACTED]" in redacted


def test_overlapping_matches_keep_leftmost_longest():
    # a private key block also contains lines that could look like other tokens;
    # ensure overlap resolution doesn't double count / corrupt the span list.
    text = "-----BEGIN PRIVATE KEY-----\nabc123\n-----END PRIVATE KEY-----"
    matches = proprietary.detect(text, categories=("private_key_block",))
    assert len(matches) == 1
    assert matches[0].value == text


def test_luhn_valid_credit_card_is_detected():
    # a well-known Luhn-valid Visa test number
    matches = proprietary.detect("card 4111111111111111 on file", categories=("credit_card",))
    assert len(matches) == 1
    assert matches[0].value == "4111111111111111"


def test_luhn_invalid_digit_run_is_not_flagged_as_credit_card():
    # same length as a real card number but fails the checksum - e.g. an
    # arbitrary internal ID that would otherwise be a false positive
    matches = proprietary.detect("ref 1234567890123456 processed", categories=("credit_card",))
    assert matches == []


def test_phone_matches_are_medium_confidence():
    matches = proprietary.detect("call 555-123-4567 now", categories=("phone",))
    assert matches and all(m.confidence == "medium" for m in matches)


def test_email_matches_are_high_confidence():
    matches = proprietary.detect("jane@acme.com", categories=("email",))
    assert matches and all(m.confidence == "high" for m in matches)


def test_high_entropy_secret_is_detected_and_medium_confidence():
    # shaped like a real API token (github/slack/stripe-style): mixed case + digits
    token = "kJ8x2Qp9zR7mN4vT6wL1sD3fG5hY0aBc"
    matches = proprietary.detect(f"key: {token}", categories=("high_entropy_secret",))
    assert len(matches) == 1
    assert matches[0].value == token
    assert matches[0].confidence == "medium"


def test_random_hex_secret_is_detected_via_lower_hex_threshold():
    hex_secret = "9f8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c"
    matches = proprietary.detect(f"secret={hex_secret}", categories=("high_entropy_secret",))
    assert len(matches) == 1
    assert matches[0].value == hex_secret


def test_low_entropy_identifier_is_not_flagged():
    # a normal camelCase identifier reads as language-like, not random
    text = "someVeryLongVariableNameForTesting is unused"
    matches = proprietary.detect(text, categories=("high_entropy_secret",))
    assert matches == []


def test_repeated_text_is_not_flagged_as_high_entropy():
    text = "thisisthisisthisisthisis is a low entropy repeated run"
    matches = proprietary.detect(text, categories=("high_entropy_secret",))
    assert matches == []


def test_uuid_without_dashes_is_not_flagged_high_entropy():
    # a known false-positive shape for entropy scanning generally (real
    # secret-scanning tools have the same trade-off) - documented, not hidden
    uuid_nodash = "550e8400e29b41d4a716446655440000"
    matches = proprietary.detect(f"id: {uuid_nodash}", categories=("high_entropy_secret",))
    assert matches == []


def test_aws_key_is_not_double_reported_as_high_entropy_secret():
    matches = proprietary.detect(
        "key=AKIAABCDEFGHIJKLMNOP rotate it", categories=("aws_access_key", "high_entropy_secret")
    )
    assert len(matches) == 1
    assert matches[0].label == "aws_access_key"


def test_shannon_entropy_helper_extremes():
    assert proprietary.shannon_entropy("") == 0.0
    assert proprietary.shannon_entropy("aaaaaaaa") == 0.0
    assert proprietary.shannon_entropy("ab") == 1.0  # 2 equally likely symbols = 1 bit
