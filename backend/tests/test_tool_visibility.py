import uuid

from app.models.tool import ToolVisibility
from app.services.tools.visibility import can_view


def view(
    *,
    user: str = "u",
    admin: bool = False,
    groups: list[str] | None = None,
    owner: str = "o",
    visibility: ToolVisibility = ToolVisibility.PRIVATE,
    server_groups: list[str] | None = None,
) -> bool:
    return can_view(
        user_id=user,
        is_admin=admin,
        groups=groups or [],
        owner_id=owner,
        visibility=visibility,
        server_groups=server_groups or [],
    )


def test_a_private_server_is_seen_by_its_owner_only() -> None:
    assert view(user="o", owner="o")
    assert not view(user="u", owner="o")


def test_a_platform_wide_server_is_seen_by_everyone() -> None:
    assert view(visibility=ToolVisibility.ALL)


def test_a_group_server_is_seen_by_members_of_a_stored_group_only() -> None:
    assert view(visibility=ToolVisibility.GROUPS, groups=["/a", "/b"], server_groups=["/b"])
    assert not view(visibility=ToolVisibility.GROUPS, groups=["/c"], server_groups=["/b"])
    assert not view(visibility=ToolVisibility.GROUPS, groups=[], server_groups=["/b"])


def test_an_administrator_sees_everything() -> None:
    assert view(admin=True, owner=str(uuid.uuid4()), visibility=ToolVisibility.PRIVATE)
