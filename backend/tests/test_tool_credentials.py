import asyncio

import pytest

from app.models.tool import ToolAuthMode
from app.services.tools.credentials import CredentialsUnavailableError, headers_for


def test_no_auth_sends_no_header() -> None:
    assert asyncio.run(headers_for(ToolAuthMode.NONE, acting_user=None)) == {}


def test_static_token_is_not_available_yet_and_says_so_with_a_stable_code() -> None:
    with pytest.raises(CredentialsUnavailableError) as error:
        asyncio.run(headers_for(ToolAuthMode.STATIC_TOKEN, acting_user="alice"))
    assert error.value.code == "jeton_statique_indisponible"
