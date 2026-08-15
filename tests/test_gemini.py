"""Kvota va token hisobi mantiqi — API chaqirilmaydi."""

from news_agent.gemini import UsageTracker, _retry_after


class TestRetryAfter:
    def test_reads_delay_from_gemini_429(self):
        exc = RuntimeError(
            "Error code: 429 - Quota exceeded ... Please retry in 28.462710989s."
        )
        assert _retry_after(exc) == 29.462710989

    def test_caps_absurd_delay(self):
        assert _retry_after(RuntimeError("Please retry in 9999s")) == 70.0

    def test_returns_none_when_absent(self):
        assert _retry_after(RuntimeError("Error code: 500 - internal")) is None


class FakeUsage:
    total_input_tokens = 1000
    total_output_tokens = 200
    total_thought_tokens = 50


class TestUsageTracker:
    def test_counts_thinking_tokens_as_output(self):
        tracker = UsageTracker()
        tracker.record(FakeUsage())

        assert tracker.input_tokens == 1000
        assert tracker.output_tokens == 250  # 200 + 50 thinking

    def test_survives_missing_usage(self):
        tracker = UsageTracker()
        tracker.record(None)

        assert tracker.calls == 1
        assert tracker.input_tokens == 0
