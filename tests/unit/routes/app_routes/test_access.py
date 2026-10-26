from pit_panel.web.routes.app_routes.access import can_access_subdomain


def test_non_owner_cannot_access_subdomain():
    user = type("User", (), {"id": 2, "is_admin": False})()
    subdomain = type("Subdomain", (), {"owner_user_id": 1, "is_main_domain": False})()
    assert can_access_subdomain(user, subdomain) is False
