from pulseguard.security.sanitise import hash_handle, sanitise_pii


class TestSanitisePii:
    def test_email_redacted(self):
        result = sanitise_pii("Contact me at user@example.com for details")
        assert "[EMAIL]" in result
        assert "user@example.com" not in result

    def test_phone_us_formats(self):
        for phone in ("555-867-5309", "(555) 867-5309", "+1 555 867 5309", "5558675309"):
            result = sanitise_pii(f"Call me at {phone} please")
            assert phone not in result

    def test_credit_card_redacted(self):
        result = sanitise_pii("my card is 4111111111111111 and it got charged")
        assert "4111111111111111" not in result
        assert "[CARD]" in result

    def test_credit_card_spaced_and_dashed_redacted(self):
        for card in ("4111 1111 1111 1111", "4111-1111-1111-1111", "5500 0000 0000 0004"):
            result = sanitise_pii(f"my card is {card} and it got charged")
            assert card not in result
            assert "[CARD]" in result

    def test_ssn_redacted(self):
        result = sanitise_pii("SSN 123-45-6789 was used")
        assert "123-45-6789" not in result
        assert "[SSN]" in result

    def test_clean_text_unchanged(self):
        text = "My Verizon signal keeps dropping near the bridge"
        assert sanitise_pii(text) == text

    def test_multiple_pii_types(self):
        text = "Email user@test.com or call 800-123-4567"
        result = sanitise_pii(text)
        assert "[EMAIL]" in result
        assert "[PHONE]" in result
        assert "user@test.com" not in result
        assert "800-123-4567" not in result


class TestHashHandle:
    def test_returns_64_char_hex(self):
        h = hash_handle("@JohnDoe")
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)

    def test_deterministic(self):
        assert hash_handle("@JohnDoe") == hash_handle("@JohnDoe")

    def test_case_insensitive(self):
        assert hash_handle("@JohnDoe") == hash_handle("@johndoe")

    def test_strips_whitespace(self):
        assert hash_handle("  @JohnDoe  ") == hash_handle("@johndoe")

    def test_different_handles_different_hashes(self):
        assert hash_handle("@Alice") != hash_handle("@Bob")
