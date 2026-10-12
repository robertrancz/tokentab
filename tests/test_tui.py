import asyncio
from pathlib import Path

from tokentab.app import TokenTabApp


def test_demo_tui_mounts(tmp_path: Path):
    app = TokenTabApp(
        db_path=tmp_path / "demo.db",
        config_path=tmp_path / "config.toml",
        demo=True,
    )

    async def _run():
        async with app.run_test() as pilot:
            await pilot.pause()
            assert app.query_one("#overview")
            assert "Metered" in str(app.query_one("#kpi-metered").render())

    asyncio.run(_run())
