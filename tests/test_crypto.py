import json
from src.core.crypto import sign_bundle, verify_signature

def test_signature_and_tamper_detection():
    data = {
        "event_id": "evt_test",
        "rankings": ["prj_01", "prj_02"],
        "scores": [4.5, 3.8]
    }
    
    canonical_json, sig_hex, pub_hex = sign_bundle(data)
    assert verify_signature(canonical_json, sig_hex, pub_hex) is True

    # Tamper test
    tampered_data = json.loads(canonical_json)
    tampered_data["scores"][0] = 5.0
    tampered_json = json.dumps(tampered_data, sort_keys=True, separators=(',', ':'))
    assert verify_signature(tampered_json, sig_hex, pub_hex) is False
