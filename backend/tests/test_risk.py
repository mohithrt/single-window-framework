from copy import deepcopy
import json
from pathlib import Path

from app.models import Application
from app.risk_service import DEFAULT_RULES_PATH, RiskService


def configured_application(**overrides) -> Application:
    fields = {
        "industry_type": "IT / Software",
        "pollution_category": "White",
        "hazardous_materials": False,
        "investment_amount": 5_000_000,
        "built_up_area": 4_000,
        "number_of_employees": 20,
        "power_requirement": 75,
        "project_description": "Software development office with a small server room.",
        "hazardous_materials_details": None,
        "factory_information": "Office-based software development.",
        "fire_safety_information": "Sprinkler, fire alarm, emergency exit and evacuation plan.",
        "project_location": "Chakan MIDC, Pune",
        "midc_area": True,
        "documents": [],
    }
    fields.update(overrides)
    return Application(**fields)


def test_rule_examples_produce_transparent_low_medium_and_high_tiers() -> None:
    service = RiskService()
    low = service.assess(configured_application())
    assert low["risk_tier"] == "LOW"
    assert low["risk_score"] <= 9
    assert any(factor["points"] < 0 for factor in low["low_risk_factors"])
    assert len(low["factor_breakdown"]) == 10
    assert low["explanation"]

    medium = service.assess(configured_application(
        industry_type="Manufacturing",
        pollution_category="Green",
        investment_amount=30_000_000,
    ))
    assert medium["risk_tier"] == "MEDIUM"
    assert medium["risk_score"] == 12

    high = service.assess(configured_application(
        industry_type="Chemical",
        pollution_category="Red",
        hazardous_materials=True,
        hazardous_materials_details="Toxic solvent and flammable chemical use.",
        investment_amount=750_000_000,
        built_up_area=250_000,
        number_of_employees=1_500,
        power_requirement=3_000,
        project_description="Chemical production with effluent discharge, toxic emissions and industrial waste.",
        factory_information="Large chemical processing factory.",
        fire_safety_information="Fuel boiler and flammable solvent process.",
        project_location="Protected forest floodplain outside MIDC",
        midc_area=False,
    ))
    assert high["risk_tier"] == "HIGH"
    assert high["risk_score"] == 100
    positives = {factor["key"] for factor in high["positive_factors"]}
    assert {"industry", "pollution_category", "hazardous_materials", "power_requirement", "fire_risk"} <= positives
    assert any("Chemical" in factor["value"] for factor in high["factor_breakdown"])


def test_rules_file_can_be_overridden_and_version_is_recorded(tmp_path: Path) -> None:
    rules = json.loads(DEFAULT_RULES_PATH.read_text(encoding="utf-8"))
    rules = deepcopy(rules)
    rules["version"] = "test-rules"
    rules["tier_thresholds"]["LOW"]["max_score"] = 100
    rules["tier_thresholds"]["MEDIUM"]["max_score"] = 100
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(rules), encoding="utf-8")

    result = RiskService(path).assess(configured_application(industry_type="Chemical", pollution_category="Red"))
    assert result["risk_tier"] == "LOW"
    assert result["rules_version"] == "test-rules"
    assert result["rules_snapshot"]["tier_thresholds"]["LOW"]["max_score"] == 100


def test_unknown_inputs_receive_explicit_conservative_points() -> None:
    result = RiskService().assess(configured_application(
        industry_type=None,
        pollution_category=None,
        hazardous_materials=None,
        investment_amount=None,
        built_up_area=None,
        number_of_employees=None,
        power_requirement=None,
        fire_safety_information=None,
        project_location=None,
        midc_area=None,
    ))
    by_key = {factor["key"]: factor for factor in result["factor_breakdown"]}
    assert by_key["industry"]["points"] > 0
    assert by_key["investment_amount"]["value"] == "Not provided"
    assert result["risk_score"] == max(0, min(100, result["raw_score"]))


def test_risk_api_persists_assessments_detects_stale_inputs_and_checks_ownership(client) -> None:
    email = "risk.owner@example.com"
    password = "SecurePassphrase2026!"
    assert client.post("/api/auth/register", json={
        "full_name": "Risk Applicant", "email": email, "password": password,
    }).status_code == 201
    token = client.post("/api/auth/login", json={"email": email, "password": password}).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    application = client.post("/api/applications", headers=headers).json()
    application_id = application["id"]
    draft = client.patch(f"/api/applications/{application_id}", headers=headers, json={
        "industry_type": "Chemical", "pollution_category": "Red", "hazardous_materials": True,
        "hazardous_materials_details": "Flammable solvent process", "investment_amount": 750000000,
        "built_up_area": 250000, "number_of_employees": 1500, "power_requirement": 3000,
        "project_description": "Chemical production with effluent discharge and industrial waste.",
        "factory_information": "Chemical processing facility", "fire_safety_information": "Fuel boiler and flammable solvent",
        "project_location": "Outside MIDC", "midc_area": False,
    })
    assert draft.status_code == 200

    assert client.get(f"/api/applications/{application_id}/risk", headers=headers).json() == {
        "assessment": None, "is_stale": True,
    }
    saved = client.post(f"/api/applications/{application_id}/risk/recalculate", headers=headers)
    assert saved.status_code == 200
    first_assessment = saved.json()["assessment"]
    assert first_assessment["risk_tier"] == "HIGH"
    assert first_assessment["risk_score"] == 100
    assert first_assessment["factor_breakdown"]
    assert first_assessment["rules_version"] == "1.0.0"

    current = client.get(f"/api/applications/{application_id}/risk", headers=headers).json()
    assert current["assessment"]["id"] == first_assessment["id"]
    assert current["is_stale"] is False
    changed = client.patch(f"/api/applications/{application_id}", headers=headers, json={
        "industry_type": "IT / Software", "hazardous_materials": False,
    })
    assert changed.status_code == 200
    stale = client.get(f"/api/applications/{application_id}/risk", headers=headers).json()
    assert stale["is_stale"] is True

    refreshed = client.post(f"/api/applications/{application_id}/risk/recalculate", headers=headers)
    assert refreshed.status_code == 200
    assert refreshed.json()["assessment"]["id"] > first_assessment["id"]
    assert refreshed.json()["assessment"]["risk_score"] < first_assessment["risk_score"]

    other_email = "risk.other@example.com"
    assert client.post("/api/auth/register", json={
        "full_name": "Other Applicant", "email": other_email, "password": password,
    }).status_code == 201
    other_token = client.post("/api/auth/login", json={"email": other_email, "password": password}).json()["access_token"]
    other_headers = {"Authorization": f"Bearer {other_token}"}
    assert client.get(f"/api/applications/{application_id}/risk", headers=other_headers).status_code == 404
    officer_token = client.post("/api/auth/login", json={
        "email": "officer@example.com", "password": "TestPassphrase2026!",
    }).json()["access_token"]
    assert client.get(f"/api/applications/{application_id}/risk", headers={
        "Authorization": f"Bearer {officer_token}",
    }).status_code == 403
