from app.policy.loader import load_policy

def test_default_policy_schema():
    p=load_policy('data/policies/TN_RERA_Compliance_Rules.json')
    assert len(p.rules)==20
    assert p.rules[0].rule_id=='R01'
    assert p.rules[-1].rule_id=='R20'
