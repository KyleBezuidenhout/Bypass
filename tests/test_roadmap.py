"""
The roadmap docs quote generated numbers. These tests keep them honest, so a
change to the sizing model cannot leave the written decision quietly wrong.
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest

from gsa_wrap import sizing
from gsa_wrap.api import app

ROADMAP = Path(__file__).resolve().parent.parent / "upgrades-roadmap"


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    return TestClient(app)


@pytest.fixture(scope="module")
def capacity():
    return sizing.capacity_10k(10000, 60)


def test_roadmap_folder_and_docs_exist():
    for name in ("README.md", "parsing-strategy.md", "capacity-10k.md", "open-questions.md"):
        assert (ROADMAP / name).is_file(), f"{name} missing"


def test_roadmap_records_the_local_parser_decision():
    readme = (ROADMAP / "README.md").read_text(encoding="utf-8")
    assert "local GSA parser" in readme
    strat = (ROADMAP / "parsing-strategy.md").read_text(encoding="utf-8")
    assert "Keep the local GSA parser" in strat


def test_parsing_decision_states_a_revisit_trigger():
    """A decision without a revisit condition is just a preference."""
    strat = (ROADMAP / "parsing-strategy.md").read_text(encoding="utf-8")
    assert "Trigger to revisit" in strat
    assert "200" in strat


def test_capacity_doc_matches_live_capacity_numbers(capacity):
    doc = (ROADMAP / "capacity-10k.md").read_text(encoding="utf-8")

    assert f"{capacity['daily_sends']:,}" in doc
    assert str(capacity["threads_recommended"]) in doc
    # the doc rounds the long figure for readability (16,667 -> ~16,700)
    assert f"~{round(capacity['parse_urls_per_day'], -2):,}" in doc
    # the recurring-daily answer is the load-bearing number
    assert str(capacity["the_actual_answer"]["if_recurring_daily"]["accounts"]) in doc


def test_capacity_doc_shows_both_scenarios(capacity):
    doc = (ROADMAP / "capacity-10k.md").read_text(encoding="utf-8")
    assert "Recurring daily" in doc
    assert "One-off list" in doc
    one_off = capacity["the_actual_answer"]["if_one_off_list"]["accounts"]
    assert f"**~{one_off}**" in doc


def test_capacity_doc_flags_the_assumption(capacity):
    """60% is an assumption, and the doc must say so rather than imply certainty."""
    doc = (ROADMAP / "capacity-10k.md").read_text(encoding="utf-8")
    assert "unmeasured" in doc
    assert f"{capacity['found_pct']}%" in doc


def test_open_questions_are_actually_open(capacity):
    doc = (ROADMAP / "open-questions.md").read_text(encoding="utf-8")
    assert "Status:** open" in doc
    # the measurement is the shared blocker
    assert "discovery" in doc.lower()


def test_readme_links_every_doc():
    readme = (ROADMAP / "README.md").read_text(encoding="utf-8")
    for name in ("parsing-strategy.md", "capacity-10k.md", "open-questions.md",
                 "import-schedule-and-proxies.md"):
        assert name in readme, f"{name} not linked"


def test_readme_documents_regeneration_command():
    readme = (ROADMAP / "README.md").read_text(encoding="utf-8")
    assert "capacity_10k" in readme
    assert "/sizing/capacity" in readme


# ---------------------------------------------------------------- import + schedule doc
def test_import_doc_names_the_upload_location():
    doc = (ROADMAP / "import-schedule-and-proxies.md").read_text(encoding="utf-8")
    assert "GSA_WebsiteContact" in doc
    assert "imports" in doc


def test_import_doc_explains_header_is_the_mapping():
    """The load-bearing fact: there is no separate mapping table."""
    doc = (ROADMAP / "import-schedule-and-proxies.md").read_text(encoding="utf-8")
    assert "%csv-Message%" in doc
    assert "header row" in doc


def test_import_doc_flags_that_sending_is_off():
    """sender on=0 means nothing sends — the most actionable finding."""
    doc = (ROADMAP / "import-schedule-and-proxies.md").read_text(encoding="utf-8")
    assert "sender on" in doc
    assert "OFF" in doc


def test_import_doc_states_unproven_areas():
    doc = (ROADMAP / "import-schedule-and-proxies.md").read_text(encoding="utf-8")
    assert "unproven" in doc.lower()


def test_proxy_recommendation_scales_with_volume():
    small = sizing.proxy_recommendation(5000)
    big = sizing.proxy_recommendation(10000)
    assert big["ips_to_actually_buy"] > small["ips_to_actually_buy"]
    assert small["ips_to_actually_buy"] >= small["threads"]


def test_proxy_recommendation_picks_dedicated_not_shared():
    d = sizing.proxy_recommendation(5000)
    assert "ISP" in d["recommended_type"]["grade"]
    assert "shared datacenter" in d["recommended_type"]["not"].lower()
    assert any("shared" in w["option"].lower() for w in d["what_not_to_buy"])


def test_proxy_recommendation_has_spares_over_threads():
    d = sizing.proxy_recommendation(5000)
    assert d["ips_to_actually_buy"] >= math.ceil(d["threads"] * 1.1) - 1
    assert d["spare_reasoning"]


def test_proxy_recommendation_cheapest_matches_vendor_table():
    d = sizing.proxy_recommendation(5000)
    table = sizing.isp_price_table(d["ips_to_actually_buy"])["dedicated"]
    assert d["vendors_ranked"][0]["usd_per_ip"] == min(v["usd_per_ip"] for v in table)


def test_proxy_doc_matches_live_numbers():
    doc = (ROADMAP / "import-schedule-and-proxies.md").read_text(encoding="utf-8")
    d = sizing.proxy_recommendation(5000)
    assert str(d["threads"]) in doc
    assert str(d["ips_to_actually_buy"]) in doc
    assert d["vendors_ranked"][0]["name"] in doc


def test_proxies_for_endpoint(client):
    r = client.get("/sizing/proxies-for?daily_sends=5000")
    assert r.status_code == 200
    assert r.json()["daily_sends"] == 5000


def test_proxy_doc_covers_rotating_residential():
    doc = (ROADMAP / "import-schedule-and-proxies.md").read_text(encoding="utf-8")
    assert "rotating residential" in doc.lower()
    assert "sticky" in doc.lower()
    # doc rounds 61.0 -> "61 GB/month"
    gb = sizing.rotating_residential_verdict(5000)["cost_math"]["gb_per_month_total"]
    assert f"{gb:g} GB/month" in doc


def test_proxy_doc_covers_cheap_tiers_and_their_real_loss():
    doc = (ROADMAP / "import-schedule-and-proxies.md").read_text(encoding="utf-8")
    d = sizing.cheap_proxy_tradeoff(5000)
    assert "concentrated" in doc.lower()
    assert "loud" in doc.lower() and "silent" in doc.lower()
    # doc rounds 7.7 -> "~7.7%"
    assert f"{d['loss_model']['blended_loss_pct']}%" in doc
    # and the dedicated-datacenter step-down must be offered
    assert "dedicated datacenter" in doc.lower()


# ---------------------------------------------------------------- rotating residential
def test_rotating_splits_parse_vs_send():
    d = sizing.rotating_residential_verdict(5000)
    assert "yes" in d["would_they_work"]["for_parsing"].lower()
    assert "no" in d["would_they_work"]["for_sending"].lower()


def test_rotating_flags_the_sticky_problem_as_the_crux():
    d = sizing.rotating_residential_verdict(5000)
    assert "sticky" in d["the_sticky_problem"]["and_gsa_cannot_fix_it"].lower() or \
           "no sticky-session setting" in d["the_sticky_problem"]["and_gsa_cannot_fix_it"].lower()
    assert "rotation" in d["the_sticky_problem"]["their_wording"].lower()


def test_rotating_costs_more_than_dedicated_at_scale():
    """The load-bearing economic finding."""
    d = sizing.rotating_residential_verdict(5000)
    c = d["the_comparison"]
    assert c["rotating_monthly_low"] > c["dedicated_monthly"]
    assert "more" in c["verdict"].lower()


def test_rotating_warns_off_the_headline_rate():
    d = sizing.rotating_residential_verdict(5000)
    assert d["cost_math"]["headline_rate_per_gb"] < d["cost_math"]["realistic_rate_per_gb"][0]
    assert "headline" in d["cost_math"]["why_not_headline"].lower()


def test_rotating_gb_math_scales_with_volume():
    small = sizing.rotating_residential_verdict(1000)["cost_math"]
    big = sizing.rotating_residential_verdict(10000)["cost_math"]
    assert big["gb_per_month_total"] > small["gb_per_month_total"]


def test_rotating_gives_a_workaround_and_a_caveat():
    d = sizing.rotating_residential_verdict(5000)
    assert d["the_workaround"]["idea"]
    # must not oversell: the workaround is unproven
    assert "unproven" in d["the_workaround"]["caveat"].lower()


def test_rotating_keeps_sending_on_dedicated():
    d = sizing.rotating_residential_verdict(5000)
    assert "dedicated" in d["recommendation"]["sending"].lower()
    assert "residential" in d["recommendation"]["parsing"].lower()


def test_rotating_endpoint(client):
    r = client.get("/sizing/rotating-residential?daily_sends=5000")
    assert r.status_code == 200
    assert r.json()["daily_sends"] == 5000


# ---------------------------------------------------------------- ipnux checkout
def test_ipnux_flags_headline_vs_checkout_gap():
    """The load-bearing finding: marketing $2 vs checkout $9."""
    d = sizing.ipnux_checkout_reality(33)
    h = d["headline_problem"]
    assert h["marketing_says_usd_per_ip"] == 2.00
    assert h["checkout_quoted_usd_per_ip"] == 9.00
    assert h["multiple"] > 4


def test_ipnux_names_the_quality_selector_as_the_cause():
    d = sizing.ipnux_checkout_reality(33)
    names = [t["name"] for t in d["the_quality_selector"]]
    assert "Regular" in names and "Premium" in names


def test_ipnux_explains_which_tier_is_selected_by_default():
    """Premium was pre-selected in the screenshot; that is the trap."""
    d = sizing.ipnux_checkout_reality(33)
    premium = next(t for t in d["the_quality_selector"] if t["name"] == "Premium")
    assert "default" in premium["verdict_for_sending"].lower()
    assert d["which_tier_for_sending"]["pick"] == "Regular"


def test_ipnux_regular_is_cheaper_than_premium():
    d = sizing.ipnux_checkout_reality(33)
    c = d["cost_impact"]
    assert c["at_regular"] < c["at_premium_default"]
    assert c["saving_from_downgrading_tier"] > 0


def test_ipnux_tells_you_to_check_the_total_not_the_headline():
    d = sizing.ipnux_checkout_reality(33)
    assert any("total" in h.lower() for h in d["checkout_hygiene"])
    assert any("dedicated" in h.lower() for h in d["checkout_hygiene"])


def test_ipnux_cost_scales_with_count():
    small = sizing.ipnux_checkout_reality(10)["cost_impact"]
    big = sizing.ipnux_checkout_reality(100)["cost_impact"]
    assert big["at_premium_default"] > small["at_premium_default"]


def test_ipnux_stays_honest_about_the_source():
    d = sizing.ipnux_checkout_reality(33)
    assert "read-from-screen" in d["honesty"] or "read from screen" in d["honesty"]
    assert d["observed_on"] == "2026-11-12"


def test_ipnux_endpoint(client):
    r = client.get("/sizing/ipnux?ips=33")
    assert r.status_code == 200
    assert r.json()["ips"] == 33



def test_split_doc_matches_live_numbers():
    doc = (ROADMAP / "import-schedule-and-proxies.md").read_text(encoding="utf-8")
    d = sizing.split_test_design(5000, 10)
    ss = d["sample_size"]
    assert str(ss["n_per_arm_for_pooled_finding"]) in doc
    assert str(ss["minimum_total_attempts"]) in doc
    assert "stratified" in doc.lower()
    assert "canary" in doc.lower()
    assert "noise floor" in doc.lower()


# ---------------------------------------------------------------- cheap proxies, real loss
def test_cheap_says_not_useless_but_admits_loss():
    d = sizing.cheap_proxy_tradeoff(5000)
    assert "not useless" in d["straight_answer"].lower()
    assert "concentrated" in d["straight_answer"].lower()


def test_cheap_loss_is_zero_on_unprotected_sites():
    """The whole point: cheap fails on hard sites, not easy ones."""
    d = sizing.cheap_proxy_tradeoff(5000)
    free = next(c for c in d["loss_model"]["by_site_class"] if c["class"] == "No protection")
    assert free["cheap_loss_pct"] == 0


def test_cheap_blended_loss_is_a_minority_not_a_washout():
    d = sizing.cheap_proxy_tradeoff(5000)
    assert 5 < d["loss_model"]["blended_loss_pct"] < 25


def test_cheap_shared_penalty_stacks_on_datacenter_penalty():
    d = sizing.cheap_proxy_tradeoff(5000)
    m = d["loss_model"]
    assert m["total_cheap_vs_good_loss_pct"] > m["blended_loss_pct"]
    assert m["shared_extra_pct"] > 0


def test_cheap_loss_model_declares_its_guesses():
    d = sizing.cheap_proxy_tradeoff(5000)
    assert "not measured" in d["loss_model"]["assumption_warning"].lower()


def test_cheap_dedicated_isp_is_the_zero_loss_baseline():
    d = sizing.cheap_proxy_tradeoff(5000)
    isp = next(o for o in d["options_ranked"] if o["option"] == "Dedicated static ISP")
    assert isp["loss_pct"] == 0.0


def test_cheap_option_loss_decreases_as_price_rises():
    d = sizing.cheap_proxy_tradeoff(5000)
    losses = [o["loss_pct"] for o in d["options_ranked"]]
    assert losses == sorted(losses, reverse=True)


def test_cheap_names_the_loud_silent_asymmetry():
    d = sizing.cheap_proxy_tradeoff(5000)
    a = d["the_dominant_asymmetry"]
    assert "loud" in a["insight"].lower() and "silent" in a["insight"].lower()
    assert "silent" in a["silent"].lower() or "no error" in a["silent"].lower()


def test_cheap_says_spend_on_sending_first():
    d = sizing.cheap_proxy_tradeoff(5000)
    assert "send" in d["the_dominant_asymmetry"]["consequence"].lower()


def test_cheap_keeps_the_two_axes_separate():
    d = sizing.cheap_proxy_tradeoff(5000)
    t = d["two_axes_do_not_collapse_them"]
    assert "reputation" in t["axis_1"].lower()
    assert "network" in t["axis_2"].lower()


def test_cheap_breakeven_recovers_real_volume():
    d = sizing.cheap_proxy_tradeoff(5000)
    b = d["breakeven"]
    assert b["extra_sends_you_get_back"] > 1000
    assert b["implied_value_per_send_to_justify"] < 0.10


def test_cheap_breakeven_scales_with_volume():
    small = sizing.cheap_proxy_tradeoff(1000)
    big = sizing.cheap_proxy_tradeoff(10000)
    assert big["breakeven"]["extra_sends_you_get_back"] > small["breakeven"]["extra_sends_you_get_back"]


def test_cheap_warns_failures_are_being_lost_silently():
    d = sizing.cheap_proxy_tradeoff(5000)
    c = d["cost_of_getting_it_wrong"]
    assert "retry failed" in c["fix_first"]
    assert "recoverable" in c


def test_cheap_compromise_splits_pools_by_stage():
    d = sizing.cheap_proxy_tradeoff(5000)
    c = d["the_smart_compromise"]
    assert "send_pool" in c and "parse_pool" in c
    assert str(d["ips"]) in c["send_pool"]


def test_cheap_cheapest_non_stupid_is_datacenter_not_residential():
    d = sizing.cheap_proxy_tradeoff(5000)
    joined = " ".join(d["cheapest_non_stupid_setup"]).lower()
    assert "dedicated datacenter" in joined


def test_cheap_offers_a_way_to_measure_instead_of_guess():
    d = sizing.cheap_proxy_tradeoff(5000)
    assert "successfully sent" in d["what_would_actually_settle_it"]["test"].lower()


def test_cheap_endpoint(client):
    r = client.get("/sizing/cheap-proxies?daily_sends=5000")
    assert r.status_code == 200
    assert r.json()["daily_sends"] == 5000


def test_cheap_endpoint_scales(client):
    r = client.get("/sizing/cheap-proxies?daily_sends=1000")
    assert r.json()["monthly_sends"] == 30000



# ---------------------------------------------------------------- split-test design
def test_split_says_captcha_cannot_be_constant():
    d = sizing.split_test_design(5000)
    assert "cannot" in d["the_core_insight"]["why_captcha_cannot_be_constant"].lower()
    assert "stratify" in d["the_core_insight"]["so"].lower()


def test_split_is_stratified_and_randomised():
    d = sizing.split_test_design(5000)
    assert "stratified" in d["design"]["name"].lower() or "block" in d["design"]["name"].lower()
    assert "coin" in d["design"]["randomisation"].lower()


def test_split_metric_is_confirmed_not_http200():
    d = sizing.split_test_design(5000)
    assert d["primary_metric"]["name"] == "confirmed_send_rate"
    assert "not" in d["primary_metric"]["explicitly_not_the_metric"].lower()


def test_split_taxonomy_separates_silent_drop_from_timeout():
    d = sizing.split_test_design(5000)
    codes = [c["code"] for c in d["failure_taxonomy"]]
    assert "silent_drop" in codes
    assert "timeout" in codes
    timeout = next(c for c in d["failure_taxonomy"] if c["code"] == "timeout")
    assert "not" in timeout["note"].lower()


def test_split_taxonomy_covers_harness_and_pool_failures():
    d = sizing.split_test_design(5000)
    codes = [c["code"] for c in d["failure_taxonomy"]]
    assert "field_not_found" in codes
    assert "proxy_dead" in codes


def test_split_sample_size_shrinks_as_effect_grows():
    small = sizing.split_test_design(5000, 20)["sample_size"]["n_per_arm_for_pooled_finding"]
    big = sizing.split_test_design(5000, 5)["sample_size"]["n_per_arm_for_pooled_finding"]
    assert big > small


def test_split_hardened_needs_fewer_than_pooled():
    d = sizing.split_test_design(5000)
    assert d["sample_size"]["n_per_arm_hard_effect"] < d["sample_size"]["n_per_arm_for_pooled_finding"]


def test_split_total_is_twice_per_arm_across_strata():
    d = sizing.split_test_design(5000)
    ss = d["sample_size"]
    expected = sum(s["n_total"] for s in ss["per_stratum"])
    assert ss["minimum_total_attempts"] == expected
    assert ss["recommended_total_with_safety"] == expected * 2


def test_split_days_scale_down_with_volume():
    big = sizing.split_test_design(10000)["sample_size"]["days_at_daily_volume"]
    small = sizing.split_test_design(1000)["sample_size"]["days_at_daily_volume"]
    assert small > big


def test_split_holds_the_usual_suspects_identical():
    d = sizing.split_test_design(5000)
    joined = " ".join(d["must_be_identical"]).lower()
    for needle in ("message", "sender", "captcha solver", "timeout", "thread"):
        assert needle in joined


def test_split_flags_dupecheck_confound_for_paired_variant():
    d = sizing.split_test_design(5000)
    joined = " ".join(c["confound"] + c["fix"] for c in d["confounds_to_kill"]).lower()
    assert "dupecheck" in joined


def test_split_flags_warmup_as_a_confound():
    d = sizing.split_test_design(5000)
    names = " ".join(c["confound"].lower() for c in d["confounds_to_kill"])
    assert "warmup" in names or "warm" in names


def test_split_requires_an_aa_noise_floor_and_a_canary():
    d = sizing.split_test_design(5000)
    assert "noise floor" in d["controls"]["negative_aa_noise_floor"]["what"].lower()
    assert "canary" in d["controls"]["positive_canary"]["what"].lower()


def test_split_decision_rule_can_say_draw():
    d = sizing.split_test_design(5000)
    assert "noise floor" in d["decision_rule"]["cant_call_it_if"].lower()


def test_split_gsa_steps_mention_a_project_diff():
    d = sizing.split_test_design(5000)
    joined = " ".join(d["gsa_implementation"]).lower()
    assert "diff" in joined
    assert "retry failed" in joined


def test_split_states_what_it_does_not_prove():
    d = sizing.split_test_design(5000)
    assert len(d["what_this_does_not_prove"]) >= 3


def test_split_power_formula_is_sane_for_known_case():
    """n for p=0.5, delta=0.1 at alpha .05 / power .8 is ~385 per arm."""
    n = sizing._n_per_arm(0.5, 0.10)
    assert 370 <= n <= 400


def test_split_endpoint(client):
    r = client.get("/sizing/split-test?daily_sends=5000&detect_pp=10")
    assert r.status_code == 200
    assert r.json()["sample_size"]["detect_pp"] == 10.0


def test_split_endpoint_rejects_silly_detect_pp(client):
    r = client.get("/sizing/split-test?detect_pp=999")
    assert r.json()["sample_size"]["detect_pp"] == 40.0



# ---------------------------------------------------------------- procurement plan
def test_procurement_is_deliberately_smaller_than_full_scale():
    d = sizing.procurement_plan(5000, 10)
    assert d["scale_check"]["test_attempts_needed"] < d["scale_check"]["full_scale_daily_sends"] * 2
    assert "do not buy the full" in d["key_point"].lower()


def test_procurement_pairs_cheap_against_clean():
    d = sizing.procurement_plan(5000, 10)
    labels = " ".join(a["label"].lower() for a in d["arms"])
    assert "shared datacenter" in labels
    assert "dedicated static isp" in labels


def test_procurement_includes_an_aa_arm():
    d = sizing.procurement_plan(5000, 10)
    assert any(a["arm"] == "B'" for a in d["arms"])


def test_procurement_cost_is_pocket_change():
    d = sizing.procurement_plan(5000, 10)
    assert d["estimated_test_cost_per_month"] < 60


def test_procurement_uses_gsas_own_paste_format():
    d = sizing.procurement_plan(5000, 10)
    assert "login:password@host:port" in d["handover"]["format"]
    assert "@" in d["handover"]["example_line"]


def test_procurement_names_the_handover_folder_and_files():
    d = sizing.procurement_plan(5000, 10)
    files = d["handover"]["files"]
    assert any("arm-a" in k for k in files)
    assert any("arm-b-clean" in k for k in files)


def test_procurement_mentions_proven_builtin_importers():
    d = sizing.procurement_plan(5000, 10)
    joined = " ".join(a["how_to_get"] for a in d["arms"]).lower()
    assert "webshare" in joined
    assert "api" in joined


def test_procurement_warns_about_country_and_minimums():
    d = sizing.procurement_plan(5000, 10)
    joined = " ".join(d["purchase_caveats"]).lower()
    assert "same country" in joined
    assert "minimum" in joined


def test_procurement_hands_over_a_step_list():
    d = sizing.procurement_plan(5000, 10)
    assert len(d["what_i_do_when_you_hand_them_over"]) >= 5


def test_procurement_endpoint(client):
    r = client.get("/sizing/procurement?daily_sends=5000&detect_pp=10")
    assert r.status_code == 200
    assert r.json()["estimated_test_cost_per_month"] > 0


def test_procurement_pool_files_exist_on_disk():
    d = sizing.procurement_plan(5000, 10)
    for rel in d["handover"]["files"]:
        p = Path(rel)
        assert p.exists(), f"missing handover file {rel}"



# ---------------------------------------------------------------- stages vs captcha
def test_stages_says_captcha_does_not_replace_proxies():
    d = sizing.stage_requirements(5000)
    assert d["straight_answer"].lower().startswith("no")
    assert "different" in d["straight_answer"].lower()


def test_stages_separates_the_three_hops():
    d = sizing.stage_requirements(5000)
    h = d["the_two_hops_they_cannot_do"]
    assert "load the form" in h["hop_1_read"]
    assert "token" in h["hop_2_solve"]
    assert "POST" in h["hop_3_submit"]


def test_stages_marks_only_sending_as_grade_sensitive():
    d = sizing.stage_requirements(5000)
    by = {s["stage"].split(" ")[0]: s for s in d["stage_by_stage"]}
    assert "CHEAP" in by["Parsing"]["grade_needed"]
    assert "CLEAN" in by["Sending"]["grade_needed"]


def test_stages_marks_captcha_stage_as_not_ours():
    d = sizing.stage_requirements(5000)
    cap = next(s for s in d["stage_by_stage"] if s["stage"].startswith("Captcha"))
    assert cap["needs_our_proxy"].lower().startswith("no")


def test_stages_cites_the_real_setting_and_its_live_value():
    d = sizing.stage_requirements(5000)
    p = d["the_setting_that_proves_it"]
    assert p["key"] == "use real captcha ip"
    assert p["live_value"] == 0
    assert "proxy" in p["app_help_text"].lower()


def test_stages_says_parse_pool_can_be_cheap_but_flags_the_caveat():
    d = sizing.stage_requirements(5000)
    p = d["does_the_parse_pool_need_to_be_good"]
    assert p["answer"].lower().startswith("no")
    assert "hostile" in p["one_caveat"].lower()


def test_stages_keeps_solved_but_rejected_as_the_real_risk():
    d = sizing.stage_requirements(5000)
    r = d["the_real_risk_they_do_not_remove"]
    assert "score" in r["detail"].lower()
    assert "reputation" in r["consequence"].lower()


def test_stages_hybrid_puts_cheap_on_parse_and_clean_on_send():
    d = sizing.stage_requirements(5000)
    h = d["the_hybrid_that_maximises_value"]
    assert "cheap" in h["parse_pool"].lower()
    assert "clean" in h["send_pool"].lower()


def test_stages_endpoint(client):
    r = client.get("/sizing/stages?daily_sends=5000")
    assert r.status_code == 200
    assert len(r.json()["stage_by_stage"]) == 3



# ---------------------------------------------------------------- spend breakdown
def test_spend_covers_all_five_buckets():
    d = sizing.spend_breakdown(5000)
    buckets = " ".join(l["bucket"].lower() for l in d["lines"])
    for needle in ("test", "sending", "parse", "captcha", "owned"):
        assert needle in buckets


def test_spend_total_equals_sum_of_lines():
    d = sizing.spend_breakdown(5000)
    recurring = sum(l["usd_month"] for l in d["lines"] if l["scale"] != "one-off, small")
    assert round(recurring, 2) == d["totals"]["recurring_monthly"]


def test_spend_sending_is_the_dominant_bucket():
    d = sizing.spend_breakdown(5000)
    send = next(l for l in d["lines"] if "Sending" in l["bucket"])
    others = [l["usd_month"] for l in d["lines"] if "Sending" not in l["bucket"]]
    assert send["usd_month"] > max(others)


def test_spend_parse_bucket_is_cheap_relative_to_send():
    d = sizing.spend_breakdown(5000)
    send = next(l for l in d["lines"] if "Sending" in l["bucket"])
    parse = next(l for l in d["lines"] if "Parse" in l["bucket"])
    assert parse["usd_month"] < send["usd_month"]


def test_spend_captcha_scales_with_solves_not_sends():
    d = sizing.spend_breakdown(5000)
    cap = next(l for l in d["lines"] if "aptcha" in l["bucket"])
    assert "SOLVES" in cap["scale"]
    assert "10%" in cap["item"] or "solves" in cap["item"].lower()


def test_spend_scales_with_volume():
    assert sizing.spend_breakdown(10000)["totals"]["recurring_monthly"] > \
           sizing.spend_breakdown(1000)["totals"]["recurring_monthly"]


def test_spend_per_send_is_tiny():
    d = sizing.spend_breakdown(5000)
    assert d["totals"]["per_send"] < 0.01


def test_spend_declares_what_is_proven_vs_guessed():
    d = sizing.spend_breakdown(5000)
    led = d["assumption_ledger"]
    assert led["proven_volumes"] and led["labelled_rates"]
    assert "re-run" in led["fix_rule"]


def test_spend_every_bucket_states_its_tradeoff():
    d = sizing.spend_breakdown(5000)
    for l in d["lines"]:
        assert l["without_it"] and l["cheap_alternative"] and l["confidence"]


def test_spend_cheap_version_is_below_full_isp():
    d = sizing.spend_breakdown(5000)
    assert d["cheapest_sane_version"]["rough_monthly"] < d["premium_version"]["rough_monthly"]


def test_spend_endpoint(client):
    r = client.get("/sizing/spend?daily_sends=5000")
    assert r.status_code == 200
    assert r.json()["daily_sends"] == 5000



# ---------------------------------------------------------------- minimum budget
def test_minbudget_separates_attempts_from_pool():
    d = sizing.minimum_budget_test(5000)
    k = d["the_two_knobs_people_conflate"]
    assert "attempt" in k["correctness_knob"].lower()
    assert "ip" in k["budget_knob"].lower()
    assert "longer" in k["the_insight"].lower()


def test_minbudget_recommends_the_tier_sized_for_the_real_gap():
    d = sizing.minimum_budget_test(5000)
    assert d["recommended"]["detect_pp"] == 8.0


def test_minbudget_orders_tiers_by_cost():
    d = sizing.minimum_budget_test(5000)
    costs = [t["usd_month"] for t in d["tiers"]]
    assert costs == sorted(costs)


def test_minbudget_cheaper_tier_detects_a_bigger_gap():
    d = sizing.minimum_budget_test(5000)
    assert d["tiers"][0]["detect_pp"] > d["tiers"][-1]["detect_pp"]


def test_minbudget_stays_under_25_dollars():
    d = sizing.minimum_budget_test(5000)
    assert d["recommended"]["usd_month"] < 25


def test_minbudget_flags_the_minimum_order_floor():
    d = sizing.minimum_budget_test(5000)
    assert "minimum" in d["hard_floor_note"].lower()
    cheap = d["tiers"][0]["breakdown"]["cheap_arm"].lower()
    assert "minimum" in cheap


def test_minbudget_top_tier_includes_the_aa_arm():
    d = sizing.minimum_budget_test(5000)
    assert "B'" in d["recommended"]["arms"]


def test_minbudget_rock_bottom_omits_aa():
    d = sizing.minimum_budget_test(5000)
    assert "only" in d["tiers"][0]["arms"].lower()
    assert d["tiers"][0]["breakdown"]["aa_arm"].startswith("$0")


def test_minbudget_lists_runtime_so_small_pools_stay_viable():
    d = sizing.minimum_budget_test(5000)
    for t in d["tiers"]:
        assert t["approx_runtime_minutes"] > 0


def test_minbudget_declares_the_pacing_guess():
    d = sizing.minimum_budget_test(5000)
    assert "25s" in d["runtime_reality"]["note"] or "labelled" in d["runtime_reality"]["note"].lower()


def test_minbudget_endpoint(client):
    r = client.get("/sizing/minimum-test?daily_sends=5000")
    assert r.status_code == 200
    assert len(r.json()["tiers"]) == 3


# ---------------------------------------------------------------- mac development split
def test_mac_doc_exists_and_is_linked():
    readme = (ROADMAP / "README.md").read_text(encoding="utf-8")
    assert "mac-development.md" in readme
    assert (ROADMAP / "mac-development.md").is_file()


def test_mac_doc_states_the_backend_cannot_move():
    """The load-bearing constraint: GSA is local, so Vercel can host the UI only."""
    doc = (ROADMAP / "mac-development.md").read_text(encoding="utf-8")
    assert "website_contact.exe" in doc
    assert "cannot" in doc.lower()


def test_mac_doc_names_the_env_vars_it_requires():
    doc = (ROADMAP / "mac-development.md").read_text(encoding="utf-8")
    for var in ("PANEL_ORIGINS", "PANEL_SAMESITE", "PANEL_COOKIE_DOMAIN"):
        assert var in doc


def test_mac_doc_warns_samesite_none_needs_https():
    doc = (ROADMAP / "mac-development.md").read_text(encoding="utf-8")
    assert "requires HTTPS" in doc or "requires https" in doc.lower()


def test_mac_doc_prefers_the_no_third_party_cookie_shape():
    """The recommendation must be the path-split, not the *.vercel.app gamble."""
    doc = (ROADMAP / "mac-development.md").read_text(encoding="utf-8")
    assert "path-split" in doc
    assert "third-party" in doc.lower()


def test_env_example_documents_the_panel_vars():
    env = (Path(__file__).resolve().parents[1] / ".env.example").read_text(encoding="utf-8")
    for var in ("PANEL_PASSWORD", "PANEL_ORIGINS", "PANEL_SAMESITE", "PANEL_COOKIE_DOMAIN"):
        assert var in env


def test_dev_server_has_no_third_party_imports():
    src = (Path(__file__).resolve().parents[1] / "dev-server.py").read_text(encoding="utf-8")
    assert "import gsa_wrap" not in src
    assert "fastapi" not in src.lower()
    assert "RELOAD_SNIPPET" in src


def test_gitignore_excludes_the_heavy_gsa_payload():
    gi = (Path(__file__).resolve().parents[1] / ".gitignore").read_text(encoding="utf-8")
    assert "_work/" in gi
    assert ".panel-password" in gi
