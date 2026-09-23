"""
Unit tests for Textile's 4-Layer Woven Security Architecture Core.
"""

import pytest

from textile.core.context import OriginToken, OriginType, SeatContext, TrustLevel
from textile.core.intent import IntentNode, IntentValidationError
from textile.core.skein import PolicyViolationError, skein
from textile.core.transaction import Transaction, TransactionStack


def test_layer1_origin_tokens():
    token_voice = OriginToken.create_local_voice("session_123")
    assert token_voice.origin_type == OriginType.LOCAL_VOICE
    assert token_voice.trust_level == TrustLevel.HIGH

    token_seat = OriginToken.create_local_seat("seat_0")
    assert token_seat.origin_type == OriginType.LOCAL_SEAT
    assert token_seat.trust_level == TrustLevel.HIGH

    token_ext = OriginToken.create_external_untrusted("https://malicious.example.com")
    assert token_ext.origin_type == OriginType.EXTERNAL_UNTRUSTED
    assert token_ext.trust_level == TrustLevel.NONE

    seat = SeatContext()
    assert seat.is_authenticated_local_user() is True


def test_layer2_intent_ast_injection_sanitization():
    token_voice = OriginToken.create_local_voice()

    # Valid Intent Node
    valid_node = IntentNode(
        strand_name="hyprland_focus_workspace",
        parameters={"workspace": "2"},
        origin_token=token_voice,
    )
    valid_node.validate_grammar()
    assert valid_node.strand_name == "hyprland_focus_workspace"

    # Malicious injection attempt in strand name
    with pytest.raises(IntentValidationError, match="Invalid strand name format"):
        bad_strand_node = IntentNode(
            strand_name="hyprland_focus; rm -rf /",
            parameters={},
            origin_token=token_voice,
        )
        bad_strand_node.validate_grammar()

    # Shell execution primitive in parameters (subshell syntax)
    with pytest.raises(IntentValidationError, match="Shell execution primitive"):
        bad_param_node = IntentNode(
            strand_name="hyprland_focus_workspace",
            parameters={"workspace": "$(rm -rf /)"},
            origin_token=token_voice,
        )
        bad_param_node.validate_grammar()


def test_layer3_policy_verification_untrusted_rejection():
    token_ext = OriginToken.create_external_untrusted("https://untrusted-site.org")
    token_voice = OriginToken.create_local_voice()

    skein.initialize()

    # Attempting to execute a MUTATE strand with TrustLevel.NONE (external untrusted data)
    untrusted_intent = IntentNode(
        strand_name="file_write",
        parameters={"path": "/tmp/test.txt", "content": "data"},
        origin_token=token_ext,
    )

    with pytest.raises(PolicyViolationError, match="Security Policy Violation"):
        skein.compile_and_execute_intent(untrusted_intent)

    # Executing with TrustLevel.HIGH (local voice) succeeds
    trusted_intent = IntentNode(
        strand_name="file_read",
        parameters={"path": "/tmp/test.txt"},
        origin_token=token_voice,
    )
    # Result returns error if file not found or ok string, but passes Layer 3 policy compiler
    res = skein.compile_and_execute_intent(trusted_intent)
    assert isinstance(res, str)


def test_layer4_transactional_undo_stack():
    stack = TransactionStack()
    rolled_back = []

    def undo_action():
        rolled_back.append("restored")

    tx = Transaction(
        strand_name="canvas_notify",
        parameters={"message": "hello"},
        rollback_handler=undo_action,
    )

    stack.push(tx)
    success, msg = stack.undo_last()
    assert success is True
    assert rolled_back == ["restored"]
