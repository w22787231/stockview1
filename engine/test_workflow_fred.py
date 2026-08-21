"""Regression test for the FRED credential used by the liquidity export step."""

from pathlib import Path


def test_liquidity_export_receives_fred_api_key():
    workflow = (Path(__file__).parents[1] / ".github" / "workflows" / "export-and-deploy.yml").read_text(
        encoding="utf-8"
    )
    section = workflow.split("      - name: Export TGA and reserve forecast", 1)[1].split(
        "      - name: Preserve lite pools' per-stock detail from live", 1
    )[0]
    assert "FRED_API_KEY: ${{ secrets.FRED_API_KEY }}" in section


if __name__ == "__main__":
    test_liquidity_export_receives_fred_api_key()
    print("[workflow-fred] passed")
