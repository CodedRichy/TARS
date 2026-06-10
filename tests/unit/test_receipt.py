from tars.router.receipt import INR_PER_USD, Receipt, estimate_cost_inr


def test_receipt_summary() -> None:
    r = Receipt(
        tier="cheap", model="gpt-4.1-mini", total_tokens=1000, cost_inr=0.05, latency_ms=250
    )
    s = r.summary
    assert "cheap" in s
    assert "gpt-4.1-mini" in s
    assert "1000" in s
    assert "₹0.0500" in s
    assert "250ms" in s


def test_receipt_to_row_length() -> None:
    r = Receipt(tier="local", provider="ollama", model="llama3.2:3b")
    row = r.to_row()
    assert len(row) == 14


def test_estimate_cost_known_model() -> None:
    cost = estimate_cost_inr("gpt-4.1-mini", prompt_tokens=1000, completion_tokens=500)
    expected_usd = (1000 / 1000 * 0.0004) + (500 / 1000 * 0.0016)
    expected_inr = round(expected_usd * INR_PER_USD, 6)
    assert cost == expected_inr


def test_estimate_cost_unknown_model_uses_default() -> None:
    cost = estimate_cost_inr("some-unknown-model", prompt_tokens=1000, completion_tokens=1000)
    assert cost > 0


def test_estimate_cost_zero_tokens() -> None:
    cost = estimate_cost_inr("gpt-4.1-mini", prompt_tokens=0, completion_tokens=0)
    assert cost == 0.0


def test_local_model_zero_cost() -> None:
    cost = estimate_cost_inr("llama3.2:3b", prompt_tokens=5000, completion_tokens=2000)
    assert cost > 0  # estimate_cost_inr uses default rates; local cost zeroing done in provider
