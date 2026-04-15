from copy import deepcopy
import pathlib
import sys

sys.path.append(str(pathlib.Path(__file__).resolve().parents[1]))

from calc_engine import build_scenario_dataframe
from config import DEFAULT_INPUT_DATA


def test_generator_disabled_sets_required_count_and_loading_to_zero():
    input_data = deepcopy(DEFAULT_INPUT_DATA)
    input_data["generator_spec"]["enabled"] = False

    scenario_df = build_scenario_dataframe(input_data)

    assert (scenario_df["required_gen_count"] == 0).all()
    assert (scenario_df["gen_loading_pct"] == 0.0).all()


def test_generator_enabled_still_computes_required_count():
    input_data = deepcopy(DEFAULT_INPUT_DATA)
    input_data["generator_spec"]["enabled"] = True

    scenario_df = build_scenario_dataframe(input_data)

    assert (scenario_df["required_gen_count"] >= 1).all()
    assert (scenario_df["gen_loading_pct"] > 0.0).any()
