"""
Checks for the AI connector (Task 7).

We never call the real AI in tests (it costs money and needs internet).
Instead we use a FAKE client that pretends to be Claude, so we can test the
"real mode" code path, and what happens when the AI fails.
"""

from types import SimpleNamespace

from app.agents.llm import LLM
from app.agents.quick_read import QuickRead, mock_quick_read


class FakeClaude:
    """Pretends to be the Anthropic client. Returns whatever answer we give it."""

    def __init__(self, answer=None, error=None):
        self.answer, self.error, self.calls = answer, error, []
        self.messages = self      # so code can call fake.messages.create(...)

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(
            content=[SimpleNamespace(type="tool_use", input=self.answer)],
            usage=SimpleNamespace(input_tokens=120, output_tokens=30),
        )


def ask(llm, message="Need it today, price?"):
    return llm.ask(system="test", prompt=message, schema=QuickRead, mock=lambda: mock_quick_read(message))


# ----- Mock mode ---------------------------------------------------------------------
def test_mock_mode_never_calls_the_ai():
    fake = FakeClaude(answer={})
    result = ask(LLM(client=fake, enabled=False))
    assert result.mode == "mock" and fake.calls == []
    assert result.data.asks_price and result.data.wants_it_soon


def test_mock_rules_spot_hinglish():
    answer = mock_quick_read("Bhai Creta ke liye coating kitne ka hai?")
    assert answer["language"] == "hinglish" and answer["asks_price"] is True


def test_mock_rules_spot_hindi_script():
    assert mock_quick_read("मुझे आज अपॉइंटमेंट चाहिए")["language"] == "hindi"


def test_mock_rules_calm_english():
    answer = mock_quick_read("Do you have parking near the gym?")
    assert answer == {"language": "english", "summary": "Do you have parking near the gym?",
                      "asks_price": False, "wants_it_soon": False}


# ----- Real mode (with the fake Claude) ------------------------------------------------
def test_real_mode_uses_the_ai_answer():
    good = {"language": "english", "summary": "Wants a quote today", "asks_price": True, "wants_it_soon": True}
    fake = FakeClaude(answer=good)
    result = ask(LLM(client=fake, enabled=True))
    assert result.mode == "real"
    assert result.data.summary == "Wants a quote today"
    assert result.input_tokens == 120 and result.output_tokens == 30
    sent = fake.calls[0]
    assert sent["tool_choice"] == {"type": "tool", "name": "give_answer"}     # AI must fill the form
    assert sent["tools"][0]["input_schema"]["properties"]["language"]          # form was sent


def test_fast_and_smart_models():
    good = {"language": "english", "summary": "x", "asks_price": False, "wants_it_soon": False}
    fake = FakeClaude(answer=good)
    llm = LLM(client=fake, enabled=True)
    fast = ask(llm)
    smart = llm.ask(system="s", prompt="p", schema=QuickRead, mock=lambda: good, smart=True)
    assert fast.model != smart.model


# ----- Safety net ----------------------------------------------------------------------
def test_ai_failure_falls_back_to_mock():
    fake = FakeClaude(error=ConnectionError("no internet"))
    result = ask(LLM(client=fake, enabled=True))
    assert result.mode == "fallback"
    assert "no internet" in result.error
    assert result.data.wants_it_soon            # still got a sensible answer


def test_weird_ai_answer_falls_back_to_mock():
    fake = FakeClaude(answer={"language": "klingon", "summary": 5})
    result = ask(LLM(client=fake, enabled=True))
    assert result.mode == "fallback"


def test_log_entry_for_the_dashboard():
    entry = ask(LLM(enabled=False)).log_entry("quick_read")
    assert entry["agent"] == "quick_read" and entry["mode"] == "mock"
    assert entry["output"]["asks_price"] is True


# ----- Endpoints -------------------------------------------------------------------------
def test_ai_status_endpoint(client):
    status = client.get("/ai/status").json()
    assert status["mode"] == "mock"
    assert "MOCK_AI=false" in status["how_to_switch"]


def test_ai_try_endpoint(client):
    r = client.post("/ai/try", json={"message": "Bhai Creta ke liye ceramic coating kitne ka hai? Aaj ho jayega?"})
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "mock"
    assert body["answer"]["language"] == "hinglish"
    assert body["answer"]["asks_price"] and body["answer"]["wants_it_soon"]
