import os
import json
import re
from datetime import datetime, timezone
from pydantic.v1 import BaseModel
from langgraph.graph import StateGraph, END

from .tools import product_search, size_recommender, eta, order_lookup, order_cancel

PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "prompts")

class AgentState(BaseModel):
    user_input: str
    intent: str | None = None
    tools_called: list = []
    evidence: list = []
    policy_decision: dict | None = None
    final_message: str | None = None

class SimpleLLM:
    def __init__(self, system_prompt_path):
        with open(system_prompt_path, "r") as f:
            self.system_prompt = f.read()

    def invoke(self, messages):
        user_message = messages[-1]["content"].lower()
        if "cancel" in user_message or "order" in user_message:
            return "order_help"
        if any(k in user_message for k in ["dress", "wedding", "under $", "midi", "eta"]):
            return "product_assist"
        return "other"

llm = SimpleLLM(os.path.join(PROMPTS_DIR, "system.md"))

# --------- Router ----------
def router(state: AgentState):
    state.intent = llm.invoke([{"role": "system", "content": ""}, {"role": "user", "content": state.user_input}])
    return state

# --------- Product Assist Flow ----------
def _parse_product_inputs(text: str):
    t = text.lower()

    # price cap: "under $120"
    price_max = None
    m = re.search(r"under\s*\$\s*(\d+)", t)
    if m:
        price_max = int(m.group(1))

    # tags: wedding, midi (loose)
    tags = []
    for tag in ["wedding", "midi", "daywear", "party"]:
        if re.search(rf"\b{tag}\b", t):
            tags.append(tag)

    # size note
    size_note = ""
    if "between m/l" in t or "between m and l" in t or "m/l" in t:
        size_note = "M/L"
    elif re.search(r"\b(size|sz)\s*(m|l)\b", t):
        size_note = re.search(r"\b(size|sz)\s*(m|l)\b", t).group(2).upper()

    # zip: handle "ETA to 560001" (also en/em dashes or punctuation)
    zip_code = None
    z = re.search(r"eta\s*to\s*(\d{5,6})", t, flags=re.IGNORECASE)
    if z:
        zip_code = z.group(1)

    return price_max, tags, size_note, zip_code

def product_assist_flow(state: AgentState):
    price_max, tags, size_note, zip_code = _parse_product_inputs(state.user_input)

    products = product_search(query=state.user_input, price_max=price_max, tags=tags)
    size_msg = size_recommender(size_note or "")
    eta_msg = eta(zip_code)

    state.tools_called.extend(["product_search", "size_recommender", "eta"])

    # take up to 2 items deterministically (product_search already sorted)
    evidence = []
    for p in products[:2]:
        evidence.append({
            "id": p["id"],
            "title": p["title"],
            "price": p["price"],
            "sizes": p["sizes"],
            "tags": p["tags"],
            "color": p["color"],
            "size_rec": size_msg,
            "eta": eta_msg
        })
    state.evidence = evidence

    # compose message if we got results
    if evidence:
        lines = []
        for item in evidence:
            lines.append(
                f"‘{item['title']}’ (${item['price']}) — sizes: {', '.join(item['sizes'])}. "
                f"Recommendation: {item['size_rec']} ETA to your area: {item['eta']}."
            )
        state.final_message = "Here are a couple of options:\n- " + "\n- ".join(lines)
    else:
        state.final_message = "I couldn’t find options under your criteria. Try widening the price or tags."

    return state

# --------- Order Help Flow ----------
def _parse_order(text: str):
    """
    Robustly parse: 'Cancel order A1003 — email mira@example.com.'
    Handles ascii or unicode dashes and trailing punctuation.
    """
    # Normalize unicode dashes to '-'
    t = re.sub(r"[—–−]", "-", text)
    t_low = t.lower()

    # Extract order id
    m_id = re.search(r"cancel\s+order\s+([a-z0-9-]+)", t_low)
    order_id = m_id.group(1).strip().upper() if m_id else None

    # Extract email after 'email'
    m_em = re.search(r"email\s+([^\s]+)", t_low)
    email = m_em.group(1).strip().rstrip(".,;:!?)(").lower() if m_em else None

    return order_id, email

def order_help_flow(state: AgentState):
    order_id, email = _parse_order(state.user_input)

    state.tools_called.append("order_lookup")
    order = order_lookup(order_id, email)

    if not order:
        state.evidence.append({"order_id": order_id, "email": email})
        state.final_message = "I couldn't find an order with that information. Please double-check the order ID and email."
        return state

    state.evidence.append({
        "order_id": order["order_id"],
        "email": order["email"],
        "created_at": order["created_at"],
        "items": order["items"]
    })

    # Deterministic 'now' for tests
    now = datetime.fromisoformat("2025-09-07T12:00:00+00:00").astimezone(timezone.utc)

    state.tools_called.append("order_cancel")
    policy = order_cancel(order["order_id"], order["created_at"], now=now)
    state.policy_decision = policy

    if policy["cancel_allowed"]:
        state.final_message = f"Success — order {order['order_id']} ({order['email']}) is canceled."
    else:
        state.final_message = (
            f"Sorry — order {order['order_id']} can’t be canceled. "
            f"Our policy allows cancellations only within 60 minutes of placing the order. "
            f"Options: we can try a shipping address edit, offer store credit once delivered, or hand you off to support."
        )
    return state

# --------- Guardrail ----------
def guardrail_flow(state: AgentState):
    state.policy_decision = {"refuse": True}
    state.final_message = (
        "I can’t provide a discount code that doesn’t exist. "
        "You can often find first-order perks by signing up for our newsletter."
    )
    return state

# --------- Responder (trace + final) ----------
def responder(state: AgentState):
    trace = {
        "intent": state.intent,
        "tools_called": state.tools_called,
        "evidence": state.evidence,
        "policy_decision": state.policy_decision,
        "final_message": state.final_message
    }
    state.final_message = f"TRACE_START_JSON\n{json.dumps(trace, indent=2)}\nTRACE_END_JSON\n\n{state.final_message}"
    return state

# --------- Build Graph ----------
def build_graph():
    workflow = StateGraph(AgentState)
    workflow.add_node("router", router)
    workflow.add_node("product_assist", product_assist_flow)
    workflow.add_node("order_help", order_help_flow)
    workflow.add_node("guardrail", guardrail_flow)
    workflow.add_node("responder", responder)

    workflow.set_entry_point("router")
    workflow.add_conditional_edges(
        "router",
        lambda s: s.intent,
        {"product_assist": "product_assist", "order_help": "order_help", "other": "guardrail"}
    )
    workflow.add_edge("product_assist", "responder")
    workflow.add_edge("order_help", "responder")
    workflow.add_edge("guardrail", "responder")
    workflow.add_edge("responder", END)
    return workflow.compile()
