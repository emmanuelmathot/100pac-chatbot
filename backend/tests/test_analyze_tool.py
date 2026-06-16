"""Tests du tool d'analyse par code : exécution valide et bac à sable restreint."""

from chatbot.tools.analyze import run_data_analysis


async def _run(code: str) -> dict:
    cmd = await run_data_analysis.ainvoke(
        {
            "args": {"code": code},
            "name": "run_data_analysis",
            "type": "tool_call",
            "id": "t1",
        }
    )
    return cmd.update


async def test_valid_code_returns_result_and_provenance(synthetic_store):
    update = await _run("result = float(fleet.shape[0])")
    assert update["provenance"][0]["status"] == "ok"
    assert update["provenance"][0]["code"] == "result = float(fleet.shape[0])"
    assert update["messages"][0].content == "2.0"


async def test_import_is_blocked(synthetic_store):
    update = await _run("import os\nresult = os.getcwd()")
    assert update["provenance"][0]["status"] == "error"
    assert "Erreur" in update["messages"][0].content


async def test_open_is_blocked(synthetic_store):
    update = await _run("result = open('/etc/passwd').read()")
    assert update["provenance"][0]["status"] == "error"


async def test_computation_on_dataset(synthetic_store):
    update = await _run(
        "result = float(daily['elec_energy_wh'].sel(logement='A').sum())"
    )
    assert update["provenance"][0]["status"] == "ok"
    assert update["messages"][0].content == "4000.0"
