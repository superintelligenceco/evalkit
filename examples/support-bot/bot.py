"""A toy rules-based support bot that stands in for your LLM app.

evalkit runs it once per task: the customer message arrives on stdin and the
reply goes to stdout. Replace it with your own agent entry point.
"""

import re
import sys

ORDERS = {"A1001": "shipped", "A1002": "processing", "A1003": "delivered"}


def reply(message: str) -> str:
    text = message.lower()
    order = re.search(r"\b(A\d{4})\b", message)
    if "password" in text:
        return (
            "Sorry for the trouble. Open Settings > Security and choose Reset password. "
            "The reset link expires after 30 minutes."
        )
    if order and ("where" in text or "status" in text or "track" in text):
        status = ORDERS.get(order.group(1))
        if status is None:
            return f"Sorry, I cannot find order {order.group(1)}. Please check the number."
        return f"Thanks for waiting. Order {order.group(1)} is {status}."
    if "refund" in text:
        return (
            "Sorry to hear that. Refund requests go through Billing > Refunds. "
            "A billing specialist reviews each request within 2 business days."
        )
    if "outage" in text or "down" in text:
        return "Sorry for the disruption. Live service health is at status.example.com."
    if "human" in text or "agent" in text:
        return "I am connecting you with a human agent now. Ticket number: T-58213."
    return "Thanks for reaching out. Could you share a few more details about the issue?"


if __name__ == "__main__":
    sys.stdout.write(reply(sys.stdin.read()) + "\n")
