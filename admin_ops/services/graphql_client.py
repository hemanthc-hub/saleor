import os
import requests
from flask import request, has_request_context
from logger import get_logger

log = get_logger()

# We expect GRAPHQL_API_URL and SALEOR_APP_TOKEN to be loaded from .env
# Default to port 8000 since that is where Saleor is currently running locally.
SALEOR_URL = os.environ.get("GRAPHQL_API_URL", "http://localhost:8000/graphql/")
raw_token = os.environ.get("SALEOR_APP_TOKEN") or os.environ.get("HEGMA_AUTH_TOKEN", "")
SALEOR_TOKEN = raw_token.replace("Bearer ", "").replace('"', '').strip() if raw_token else ""

def execute_graphql(query: str, variables: dict = None):
    """
    Executes a GraphQL query/mutation against the Saleor API.
    Prioritizes the Authorization header from the incoming Flask request (User JWT).
    Falls back to the SALEOR_APP_TOKEN in .env if no User JWT is provided.
    """
    headers = {
        "Content-Type": "application/json",
    }
    
    # 1. Try to get User's JWT from incoming Flask request
    user_token = None
    if has_request_context():
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            user_token = auth_header.split(" ")[1]
            
    if user_token:
        headers["Authorization"] = f"Bearer {user_token}"
        log.info("Using User JWT for Saleor Request")
    elif SALEOR_TOKEN:
        headers["Authorization"] = f"Bearer {SALEOR_TOKEN}"
        log.info("Using App Token for Saleor Request")
    else:
        log.warning("No User JWT or SALEOR_APP_TOKEN provided! Mutations requiring permissions will fail.")

    payload = {
        "query": query,
        "variables": variables or {}
    }

    try:
        response = requests.post(SALEOR_URL, json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()

        # Catch GraphQL level errors
        if "errors" in data:
            log.error(f"GraphQL Error: {data['errors']}")
            return {"error": data["errors"], "data": None}

        return {"error": None, "data": data.get("data")}
    except requests.exceptions.RequestException as e:
        log.error(f"Network Error connecting to Saleor API: {e}")
        return {"error": str(e), "data": None}
