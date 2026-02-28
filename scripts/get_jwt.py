#!/usr/bin/env python3
"""
Authenticate against Supabase and output a JWT token for API testing.

Usage:
  uv run python scripts/get_jwt.py
  uv run python scripts/get_jwt.py --email user@example.com --password secret

Environment:
  SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY - from .env
  SUPABASE_USER_EMAIL, SUPABASE_USER_PASS - optional; can pass via --email/--password

After running, copy the export command to your shell to set JWT_TOKEN, then:
  curl -X POST http://localhost:8000/api/v1/resources \\
    -H "Authorization: Bearer $JWT_TOKEN" \\
    -H "Content-Type: application/json" \\
    -d '{"urls": ["https://example.com/article-1"]}'
"""
import argparse
import os
import sys

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    parser = argparse.ArgumentParser(description="Get Supabase JWT for API testing")
    parser.add_argument("--email", help="Supabase user email (or set SUPABASE_TEST_EMAIL)")
    parser.add_argument("--password", help="Supabase user password (or set SUPABASE_PASSWORD)")
    args = parser.parse_args()

    email = args.email or os.environ.get("SUPABASE_USER_EMAIL")
    password = args.password or os.environ.get("SUPABASE_USER_PASS")

    if not email or not password:
        print("ERROR: Email and password required.", file=sys.stderr)
        print("  Set SUPABASE_USER_EMAIL and SUPABASE_USER_PASS in .env", file=sys.stderr)
        print("  Or pass --email and --password", file=sys.stderr)
        sys.exit(1)

    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_PUBLISHABLE_KEY")
    if not url or not key:
        print("ERROR: SUPABASE_URL and SUPABASE_PUBLISHABLE_KEY must be set in .env", file=sys.stderr)
        sys.exit(1)

    from supabase import create_client

    client = create_client(url, key)
    try:
        session = client.auth.sign_in_with_password({"email": email, "password": password})
    except Exception as e:
        print(f"ERROR: Sign in failed: {e}", file=sys.stderr)
        sys.exit(1)

    jwt_token = session.session.access_token
    print("JWT token generated. Run:")
    print()
    print(f'export JWT_TOKEN="{jwt_token}"')
    print()
    print("Then test the API:")
    print('  curl -X POST http://localhost:8000/api/v1/resources \\')
    print('    -H "Authorization: Bearer $JWT_TOKEN" \\')
    print('    -H "Content-Type: application/json" \\')
    print('    -d \'{"urls": ["https://example.com/article-1"]}\'')


if __name__ == "__main__":
    main()
