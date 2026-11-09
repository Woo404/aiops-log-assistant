from app.rules import classify


def test_oom_rule():
    result = classify("kernel: Out of memory: Killed process 2241 (node)")
    assert result["matched_rule"] == "oom_killer"
    assert result["severity"] == "critical"
    assert result["analysis_source"] == "rule_fallback"
    assert result["confidence"] >= 0.7


def test_disk_full_rule():
    result = classify("write failed: No space left on device")
    assert result["matched_rule"] == "disk_full"
    assert result["severity"] == "high"


def test_mysql_connections():
    result = classify("ERROR 1040 (HY000): Too many connections")
    assert result["matched_rule"] == "mysql_connection"


def test_no_match():
    result = classify("INFO service started successfully")
    assert result["matched_rule"] is None
    assert result["confidence"] <= 0.3
