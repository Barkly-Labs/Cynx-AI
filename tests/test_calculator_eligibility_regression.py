"""Archived-source calculator eligibility regression tests (no Ollama required)."""
import ast
import json
import re
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / 'ai' / 'chat_engine.py'


def _eligibility():
    # Load only the production method: avoids requiring Ollama and unrelated
    # application dependencies when testing an archived source snapshot.
    tree = ast.parse(SOURCE.read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'ChatEngine')
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_calculator_relevant')
    method.decorator_list = []
    module = ast.fix_missing_locations(ast.Module(body=[method], type_ignores=[]))
    ns = {'re': re, 'json': json}
    exec(compile(module, str(SOURCE), 'exec'), ns)
    return ns['_calculator_relevant']


def _call(expression):
    return {'function': {'name': 'calculator', 'arguments': {'expression': expression}}}


def test_social_messages_never_authorize_calculator():
    eligible = _eligibility()
    for user in ('mommy', 'hey mommy', 'hey mommy how are u', ':3', 'owo',
                 'hi', 'hello', "I'm bored", "I'm sad", 'can we talk'):
        for expression in ('3 + 2 * :)', '3 + 2'):
            assert not eligible(user, _call(expression)), (user, expression)


def test_arithmetic_requests_remain_eligible():
    eligible = _eligibility()
    for user, expression in (
        ("what's 3 + 2", '3 + 2'),
        ('calculate 12 * 4', '12 * 4'),
        ('what is 12 * 4', '12 * 4'),
        ('how much is 15% of 80', '15 * 80 / 100'),
        ('divide 144 by 12', '144 / 12'),
        ("what's 20 dollars plus 15 dollars", '20 + 15'),
        ('calculate the average of 4, 7, and 10', '(4 + 7 + 10) / 3'),
    ):
        assert eligible(user, _call(expression)), (user, expression)


def test_invented_operands_are_rejected():
    assert not _eligibility()("what's 3 + 2", _call('300 + 200'))


def test_rejected_call_regenerates_without_tools_and_cannot_be_appended():
    source = SOURCE.read_text(encoding='utf-8')
    assert 'validated_tool_calls = filtered_calculator_calls' in source
    assert 'if (blocked_optional_web_search or blocked_optional_calculator) and not tool_calls:' in source
    assert source.index('validated_tool_calls = filtered_calculator_calls') < source.index('if tool_calls:')
    assert source.index('if (blocked_optional_web_search or blocked_optional_calculator) and not tool_calls:') < source.index('if tool_calls:')
    assert 'tools=None' in source


def test_web_search_and_deterministic_paths_preserved():
    source = SOURCE.read_text(encoding='utf-8')
    assert 'if not retrieval_cue.search(text):' in source
    assert 'tc_name == "web_search"' in source
    assert 'self.tool_router.detect(text)' in source
    assert 'name == "smoke_counter"' in source
