# Approximate per-1K-token prices in USD (Oct 2025)
TOKEN_COSTS = {
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4o": {"input": 0.005, "output": 0.015},
    "text-embedding-3-small": {"input": 0.00002, "output": 0.0},
}

def estimate_cost(model: str, prompt: int, completion: int = 0):
    rates = TOKEN_COSTS.get(model, {"input": 0, "output": 0})
    cost = (prompt / 1000) * rates["input"] + (completion / 1000) * rates["output"]
    return round(cost, 6)
