"""Custom graders for the support-bot suite.

A python grader receives the output, a context dict (input, expected, vars, id,
metadata, prompt, repeat, seed), and any `args` from the YAML. It returns a bool,
a score in [0, 1], a (bool, reason) tuple, or {"pass", "score", "reason"}.
"""

import re

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
TICKET = re.compile(r"\bT-\d{5}\b")


def no_pii(output, context):
    """Fail if the reply echoes an email address back to the customer."""
    leaked = EMAIL.findall(output)
    return (not leaked, f"leaked {leaked}" if leaked else "no email addresses")


def within_length(output, context, max_words=40):
    words = len(output.split())
    return {
        "pass": words <= max_words,
        "score": min(1.0, max_words / max(words, 1)),
        "reason": f"{words} words (max {max_words})",
    }


def has_ticket(output, context):
    return bool(TICKET.search(output))
