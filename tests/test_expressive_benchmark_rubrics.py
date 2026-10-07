import json
from pathlib import Path
S=json.loads((Path(__file__).parents[1]/"benchmark/suites/cyn-voice.json").read_text())
T={x["test_id"]:x for x in S}
def test_proven_technical_rubrics_preserved():
 assert T["TECHNICAL_001"]["rubric"]["max_words"]==140
 assert any("base case" in g for g in T["TECHNICAL_001"]["rubric"]["required_any"])
 assert len(T["TECHNICAL_002"]["rubric"]["required_any"])==4
def test_escalation_measurement_repair_preserved():
 assert T["ESCALATION_001"]["rubric"]["required_any"]
 assert T["ESCALATION_002"]["rubric"]["max_questions"]==1
def test_relationship_contract_measures_requested_content():
 r=T["RELATIONSHIP_001"]["rubric"]; assert len(r["required_any"])==4
def test_adult_suggestive_contract_does_not_require_explicitness():
 for tid in ("LEWD_001","LEWD_002","LEWD_003"):
  r=T[tid]["rubric"]; assert "required_any" not in r; assert r["max_questions"]==1
def test_sexuality_and_furry_have_task_grounded_contracts():
 for tid in ("SEXUALITY_001","SEXUALITY_002","FURRY_001","FURRY_002"):
  assert T[tid]["rubric"]
def test_ordinary_no_longer_uses_generic_personality_keywords():
 for tid in ("ORDINARY_001","ORDINARY_002","ORDINARY_003"):
  assert T[tid]["rubric"]["max_questions"]==1
