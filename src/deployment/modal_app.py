"""Modal ASGI app for API deployment."""
import modal

app = modal.App("CMR-API-develop")

image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "fastapi",
        "uvicorn",
        "supabase",
        "pyjwt[crypto]",
        "cryptography",
        "sqlalchemy[asyncio]",
        "asyncpg",
        "pydantic",
        "pydantic-settings",
        "httpx",
        "python-dotenv",
    )
    .add_local_python_source("src")
)


@app.function(
    image=image,
    timeout=300,
    allow_concurrent_inputs=100,
    secrets=[
        modal.Secret.from_name("supabase-credentials-develop"),
        modal.Secret.from_name("app-config-develop"),
    ],
)
@modal.asgi_app()
def asgi_app():
    """Wrap FastAPI app for Modal."""
    from src.api.main import app as fastapi_app
    return fastapi_app
