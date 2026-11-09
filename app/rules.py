"""Rule-based fallback classifier when the LLM is unavailable.

Deterministic keyword / pattern matching over common Linux, network,
and MySQL failure signatures. Lower confidence than LLM analysis —
clearly labeled as fallback in the response.
"""

from __future__ import annotations

import re
from typing import Any

RULES: list[dict[str, Any]] = [
    {
        "name": "oom_killer",
        "pattern": re.compile(r"Out of memory|oom-kill|Killed process", re.I),
        "summary": "Process likely killed by the Linux OOM killer due to memory pressure.",
        "probable_root_cause": "Host memory exhaustion; a process exceeded available RAM.",
        "severity": "critical",
        "troubleshooting_steps": [
            "Check free -h and /proc/meminfo for current memory pressure",
            "Inspect dmesg | grep -i oom for the killed process name",
            "Review recent deployments or traffic spikes that increased memory use",
            "Consider raising limits, adding swap carefully, or fixing a leak",
        ],
        "confidence": 0.75,
    },
    {
        "name": "disk_full",
        "pattern": re.compile(r"No space left on device|disk.*(full|quota)|ENOSPC", re.I),
        "summary": "Disk or filesystem appears full (ENOSPC / no space left).",
        "probable_root_cause": "Filesystem capacity exhausted or inode quota hit.",
        "severity": "high",
        "troubleshooting_steps": [
            "Run df -h and df -i to check capacity and inodes",
            "Find large files with du -xh / | sort -h | tail",
            "Rotate or purge logs under /var/log",
            "Expand the volume or clean unused images/containers",
        ],
        "confidence": 0.8,
    },
    {
        "name": "mysql_connection",
        "pattern": re.compile(
            r"Too many connections|Can't connect to (local )?MySQL|Access denied for user",
            re.I,
        ),
        "summary": "MySQL connection failure or connection limit reached.",
        "probable_root_cause": "Connection pool exhaustion, wrong credentials, or MySQL down.",
        "severity": "high",
        "troubleshooting_steps": [
            "Check MySQL process and listen port (ss -lntp | grep 3306)",
            "Show status like 'Threads_connected' and max_connections",
            "Review application pool size vs MySQL max_connections",
            "Verify credentials and host allowlists",
        ],
        "confidence": 0.7,
    },
    {
        "name": "mysql_slow_or_lock",
        "pattern": re.compile(
            r"Lock wait timeout|Deadlock found|slow query|Query execution was interrupted",
            re.I,
        ),
        "summary": "MySQL locking or slow-query related issue detected.",
        "probable_root_cause": "Long-running transactions, missing indexes, or lock contention.",
        "severity": "medium",
        "troubleshooting_steps": [
            "Check SHOW ENGINE INNODB STATUS and processlist",
            "Identify blocking transactions and kill if safe",
            "Review slow query log and EXPLAIN plans",
            "Add indexes or shorten transaction scope",
        ],
        "confidence": 0.65,
    },
    {
        "name": "network_timeout",
        "pattern": re.compile(
            r"Connection timed out|Network is unreachable|No route to host|"
            r"Connection refused|i/o timeout|dial tcp.*timeout",
            re.I,
        ),
        "summary": "Network connectivity failure between components.",
        "probable_root_cause": "Target down, firewall drop, DNS failure, or routing issue.",
        "severity": "high",
        "troubleshooting_steps": [
            "Ping / curl the target from the same host",
            "Check DNS resolution and /etc/resolv.conf",
            "Verify security group / iptables / cloud firewall rules",
            "Confirm the remote service is listening and healthy",
        ],
        "confidence": 0.7,
    },
    {
        "name": "redis_issue",
        "pattern": re.compile(
            r"MOVED|CLUSTERDOWN|LOADING Redis|MISCONF|OOM command not allowed|"
            r"Connection reset by peer.*6379|redis.*timeout",
            re.I,
        ),
        "summary": "Redis connectivity or cluster health problem.",
        "probable_root_cause": "Redis overloaded, misconfigured persistence, or cluster failover.",
        "severity": "high",
        "troubleshooting_steps": [
            "redis-cli INFO and PING from the app host",
            "Check maxmemory policy and used_memory",
            "Review AOF/RDB persistence errors in Redis log",
            "For cluster: check CLUSTER INFO and node health",
        ],
        "confidence": 0.7,
    },
    {
        "name": "auth_failure",
        "pattern": re.compile(
            r"authentication failure|Failed password|Invalid user|Unauthorized|401 Unauthorized",
            re.I,
        ),
        "summary": "Authentication or authorization failures observed.",
        "probable_root_cause": "Bad credentials, expired tokens, or brute-force attempts.",
        "severity": "medium",
        "troubleshooting_steps": [
            "Confirm whether failures are from a known service account or external IPs",
            "Rotate credentials if compromise is suspected",
            "Tighten firewall / fail2ban if brute force",
            "Check IdP / SSO token expiry settings",
        ],
        "confidence": 0.6,
    },
    {
        "name": "kernel_panic_or_hw",
        "pattern": re.compile(
            r"kernel panic|BUG: soft lockup|NVRM| Contiguous memory|I/O error|"
            r"EXT4-fs error|Buffer I/O error",
            re.I,
        ),
        "summary": "Kernel, filesystem, or hardware-level error signature.",
        "probable_root_cause": "Hardware fault, filesystem corruption, or driver issue.",
        "severity": "critical",
        "troubleshooting_steps": [
            "Capture dmesg and smartctl health for disks",
            "Check cloud console for underlying host maintenance events",
            "Run filesystem check in maintenance window if needed",
            "Migrate workload to a healthy node if hardware suspected",
        ],
        "confidence": 0.7,
    },
]


def classify(text: str) -> dict[str, Any]:
    """Apply first matching rule; otherwise return a low-confidence generic result."""
    for rule in RULES:
        if rule["pattern"].search(text):
            return {
                "summary": rule["summary"],
                "probable_root_cause": rule["probable_root_cause"],
                "severity": rule["severity"],
                "troubleshooting_steps": list(rule["troubleshooting_steps"]),
                "confidence": rule["confidence"],
                "analysis_source": "rule_fallback",
                "matched_rule": rule["name"],
            }

    return {
        "summary": "No strong rule matched; logs need manual or LLM review.",
        "probable_root_cause": "Unknown — insufficient signature match in fallback rules.",
        "severity": "unknown",
        "troubleshooting_steps": [
            "Collect surrounding log context (±15 minutes)",
            "Correlate with recent deploys and metric spikes",
            "Retry analysis when the LLM endpoint is available",
        ],
        "confidence": 0.2,
        "analysis_source": "rule_fallback",
        "matched_rule": None,
    }
