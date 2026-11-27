import base64
import json


def decode_access_token(token: str) -> dict:
    """Decode a JWT access token **without verifying its signature**.

    Signature verification is already handled by Keycloak's userinfo endpoint
    (which rejects invalid tokens). Here we only need the ``resource_access``
    claim that Keycloak's userinfo does **not** return, so we decode the JWT
    payload to enrich the identity built from userinfo.
    """
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload))
    except Exception:
        return {}


def extract_identity(claims: dict, client_id: str) -> dict | None:
    """Map Keycloak userinfo/token claims to the internal identity shape.

    Roles live under resource_access.<client_id>.roles for a client-scoped
    check, rather than the realm-wide roles every user gets by default.
    """
    user_id = claims.get("sub")
    if not user_id:
        return None

    roles = claims.get("resource_access", {}).get(client_id, {}).get("roles", [])
    return {
        "user_id": user_id,
        "email": claims.get("email", ""),
        "first_name": claims.get("given_name", ""),
        "last_name": claims.get("family_name", ""),
        "roles": roles,
        "is_admin": "admin" in roles or "realm-admin" in roles,
        # Les groupes viennent de la base (issue #660), plus du jeton.
        "groups": [],
        "email_verified": claims.get("email_verified") is True,
    }
