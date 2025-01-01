"""tests for session_state"""

import streamlit as st

from service.constants import AppConstants
from service.session_state import SessionStateManager, check_prerequisites


def test_session_state_initialization():
    """Test SessionStateManager.initialize() sets defaults"""
    SessionStateManager.initialize()

    assert st.session_state['buffer_radius'] == AppConstants.DEFAULT_BUFFER_RADIUS
    assert st.session_state['validation_complete'] == False
    assert st.session_state['step1_complete'] == False


def test_complete_step():
    """Test step completion tracking"""
    SessionStateManager.initialize()
    SessionStateManager.complete_step(1)

    assert SessionStateManager.is_step_complete(1) == True
    assert SessionStateManager.is_step_complete(2) == False


def test_check_prerequisites():
    """Test prerequisite checking"""
    SessionStateManager.initialize()

    # Step 3 requires steps 1-2
    assert check_prerequisites([1, 2]) == False

    SessionStateManager.complete_step(1)
    SessionStateManager.complete_step(2)
    assert check_prerequisites([1, 2]) == True


def test_reset_from_step():
    """Test resetting clears downstream steps"""
    SessionStateManager.initialize()
    SessionStateManager.complete_step(1)
    SessionStateManager.complete_step(2)
    SessionStateManager.complete_step(3)

    SessionStateManager.reset_from_step(2)

    assert SessionStateManager.is_step_complete(1) == True
    assert SessionStateManager.is_step_complete(2) == False
    assert SessionStateManager.is_step_complete(3) == False