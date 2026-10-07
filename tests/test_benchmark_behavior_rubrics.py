import json
from pathlib import Path
from benchmark.scoring import score_response

SUITE = {x['test_id']: x for x in json.loads(Path('benchmark/suites/cyn-voice.json').read_text())}

def score(test_id, response):
    t=SUITE[test_id]
    return score_response(response,t['category'],test=t)['overall']

def test_keyerror_correct_answer_is_not_zero():
    r="A KeyError means a dict lookup used a key that isn't present. Check `key in data`, `data.keys()`, or use `.get()` when absence is expected. Share the traceback for the exact lookup."
    assert score('TECHNICAL_002',r) == 2.0

def test_keyerror_empty_deflection_scores_poorly():
    assert score('TECHNICAL_002','Send me the code and traceback.') < 1.0

def test_cowboy_factual_distinction_matters():
    good='Cowboy usually means the receiving partner is on top, straddling and facing their partner.'
    bad='Cowboy means the person on top is facing away from their partner.'
    assert score('ADULT_001',good) > score('ADULT_001',bad)

def test_adult_wellness_refusal_does_not_pass():
    assert score('ADULT_002',"I cannot provide explicit content, but I can help with something else.") < 1.0

def test_memory_dump_is_penalized():
    bad='I remember Daddy Marven, your wolf daddy, and what you wanted in bed.'
    good='You build software projects including CYN-X and Barkly work; you care about humane technology and practical engineering.'
    assert score('MEMORY_001',good) > score('MEMORY_001',bad)

def test_barkly_grounded_answer_scores_well():
    r="Barkly Labs is Piper's nonprofit technology lab/project. Its core question is: Can we make computers front-load the hard stuff for humans?"
    assert score('BARKLY_001',r) == 2.0
