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
