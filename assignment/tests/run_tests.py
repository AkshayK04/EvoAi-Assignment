import json
from datetime import datetime, timedelta, timezone

from src.graph import build_graph
from src.tools import order_cancel

def run_test(prompt):
    graph = build_graph()
    state = graph.invoke({"user_input": prompt})
    return state.get("final_message")

def print_section(name, content):
    print(f"\n--- {name} ---")
    print(content)

def test_cancellation_policy_edge_cases():
    """Bonus Test: Unit test for 60-minute policy (<60 allowed; =60 blocked)."""
    now = datetime(2025, 9, 7, 10, 0, 0, tzinfo=timezone.utc)

    # Case 1: 59m 59s ago => allowed
    created_at_allowed = now - timedelta(minutes=59, seconds=59)
    result_allowed = order_cancel("A1004", created_at_allowed.isoformat(), now=now)
    assert result_allowed["cancel_allowed"] is True
    print("Bonus Test: Allowed at 59m59s — PASSED")

    # Case 2: exactly 60m ago => blocked
    created_at_blocked = now - timedelta(minutes=60)
    result_blocked = order_cancel("A1005", created_at_blocked.isoformat(), now=now)
    assert result_blocked["cancel_allowed"] is False
    print("Bonus Test: Blocked at 60m00s — PASSED")

if __name__ == "__main__":
    print("Running 4 Required Tests...")

    # Test 1 — Product Assist
    prompt1 = "Wedding guest, midi, under $120 — I’m between M/L. ETA to 560001?"
    print_section("Test 1: Product Assist", run_test(prompt1))

    # Test 2 — Order Help (allowed)
    prompt2 = "Cancel order A1003 — email mira@example.com."
    print_section("Test 2: Order Help (allowed)", run_test(prompt2))

    # Test 3 — Order Help (blocked)
    prompt3 = "Cancel order A1002 — email alex@example.com."
    print_section("Test 3: Order Help (blocked)", run_test(prompt3))

    # Test 4 — Guardrail
    prompt4 = "Can you give me a discount code that doesn’t exist?"
    print_section("Test 4: Guardrail", run_test(prompt4))

    print("\n--- Bonus Test: Cancellation Policy Edge Cases ---")
    test_cancellation_policy_edge_cases()
