from app.redaction import redact


def test_redacts_ip_email_phone_mac():
    text = (
        "user alice@example.com from 10.0.0.5 called +86-138-0013-8000 "
        "mac aa:bb:cc:dd:ee:ff token Bearer abcdefghijklmnopqrstuvwxyz012345"
    )
    scrubbed, counts = redact(text)
    assert "alice@example.com" not in scrubbed
    assert "10.0.0.5" not in scrubbed
    assert "138-0013-8000" not in scrubbed or "[REDACTED_PHONE]" in scrubbed
    assert "aa:bb:cc:dd:ee:ff" not in scrubbed
    assert "[REDACTED_EMAIL]" in scrubbed
    assert "[REDACTED_IP]" in scrubbed
    assert "[REDACTED_MAC]" in scrubbed
    assert counts["email"] >= 1
    assert counts["ipv4"] >= 1
    assert counts["mac"] >= 1


def test_preserves_non_pii():
    text = "Out of memory: Killed process 1234 (java)"
    scrubbed, counts = redact(text)
    assert "Out of memory" in scrubbed
    assert sum(counts.values()) == 0
