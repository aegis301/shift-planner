from app.services.mcp_access import mint_mcp_access_token, require_mcp_access


def test_planner_jwt_rejected_for_admin_need():
    token = mint_mcp_access_token(
        user_id=3,
        organization_id=9,
        role="planner",
        shift_group_ids=[4, 5],
    )
    principal = require_mcp_access(token, need="planning")
    assert principal.organization_id == 9
    assert principal.shift_group_ids == (4, 5)
    try:
        require_mcp_access(token, need="admin")
        raise AssertionError("planner JWT must not satisfy admin need")
    except PermissionError:
        pass


def test_wrong_org_token_is_self_contained():
    token = mint_mcp_access_token(user_id=1, organization_id=2, role="admin", shift_group_ids=[])
    principal = require_mcp_access(token, need="admin")
    assert principal.organization_id == 2
