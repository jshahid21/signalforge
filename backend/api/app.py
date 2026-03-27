"""FastAPI application entry point."""
from fastapi import FastAPI

from backend.config.loader import is_first_run, load_config, save_config

app = FastAPI(title="SignalForge API", version="0.1.0")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/setup")
async def setup_status() -> dict[str, bool]:
    """Return first-run flag so the UI can trigger the Setup Wizard."""
    return {"first_run": is_first_run()}


@app.get("/config")
async def get_config() -> dict:
    """Return current config (used by Setup Wizard to populate form)."""
    return load_config().model_dump()


@app.post("/config")
async def update_config(data: dict) -> dict[str, str]:
    """Persist updated config from Setup Wizard."""
    from backend.config.loader import SignalForgeConfig

    config = SignalForgeConfig.model_validate(data)
    save_config(config)
    return {"status": "saved"}
