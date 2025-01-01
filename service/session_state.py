"""
Session State Management for Beaver Impacts Analysis Application.

This module provides centralized management of Streamlit session state variables
for the beaver dam impact analysis workflow. It handles initialization of all
application state including user progress, data collections, configuration
settings, and UI flags.

The session state is organized into several categories:
- Data collections (dam locations, waterways, analysis results)
- Workflow progress and step completion
- Configuration values (buffer sizes, validation parameters)
- UI state (map visibility, section expansion)

Classes:
    SessionStateManager: Static methods for initializing and managing session state

Usage:
    from session_state import SessionStateManager

    # Initialize all session state variables at app startup
    SessionStateManager.initialize()

    # Reset workflow state when starting over
    SessionStateManager.reset_workflow()

Note:
    This module depends on constants.py for default values and assumes
    Streamlit's session_state is available in the global context.
"""

from typing import Any, Optional, Dict, List

import streamlit as st
import ee

from service.constants import AppConstants


class SessionStateManager:
    """Centralized session state management with type hints and validation"""

    @staticmethod
    def initialize():
        """Initialize all session state variables."""
        SessionStateManager._init_basic_state()
        SessionStateManager._init_step_completion()

    @staticmethod
    def _init_basic_state():
        """Initialize basic state from constants"""
        if hasattr(AppConstants, "SESSION_DEFAULTS"):
            for key, default_value in AppConstants.SESSION_DEFAULTS.items():
                if key not in st.session_state:
                    st.session_state[key] = default_value

    @staticmethod
    def _init_step_completion():
        """Initialize step completion states"""
        for i in range(1, 7):
            step_key = f"step{i}_complete"
            if step_key not in st.session_state:
                st.session_state[step_key] = False

    @staticmethod
    def reset_workflow():
        """Reset workflow-related state (useful for starting over)."""
        workflow_keys = [
            "validation_complete",
            "buffer_complete",
            "buffers_created",
            "visualization_complete",
            "show_non_dam_section",
        ]
        for key in workflow_keys:
            st.session_state[key] = False

        for i in range(1, 7):
            st.session_state[f"step{i}_complete"] = False

    @staticmethod
    def get(key: str, default: Any = None) -> Any:
        """Get value from session state with optional default"""
        return st.session_state.get(key, default)

    @staticmethod
    def set(key: str, value: Any) -> None:
        """Set value in session state"""
        st.session_state[key] = value

    @staticmethod
    def set_multiple(data: Dict[str, Any]) -> None:
        """Set multiple values in session state"""
        for key, value in data.items():
            st.session_state[key] = value

    @staticmethod
    def has(key: str) -> bool:
        """Check if key exists in session state"""
        return key in st.session_state

    @staticmethod
    def delete(key: str) -> None:
        """Remove key from session state if it exists"""
        if key in st.session_state:
            del st.session_state[key]

    # Step management methods
    @staticmethod
    def complete_step(step_num: int) -> None:
        """Mark a step as complete"""
        st.session_state[f"step{step_num}_complete"] = True

    @staticmethod
    def is_step_complete(step_num: int) -> bool:
        """Check if a step is complete"""
        return st.session_state.get(f"step{step_num}_complete", False)

    @staticmethod
    def get_completed_steps() -> List[int]:
        """Get list of completed step numbers"""
        completed = []
        for key in st.session_state.keys():
            if key.endswith("_complete") and key.startswith("step"):
                try:
                    step_num = int(key.split("step")[1].split("_")[0])
                    if st.session_state[key]:
                        completed.append(step_num)
                except (IndexError, ValueError):
                    continue
        return sorted(completed)

    @staticmethod
    def reset_from_step(step_num: int, max_steps: int = 6) -> None:
        """Reset all steps from given step number onwards"""
        for i in range(step_num, max_steps + 1):
            SessionStateManager.set(f"step{i}_complete", False)

        # Reset related state variables
        state_to_reset = [
            "validation_complete",
            "validation_step",
            "validation_summary",
            "analysis_coverage_warning",
            "analysis_mode",
            "analysis_point_count",
            "analysis_label",
            "visualization_complete",
            "buffer_complete",
            "show_non_dam_section",
        ]
        for key in state_to_reset:
            if key in st.session_state:
                del st.session_state[key]

    # Data validation methods
    @staticmethod
    def validate_required_data(required_keys: Dict[str, str]) -> Optional[str]:
        """Returns error message if required data missing, None if all present"""
        for key, description in required_keys.items():
            if not SessionStateManager.has(key) or SessionStateManager.get(key) is None:
                return f"Missing required data: {description}"
        return None

    @staticmethod
    def validate_earth_engine_data(data_keys: Dict[str, str]) -> Optional[str]:
        """Validate Earth Engine data exists and has content"""
        for key, description in data_keys.items():
            data = SessionStateManager.get(key)
            if data is None:
                return f"Missing required data: {description}"

            # For Earth Engine FeatureCollections, check if they have features
            if hasattr(data, "size"):
                try:
                    size = data.size().getInfo()
                    if size == 0:
                        return f"Empty dataset: {description}"
                except Exception:
                    return f"Invalid Earth Engine data: {description}"
        return None

    # Specific getter methods for common data
    @staticmethod
    def get_dam_data() -> Optional[ee.FeatureCollection]:
        """Get dam data from session state"""
        return SessionStateManager.get("Dam_data")

    @staticmethod
    def get_positive_collection() -> Optional[ee.FeatureCollection]:
        """Get positive dam collection from session state"""
        return SessionStateManager.get("Positive_collection")

    @staticmethod
    def get_waterway_data() -> Optional[ee.FeatureCollection]:
        """Get waterway data from session state"""
        return SessionStateManager.get("selected_waterway")

    @staticmethod
    def get_merged_collection() -> Optional[ee.FeatureCollection]:
        """Get merged collection from session state"""
        return SessionStateManager.get("Merged_collection")

    @staticmethod
    def get_analysis_summary() -> Dict[str, Any]:
        """Get summary of current analysis state"""
        return {
            "completed_steps": SessionStateManager.get_completed_steps(),
            "has_dam_data": SessionStateManager.get_dam_data() is not None,
            "has_waterway_data": SessionStateManager.get_waterway_data() is not None,
            "validation_status": SessionStateManager.get("validation_step"),
            "buffer_radius": SessionStateManager.get("buffer_radius"),
            "use_all_dams": SessionStateManager.get("use_all_dams"),
        }


def check_prerequisites(required_steps: List[int]) -> bool:
    """Check if prerequisites for a step are met"""
    for req_step in required_steps:
        if not SessionStateManager.is_step_complete(req_step):
            return False
    return True


def show_prerequisite_error(step_name: str, required_steps: List[int]) -> None:
    """Display error message for missing prerequisites"""
    if len(required_steps) == 1:
        st.error(f"Please complete Step {required_steps[0]} before proceeding with {step_name}.")
    else:
        step_list = ", ".join([f"Step {s}" for s in required_steps])
        st.error(f"Please complete {step_list} before proceeding with {step_name}.")
