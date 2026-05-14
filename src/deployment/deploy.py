"""Deploy script for Modal."""
import os
import subprocess
import sys


def validate_modal_workspace(expected_workspace: str) -> bool:
    """Confirm the active Modal profile is authenticated to the expected workspace."""
    try:
        result = subprocess.run(
            ["modal", "profile", "list"],
            capture_output=True, text=True, check=True,
        )
    except subprocess.CalledProcessError as e:
        print(f"❌ Could not run 'modal profile list': {e.stderr or e}", file=sys.stderr)
        return False

    active_workspace = None
    for line in result.stdout.splitlines():
        if "•" in line:
            # Table row format: │ • │ <profile> │ <workspace> │
            cols = [c.strip() for c in line.split("│") if c.strip()]
            # cols: ['•', '<profile>', '<workspace>']
            if len(cols) >= 3:
                active_workspace = cols[2]
            break

    if active_workspace != expected_workspace:
        print(
            f"❌ Wrong Modal workspace. Expected '{expected_workspace}', "
            f"but active profile is '{active_workspace or 'unknown'}'.",
            file=sys.stderr,
        )
        print(
            "   Switch profiles with: modal profile activate <profile-name>",
            file=sys.stderr,
        )
        print(
            "   Or create a new profile with: modal setup",
            file=sys.stderr,
        )
        return False

    print(f"✅ Modal workspace: {active_workspace}")
    return True


def push_modal_secrets(env: str) -> bool:
    """
    Push secrets from .env to Modal for the specified environment.
    Creates/updates supabase-credentials-{env} and app-config-{env}.

    Returns True on success, False on failure.
    """
    required = [
        "SUPABASE_URL",
        "SUPABASE_PUBLISHABLE_KEY",
        "SUPABASE_SECRET_KEY",
        "TRANSACTION_POOLER_URL",
    ]
    missing = [k for k in required if not os.environ.get(k)]
    if missing:
        print(f"❌ Missing required env vars for Modal secrets: {', '.join(missing)}", file=sys.stderr)
        print("   Ensure .env is loaded and contains these values.", file=sys.stderr)
        return False

    modal_project = os.environ.get("MODAL_PROJECT")
    project_args = ["-e", modal_project] if modal_project else []

    # supabase-credentials-{env} (--force overwrites if exists)
    supabase_secret = f"supabase-credentials-{env}"
    supabase_cmd = [
        "modal",
        "secret",
        "create",
        *project_args,
        "--force",
        supabase_secret,
        f"SUPABASE_URL={os.environ['SUPABASE_URL']}",
        f"SUPABASE_PUBLISHABLE_KEY={os.environ['SUPABASE_PUBLISHABLE_KEY']}",
        f"SUPABASE_SECRET_KEY={os.environ['SUPABASE_SECRET_KEY']}",
        f"TRANSACTION_POOLER_URL={os.environ['TRANSACTION_POOLER_URL']}",
    ]
    print(f"🔐 Pushing {supabase_secret} to Modal...")
    try:
        subprocess.run(supabase_cmd, check=True, capture_output=True, text=True)
        print(f"   ✅ {supabase_secret}")
    except subprocess.CalledProcessError as e:
        print(f"   ❌ Failed: {e.stderr or e}", file=sys.stderr)
        return False

    # app-config-{env} (--force overwrites if exists)
    app_secret = f"app-config-{env}"
    scrape_min = os.environ.get("SCRAPE_MIN_WORD_COUNT", "50")
    app_cmd = [
        "modal",
        "secret",
        "create",
        *project_args,
        "--force",
        app_secret,
        f"ENVIRONMENT={env}",
        f"SCRAPE_MIN_WORD_COUNT={scrape_min}",
        f"INGEST_MIN_WORD_COUNT={os.environ.get('INGEST_MIN_WORD_COUNT', '100')}",
        f"SCRAPE_STUCK_TIMEOUT_MINUTES={os.environ.get('SCRAPE_STUCK_TIMEOUT_MINUTES', '15')}",
        f"INGEST_STUCK_TIMEOUT_MINUTES={os.environ.get('INGEST_STUCK_TIMEOUT_MINUTES', '30')}",
        f"NEO4J_URI={os.environ.get('NEO4J_URI', '')}",
        f"NEO4J_USERNAME={os.environ.get('NEO4J_USERNAME', '')}",
        f"NEO4J_PASSWORD={os.environ.get('NEO4J_PASSWORD', '')}",
        f"NEO4J_DATABASE={os.environ.get('NEO4J_DATABASE', 'neo4j')}",
        f"OPENROUTER_API_KEY={os.environ.get('OPENROUTER_API_KEY', '')}",
        f"OPENROUTER_BASE_URL={os.environ.get('OPENROUTER_BASE_URL', 'https://openrouter.ai/api/v1')}",
        f"OPENROUTER_MODEL={os.environ.get('OPENROUTER_MODEL', 'openai/gpt-4o-mini')}",
        f"OPENROUTER_SMALL_MODEL={os.environ.get('OPENROUTER_SMALL_MODEL', 'openai/gpt-4o-mini')}",
        f"OPENROUTER_EMBEDDING_MODEL={os.environ.get('OPENROUTER_EMBEDDING_MODEL', 'openai/text-embedding-3-small')}",
        f"YOUTUBE_API_KEY={os.environ.get('YOUTUBE_API_KEY', '')}",
    ]
    if scraping_proxy_url := os.environ.get("SCRAPING_PROXY_URL"):
        app_cmd.append(f"SCRAPING_PROXY_URL={scraping_proxy_url}")
    print(f"🔐 Pushing {app_secret} to Modal...")
    try:
        subprocess.run(app_cmd, check=True, capture_output=True, text=True)
        print(f"   ✅ {app_secret}")
    except subprocess.CalledProcessError as e:
        print(f"   ❌ Failed: {e.stderr or e}", file=sys.stderr)
        return False

    return True


def push_finance_mcp_secret(project_args: list[str]) -> bool:
    """Push FINANCE_MCP_TOKEN to Modal as finance-mcp-credentials secret."""
    token = os.environ.get("FINANCE_MCP_TOKEN", "")
    if not token:
        print("❌ Missing required env var: FINANCE_MCP_TOKEN", file=sys.stderr)
        print("   Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\"", file=sys.stderr)
        return False

    secret_name = "finance-mcp-credentials"
    cmd = ["modal", "secret", "create", *project_args, "--force", secret_name, f"FINANCE_MCP_TOKEN={token}"]
    print(f"🔐 Pushing {secret_name} to Modal...")
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(f"   ✅ {secret_name}")
    except subprocess.CalledProcessError as e:
        print(f"   ❌ Failed: {e.stderr or e}", file=sys.stderr)
        return False

    return True


def main() -> None:
    """Deploy to Modal. Usage: deploy_dev or deploy_prod."""
    from dotenv import load_dotenv

    load_dotenv()

    expected_workspace = os.environ.get("MODAL_WORKSPACE", "canadian-mining-report")
    if not validate_modal_workspace(expected_workspace):
        sys.exit(1)

    env = "production" if "prod" in (sys.argv[0] or "") else "develop"
    modal_project = os.environ.get("MODAL_PROJECT")
    project_args = ["-e", modal_project] if modal_project else []
    deploy_args = ["modal", "deploy"]
    if modal_project:
        deploy_args.extend(["-e", modal_project])

    # Push secrets from .env to Modal before deploy
    if not push_modal_secrets(env):
        sys.exit(1)
    if not push_finance_mcp_secret(project_args):
        sys.exit(1)

    # Ensure ENVIRONMENT is set so modal_workers uses correct app name and secrets
    deploy_env = os.environ.copy()
    deploy_env["ENVIRONMENT"] = env

    if env in ("develop", "production"):
        subprocess.run([*deploy_args, "src/deployment/modal_app.py"], check=True, env=deploy_env)
        subprocess.run([*deploy_args, "src/deployment/modal_workers.py"], check=True, env=deploy_env)
        subprocess.run([*deploy_args, "src/deployment/modal_mcp_finance.py"], check=True, env=deploy_env)
    else:
        print(f"Unknown environment: {env}")
        sys.exit(1)


if __name__ == "__main__":
    main()
