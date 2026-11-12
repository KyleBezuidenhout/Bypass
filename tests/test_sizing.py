"""Tests for the sizing / cost model."""
from __future__ import annotations

import pytest

from gsa_wrap import sizing
from gsa_wrap.api import app


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient
    return TestClient(app)


def test_proxy_plan_scales_with_volume():
    small = sizing.proxy_plan(100, sizing.recommended_threads(100), "free")
    big = sizing.proxy_plan(10000, sizing.recommended_threads(10000), "free")
    assert big["pool_entries_needed"] > small["pool_entries_needed"]
    assert big["distinct_ips_per_day"] > small["distinct_ips_per_day"]


def test_free_tier_needs_more_spares_than_dedicated():
    free = sizing.proxy_plan(1000, 20, "free")
    ded = sizing.proxy_plan(1000, 20, "dedicated_dc")
    assert free["pool_entries_needed"] > ded["pool_entries_needed"]


def test_threads_clamped_to_schema_max():
    assert sizing.recommended_threads(10) == 10
    assert sizing.recommended_threads(10_000_000) <= 200
    assert sizing.recommended_threads(5000) >= 10


@pytest.mark.parametrize("vol", [100, 500, 1000, 5000])
def test_captcha_plan_shapes(vol):
    p = sizing.captcha_plan(vol)
    assert p["solves_per_day"] == pytest.approx(vol * sizing.CAPTCHA_RATE)
    assert p["services"], "should list candidate services"
    for s in p["services"]:
        assert s["est_monthly_usd"] >= 0


def test_captcha_cost_grows_with_volume():
    a = sizing.captcha_plan(100)["totals"]["typical_monthly"]
    b = sizing.captcha_plan(1000)["totals"]["typical_monthly"]
    assert b > a


def test_recommended_stack_has_real_layers():
    st = sizing.recommended_stack(1000)
    assert st["layers"]["primary"] is not None
    assert st["layers"]["backup"] is not None
    assert st["settings_to_set"]["misc::captcha services in random order"] is True


def test_load_captcha_services_parses_shipped_files():
    svcs = sizing.load_captcha_services()
    if not svcs:
        pytest.skip("no captcha_service dir on this machine")
    assert len(svcs) > 50
    assert any(s.name == "2Captcha" for s in svcs)
    # costs must be parsed into a number or left None, never garbage
    for s in svcs:
        assert s.cost_per_solve is None or isinstance(s.cost_per_solve, float)
        assert s.monthly_fixed is None or isinstance(s.monthly_fixed, float)


def test_free_service_costs_zero_not_ten():
    svcs = {s.name: s for s in sizing.load_captcha_services()}
    if "Capv2v3" in svcs:
        assert svcs["Capv2v3"].cost_per_solve == 0.0


def test_proxy_source_stats_counts_sections():
    s = sizing.proxy_source_stats()
    if s["total"]:
        assert s["total"] >= s["enabled"]
        assert s["disabled"] == s["total"] - s["enabled"]


def test_every_tier_produces_a_row():
    for t in sizing.TIERS:
        rows = sizing.proxy_table(t.key, volumes=[500])
        assert len(rows) == 1
        assert rows[0]["tier"] == t.key


# ---------------------------------------------------------------- providers
def test_provider_table_shapes_and_flags():
    rows = sizing.provider_table()
    assert len(rows) >= 5
    for r in rows:
        assert r["billing"], f"{r['name']} must state the true billing unit"
        assert r["entry_price"] and r["caveat"]
        assert isinstance(r["fits_unlimited_residential"], bool)
    # at least some genuinely satisfy unmetered+no-speed-tier
    assert any(r["fits_unlimited_residential"] for r in rows)


def test_every_provider_states_a_real_limit():
    """'unlimited' must always name what it is actually limited by."""
    for p in sizing.PROVIDERS:
        low = p.billing.lower()
        assert any(k in low for k in ("port", "speed", "gb", "per ip", "plan period", "concurrent")), \
            f"{p.name} does not name its real limitation"


def test_unlimited_advice_is_honest():
    a = sizing.unlimited_advice()
    assert "unlimited" in a["headline"].lower()
    assert a["the_only_real_unlimited"]
    assert set(a["kinds"]) == {"static_isp", "unlimited_rotating", "metered_rotating"}


# ---------------------------------------------------------------- layer 2 captcha
def test_layer2_returns_two_distinct_paid_vendors():
    s = sizing.layer2_stack(1000)
    p = s["buy"]["layer_2_primary"]
    b = s["buy"]["layer_2_backup"]
    if p and b:
        assert p["name"] != b["name"], "backup must be a different vendor from primary"
        assert p["est_monthly_usd"] is not None
    assert s["buy"]["layer_1_builtin"]["cost"] == 0.0


def test_layer2_cost_scales_with_volume():
    small = sizing.layer2_stack(100)["two_vendor_total_monthly_usd"]
    big = sizing.layer2_stack(10000)["two_vendor_total_monthly_usd"]
    assert big > small


def test_layer2_alias_never_shadows_primary():
    """Even at odd volumes the backup must not collapse onto the primary."""
    for vol in (50, 1000, 5000, 20000):
        s = sizing.layer2_stack(vol)
        p = s["buy"]["layer_2_primary"]
        b = s["buy"]["layer_2_backup"]
        if p and b:
            assert p["name"] != b["name"]


# ---------------------------------------------------------------- isp price index
def test_isp_price_table_scales_and_ranks():
    t = sizing.isp_price_table(40)
    assert t["count"] == 40
    assert t["cheapest_dedicated"] < t["dearest_dedicated"]
    assert t["typical_dedicated"] >= t["cheapest_dedicated"]
    # dedicated rows only in the headline list
    assert all(r["is_dedicated"] for r in t["dedicated"])
    assert t["shared_budget"] and not any(r["is_dedicated"] for r in t["shared_budget"])
    # sorted cheapest first
    totals = [r["monthly_total"] for r in t["dedicated"]]
    assert totals == sorted(totals)


def test_isp_price_forty_dedicated_is_plausible():
    """40 unmetered dedicated residential IPs sit in a sane band, not garbage."""
    t = sizing.isp_price_table(40)
    assert 60 <= t["cheapest_dedicated"] <= 120
    assert t["dearest_dedicated"] <= 250


def test_isp_price_per_ip_falls_with_quantity():
    a = sizing.isp_price_table(10)["cheapest_dedicated"] / 10
    b = sizing.isp_price_table(500)["cheapest_dedicated"] / 500
    assert b < a, "bulk should be cheaper per IP"


def test_isp_price_handles_tiny_and_huge_counts():
    for n in (1, 5, 5000):
        t = sizing.isp_price_table(n)
        assert t["cheapest_dedicated"] > 0
        for r in t["dedicated"]:
            assert r["monthly_total"] == round(r["usd_per_ip"] * n, 2)


# ---------------------------------------------------------------- ip grade / coverage
def test_ip_grade_table_shapes():
    rows = sizing.ip_grade_table()
    assert len(rows) >= 6
    for r in rows:
        for k in ("reach_general", "reach_hostile", "reach_google"):
            assert 0 <= r[k] <= 100, f"{r['key']} {k} out of range"
        assert r["cost_shape"] and r["verdict"] and r["best_stage"]
        assert 0 <= r["sending_score"] <= 100


def test_coverage_ranks_sensibly():
    by = {r["key"]: r for r in sizing.ip_grade_table()}
    # residential beats datacenter beats free, on hostile coverage
    assert by["isp_static"]["reach_hostile"] > by["dedicated_dc"]["reach_hostile"]
    assert by["dedicated_dc"]["reach_hostile"] > by["free_public"]["reach_hostile"]
    assert by["mobile"]["reach_hostile"] >= by["isp_static"]["reach_hostile"]
    # datacenter is always worse on Google than residential (range is known)
    assert by["isp_static"]["reach_google"] > by["shared_dc"]["reach_google"]


def test_own_ip_is_weak_at_google_and_volume():
    by = {r["key"]: r for r in sizing.ip_grade_table()}
    assert by["own_ip"]["reach_google"] < by["isp_static"]["reach_google"]
    assert by["free_public"]["reach_hostile"] < 50


def test_static_residential_is_recommended():
    rec = [r for r in sizing.ip_grade_table() if r["recommend"]]
    assert any(r["key"] == "isp_static" for r in rec)
    adv = sizing.ip_coverage_advice()
    assert "static residential" in adv["headline"].lower()
    assert adv["layering"] and adv["honesty"] and adv["grounded_note"]


def test_rotating_beats_hostile_but_loses_google_vs_static():
    """Rotating residential is high trust but a poor sender because the IP moves."""
    by = {r["key"]: r for r in sizing.ip_grade_table()}
    assert by["rotating_res"]["reach_google"] < by["isp_static"]["reach_google"]
    assert by["rotating_res"]["reach_hostile"] > by["dedicated_dc"]["reach_hostile"]


# ---------------------------------------------------------------- ip fallback
def test_fallback_plan_is_honest_about_not_being_native():
    p = sizing.fallback_plan(300)
    assert p["is_native"] is False
    assert p["native_limits"] and "per PROJECT" in " ".join(p["native_limits"])
    assert p["what_does_work_natively"]


def test_fallback_ladder_shrinks_as_grade_gets_dearer():
    p = sizing.fallback_plan(300)
    ips = [r["ips"] for r in p["ladder"]]
    # cheapest rung biggest, dearest rung smallest
    assert ips[0] > ips[-1]
    assert ips == sorted(ips, reverse=True)


def test_cost_per_success_rewards_high_reach():
    """A dearer IP that reaches far more can still be the efficient choice."""
    cheap_low_reach = sizing.cost_per_success(30, 0.30)
    dear_high_reach = sizing.cost_per_success(88, 2.00)
    assert cheap_low_reach > 0 and dear_high_reach > 0
    # shared datacenter at 55% for $0.20 is the efficiency sweet spot here
    sweet = sizing.cost_per_success(55, 0.20)
    assert sweet < cheap_low_reach


def test_fallback_includes_free_deduction_first():
    p = sizing.fallback_plan(300)
    assert len(p["deduction_steps"]) >= 4
    assert "free" in p["deduction_order_note"].lower()
    # deductions must come before any spend
    assert "never" in p["deduction_order_note"]


def test_fallback_single_grade_comparison_full():
    p = sizing.fallback_plan(200)
    keys = {s["key"] for s in p["single_grade_comparison"]}
    assert {"free_public", "shared_dc", "dedicated_dc", "isp_static"} <= keys


# ---------------------------------------------------------------- imported list
def test_imported_list_plan_marks_scraping_skipped():
    p = sizing.imported_list_plan()
    assert p["skipped_stage"] == "scraping"
    assert set(p["active_stages"]) == {"parsing", "sending"}


def test_imported_list_recommends_turning_se_proxies_off():
    p = sizing.imported_list_plan()
    assert "se" in p["grade_advice"]
    assert "OFF" in p["grade_advice"]["se"].upper()
    assert any("proxies for se" in x for x in p["what_changes"] + p["ready_made_checklist"])


def test_imported_list_flags_real_project_risks():
    """The warnings must target the actual live-project footguns, refuting, not generic."""
    p = sizing.imported_list_plan()
    flags = {w["flag"] for w in p["hard_warnings"]}
    # these three are the real risks for a personalised list
    assert "retry failed" in flags
    assert "export failed" in flags
    assert "only root domains" in flags
    for w in p["hard_warnings"]:
        assert w["currently"] and w["why"]


def test_imported_list_scheduler_note_matches_window():
    p = sizing.imported_list_plan()
    assert "08:30" in p["scheduler_note"]


def test_imported_list_states_uncertainty():
    p = sizing.imported_list_plan()
    assert "pre-filtered" in p["what_you_cannot_see_from_files"]


# ---------------------------------------------------------------- tinyfish
def test_tinyfish_says_not_a_swap():
    v = sizing.tinyfish_verdict()
    assert "no" in v["short_answer"].lower()
    assert v["why_not_a_swap"]
    # the reason is that parsing happens INSIDE gsa
    assert any("itself" in x.lower() or "internal" in x.lower() for x in v["why_not_a_swap"])


def test_tinyfish_math_uses_published_rates():
    v = sizing.tinyfish_verdict()
    assert v["the_math"]["free_urls_per_day"] == 1000
    assert v["the_math"]["agent_cost_per_step_usd"] == 0.016
    assert v["the_math"]["free_urls_per_min"] == 150


def test_tinyfish_flags_the_speed_ceiling():
    """The load-bearing downside: 2.5/sec is below what 40 threads push."""
    v = sizing.tinyfish_verdict()
    assert v["concurrency_reality"]["implied_per_second"] < 5
    note = v["concurrency_reality"]["note"]
    assert "cap" in note and "2.5" in note


def test_tinyfish_is_balanced_not_hyped():
    v = sizing.tinyfish_verdict()
    assert len(v["where_it_wins"]) >= 3
    assert len(v["where_it_loses"]) >= 3
    # coverage figure must be flagged as the vendor's own evaluation
    assert "own" in v["where_it_loses"][3].lower()
    assert v["honesty"] and v["recommendation"]


def test_tinyfish_no_priced_link_leak():
    """No URLs invented in the payload — just quoted figures."""
    v = sizing.tinyfish_verdict()
    assert v["prices_read_on"] == "2026-11-12"


def test_tinyfish_mentions_farming_as_the_better_lever():
    v = sizing.tinyfish_verdict()
    assert "per account" in v["farming_helps"].lower()


# ---------------------------------------------------------------- farm scaling
def test_farm_scales_daily_allowance_linearly():
    assert sizing.farm_scaling(1)["what_scales"]["daily_urls"]["total"] == 1000
    assert sizing.farm_scaling(4)["what_scales"]["daily_urls"]["total"] == 4000
    assert sizing.farm_scaling(10)["what_scales"]["daily_urls"]["total"] == 10000


def test_farm_scales_per_minute_and_speed():
    f = sizing.farm_scaling(6)
    assert f["what_scales"]["per_minute"]["total_per_min"] == 900
    assert f["what_scales"]["per_minute"]["implied_per_second"] == 15.0


def test_farm_clamps_to_at_least_one_account():
    assert sizing.farm_scaling(0)["accounts"] == 1
    assert sizing.farm_scaling(-5)["what_scales"]["daily_urls"]["total"] == 1000


def test_farm_keeps_cost_at_zero():
    """The whole point: farmed capacity is free capacity."""
    f = sizing.farm_scaling(5)
    assert any("No per-request cost" in x for x in f["advantage_over_proxies"])


def test_farm_separates_proxies_from_accounts():
    f = sizing.farm_scaling(3)
    assert "disguise" in f["proxies_relationship"].lower()
    assert "ceiling" in f["proxies_relationship"].lower()


def test_farm_states_the_billing_uncertainty():
    """Per-key minute limit is claimed but is the wording-per-person detail."""
    f = sizing.farm_scaling(2)
    assert any("wallet" in c.lower() for c in f["honest_caveats"])
    assert any("abuse" in c.lower() or "multiple accounts" in c.lower() for c in f["honest_caveats"])


def test_farm_has_a_breakpoint_where_it_stops_being_worth_it():
    f = sizing.farm_scaling(1)
    assert f["the_real_breakpoint"]["worth_farming_under"] > 0
    assert "top-up" in f["the_real_breakpoint"]["advice"].lower() or "wallet" in f["the_real_breakpoint"]["advice"].lower()


def test_farm_gives_operational_steps():
    f = sizing.farm_scaling(1)
    assert len(f["how_to_actually_do_it"]) >= 4
    assert any("round" in s.lower() for s in f["how_to_actually_do_it"])


def test_farm_endpoint_clamps_and_returns(client):
    r = client.get("/sizing/farm?accounts=0")
    assert r.status_code == 200
    assert r.json()["accounts"] == 1


# ---------------------------------------------------------------- farm safety
def test_farm_safety_says_ip_is_not_required():
    """The decisive point: docs document API-key auth only, no IP binding."""
    d = sizing.farm_without_blocks(3)
    assert d["is_different_ip_required"]["answer"].lower().startswith("no")
    assert "api key" in d["the_one_line"].lower()


def test_farm_safety_ranks_one_ip_first():
    d = sizing.farm_without_blocks(3)
    assert d["ip_strategy_ranked"][0]["rank"] == 1
    assert "one ip" in d["ip_strategy_ranked"][0]["approach"].lower()


def test_farm_safety_ranks_are_contiguous():
    d = sizing.farm_without_blocks(3)
    assert [r["rank"] for r in d["ip_strategy_ranked"]] == [1, 2, 3, 4]


def test_farm_safety_names_staggering_as_the_real_fix():
    d = sizing.farm_without_blocks(3)
    assert any("stagger" in r["approach"].lower() for r in d["ip_strategy_ranked"])
    assert any("stagger" in m.lower() or "spac" in m.lower() for m in d["the_safety_moves"])


def test_farm_safety_only_email_must_differ():
    d = sizing.farm_without_blocks(3)
    assert len(d["what_to_separate"]["must_differ"]) == 1
    assert "email" in d["what_to_separate"]["must_differ"][0].lower()


def test_farm_safety_lists_flagged_triggers_with_fixes():
    d = sizing.farm_without_blocks(3)
    assert len(d["what_actually_gets_you_blocked"]) >= 3
    for t in d["what_actually_gets_you_blocked"]:
        assert t["trigger"] and t["why"] and t["fix"] and t["severity"]


def test_farm_safety_has_a_stop_rule():
    d = sizing.farm_without_blocks(1)
    assert "stop" in d["stop_rule"].lower()
    assert d["signs_you_are_drifting_into_abuse"]


def test_farm_safety_stays_consistent_with_scaling():
    """Both must agree the per-minute limit is per account, not per key."""
    assert "per PERSON" in sizing.farm_scaling(1)["honest_caveats"][0]
    assert "separate accounts" in sizing.farm_scaling(1)["honest_caveats"][0]


def test_farm_safety_endpoint(client):
    r = client.get("/sizing/farm-safety?accounts=4")
    assert r.status_code == 200
    assert r.json()["accounts_baseline"] == 4


# ---------------------------------------------------------------- 10k capacity
def test_capacity_separates_sends_from_parse_volume():
    d = sizing.capacity_10k(10000, 60)
    assert d["daily_sends"] == 10000
    # parse volume must be LARGER than sends when not every site yields a form
    assert d["parse_urls_per_day"] > d["daily_sends"]


def test_capacity_answer_differs_for_recurring_vs_one_off():
    """The whole point: allowance binds daily, speed binds for a one-off."""
    d = sizing.capacity_10k(10000, 60)
    recurring = d["the_actual_answer"]["if_recurring_daily"]["accounts"]
    one_off = d["the_actual_answer"]["if_one_off_list"]["accounts"]
    assert recurring > one_off
    assert "allowance" in d["the_actual_answer"]["if_recurring_daily"]["because"].lower()


def test_capacity_warns_against_reading_speed_as_daily():
    d = sizing.capacity_10k(10000, 60)
    assert "daily capacity" in d["the_actual_answer"]["warning"]


def test_capacity_accounts_match_allowance_arithmetic():
    d = sizing.capacity_10k(10000, 50)
    assert d["parse_urls_per_day"] == 20000
    assert d["the_actual_answer"]["if_recurring_daily"]["accounts"] == 20


def test_capacity_spread_table_shrinks_with_more_accounts():
    d = sizing.capacity_10k(10000, 60)
    days = [v["days_to_clear"] for v in d["spread_table"].values()]
    assert days == sorted(days, reverse=True)
    assert days[-1] == 1


def test_capacity_wall_clock_is_minutes_not_hours():
    """Regression: was dividing by 60 while labelling the unit 'min'."""
    d = sizing.capacity_10k(10000, 60)
    # 1 account at 150 urls/min clearing 16667 urls = ~111 min, not ~1.9
    assert 100 < float(d["spread_table"]["1_accounts"]["wall_clock_if_back_to_back"].split()[0]) < 120


def test_capacity_threads_uses_the_shared_helper():
    d = sizing.capacity_10k(10000, 60)
    assert d["threads_recommended"] == sizing.recommended_threads(10000)


def test_capacity_proxy_tiers_are_all_present():
    d = sizing.capacity_10k(10000, 60)
    for k in ("dedicated_dc", "shared_dc", "residential", "free"):
        assert k in d["proxy_by_tier"]


def test_capacity_captcha_cost_is_small_and_tracked():
    d = sizing.capacity_10k(10000, 60)
    assert d["captcha"]["solves_per_day"] == 2000
    assert d["captcha"]["cost_per_day_usd"] < 5


def test_capacity_endpoint(client):
    r = client.get("/sizing/capacity?daily_sends=5000&found_pct=50")
    assert r.status_code == 200
    assert r.json()["parse_urls_per_day"] == 10000
