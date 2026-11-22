import pyotp

from pit_panel.security.totp import verify_totp


def test_verify_allows_one_step_of_clock_skew(monkeypatch):
    seen = {}

    def fake_verify(self, code, **kwargs):
        seen.update(kwargs)
        return True

    monkeypatch.setattr(pyotp.TOTP, "verify", fake_verify)

    assert verify_totp("JBSWY3DPEHPK3PXP", "123456") is True
    assert seen.get("valid_window") == 1
