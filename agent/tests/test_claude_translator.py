"""The Claude path, offline: a stub client replays forms the way an LLM actually fills them.

The forms below are the sloppy-but-plausible answers seen in a real run (dates as filters, date
columns in group_by, grouping by a value already filtered, no period at all). Whatever the LLM writes,
the cleaning + shared policy + guardrails must land on the same intent as the rule translator.
"""

from types import SimpleNamespace

import pytest

from agent import guardrails
from agent.evaluation import load_cases, score_case
from agent.intent import Refusal
from agent.translate import ClaudeTranslator

CASES = {c["question"]: c for c in load_cases()}

REPLAYS = {
    "How much is the Le City bag in the USA?": {
        "metric": "hero_price", "group_by": [], "group_by_time": False,
        "filters": {"product_label": ["Le City Bag Medium (black)"], "market": ["USA"]}},
    "Price of the Rodeo handbag in Japan in August": {
        "metric": "hero_price", "group_by_time": False,
        "group_by": ["delivery_date", "product_label", "market", "currency_code"],
        "filters": {"product_label": ["Rodeo Handbag Small (black)"], "market": ["JPN"]},
        "time_start": "2026-08-01", "time_end": "2026-08-31"},
    "Hero price of the 3XL sneaker by market in September 2026": {
        "metric": "hero_price", "group_by": ["market", "currency_code"], "group_by_time": False,
        "filters": {"product_label": ["3XL Sneaker (black)"]},
        "time_start": "2026-09-01", "time_end": "2026-09-30"},
    "price of the triple s in korea last week": {
        "metric": "hero_price", "group_by": [], "group_by_time": False,
        "filters": {"product_label": ["Triple S.2 Sneaker (black)"], "market": ["South Korea"]}},
    "How did hero prices change week on week?": {
        "metric": "hero_price_change", "group_by": ["delivery_date"], "group_by_time": False, "filters": {}},
    "What was the like-for-like price change for bags in Japan in September?": {
        "metric": "category_lfl_change", "group_by": [], "group_by_time": False,
        "filters": {"macro_category": ["Bags"], "market": ["JPN"], "report_month": ["2026-09-01"]}},
    "LFL change for small leather goods": {
        "metric": "category_lfl_change", "group_by": [], "group_by_time": False,
        "filters": {"macro_category": ["Small Leather Goods"]}},
    "How many price changes by month?": {
        "metric": "price_change_count", "group_by": ["changed_on_crawl_date"], "group_by_time": False,
        "filters": {}},
    "Compare the LFL change of bags in France and Japan": {
        "metric": "category_lfl_change", "group_by": [], "group_by_time": False,
        "filters": {"macro_category": ["Bags"], "market": ["France", "Japan"]}},
    "What is Balenciaga's revenue in France?": {"metric": None, "group_by": [], "group_by_time": False,
                                                "filters": {}},
}


class StubClient:
    def __init__(self, forms):
        self.forms = forms
        self.messages = self

    def create(self, *, messages, **_):
        form = self.forms[messages[0]["content"]]
        return SimpleNamespace(content=[SimpleNamespace(type="tool_use", input=form)])


@pytest.mark.parametrize("question", list(REPLAYS), ids=[q[:60] for q in REPLAYS])
def test_replayed_llm_form_is_normalised(question, catalogue, vocab):
    translator = ClaudeTranslator(catalogue, vocab, client=StubClient(REPLAYS))
    result = translator.translate(question)
    if not isinstance(result, Refusal):
        result = guardrails.check(result, catalogue, vocab) or result
    assert score_case(CASES[question], result) == []


def test_unmonitored_place_is_refused_before_calling_the_llm(catalogue, vocab):
    translator = ClaudeTranslator(catalogue, vocab, client=StubClient({}))   # any call would KeyError
    assert isinstance(translator.translate("LFL change for shoes in Germany"), Refusal)


def test_tool_schema_has_no_date_columns(catalogue, vocab):
    tool = ClaudeTranslator(catalogue, vocab, client=StubClient({}))._tool()
    props = tool["input_schema"]["properties"]
    dates = {"delivery_date", "report_month", "changed_on_crawl_date"}
    assert not dates & set(props["group_by"]["items"]["enum"])
    assert not dates & set(props["filters"]["properties"])
    assert props["filters"]["properties"]["market"]["items"]["enum"]           # canonical values offered
