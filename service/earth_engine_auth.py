"""
Earth Engine Authentication Module

Centralized authentication for Google Earth Engine to eliminate code duplication
across the application.
"""

import os

import ee
import streamlit as st
import yaml
from google.oauth2 import service_account


def get_credentials():
    """
    Get Google Earth Engine credentials from Streamlit secrets.

    Returns:
        google.oauth2.service_account.Credentials: Configured credentials object
    """
    credentials_info = {
        "type": st.secrets["gcp_service_account"]["type"],
        "project_id": st.secrets["gcp_service_account"]["project_id"],
        "private_key_id": st.secrets["gcp_service_account"]["private_key_id"],
        "private_key": st.secrets["gcp_service_account"]["private_key"],
        "client_email": st.secrets["gcp_service_account"]["client_email"],
        "client_id": st.secrets["gcp_service_account"]["client_id"],
        "auth_uri": st.secrets["gcp_service_account"]["auth_uri"],
        "token_uri": st.secrets["gcp_service_account"]["token_uri"],
        "auth_provider_x509_cert_url": st.secrets["gcp_service_account"]["auth_provider_x509_cert_url"],
        "client_x509_cert_url": st.secrets["gcp_service_account"]["client_x509_cert_url"],
        "universe_domain": st.secrets["gcp_service_account"]["universe_domain"],
    }

    return service_account.Credentials.from_service_account_info(
        credentials_info, scopes=["https://www.googleapis.com/auth/earthengine"]
    )


def load_local_config():
    """Load local development configuration"""
    config_path = "config.yaml"
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    return None


_INITIALIZED = False


def is_earth_engine_initialized():
    """
    Check if Google Earth Engine is already initialized.

    Tests with a simple Earth Engine operation that will succeed if EE is initialized and fail if not.

    Returns:
        bool: True if Earth Engine is initialized, False otherwise.
    """
    try:
        ee.Number(1).getInfo()
        return True
    except Exception:  # pylint: disable=broad-except
        return False


def initialize_earth_engine():
    """
    Initialize Google Earth Engine with the configured credentials.

    This function handles the complete Earth Engine initialization process
    including credential retrieval and project setup.
    """

    # Streamlit re-executes the page module on every interaction, so this function
    # runs constantly. is_earth_engine_initialized() costs a server round-trip, so
    # remember the result in module state (which survives reruns) and skip it.
    global _INITIALIZED  # pylint: disable=global-statement
    if _INITIALIZED:
        return

    # Check if Earth Engine is already initialized
    if is_earth_engine_initialized():
        # st.info("Earth Engine is already initialized")
        _INITIALIZED = True
        return

    try:
        credentials = get_credentials()
        project_id = st.secrets["gcp_service_account"]["project_id"]
        ee.Initialize(credentials, project=project_id)
        _INITIALIZED = True
        st.success("Earth Engine initialized with service account")
    except (KeyError, FileNotFoundError):
        config = load_local_config()
        if not config or not config.get("development", {}).get("earth_engine", {}).get("project_id"):
            st.error("Local development requires config.yaml with your Earth Engine project ID")
            st.error("1. Copy config.yaml.example to config.yaml")
            st.error("2. Update the project_id with your GCP Project ID")
            st.stop()

        # Fallback to user authentication (for local development)
        try:
            ee.Authenticate()
            project_id = config["development"]["earth_engine"]["project_id"]
            ee.Initialize(project=project_id)
            _INITIALIZED = True
            st.success("Earth Engine initialized with user authentication (local mode)")
        except Exception as e:  # pylint: disable=broad-except
            st.error(f"Earth Engine Authentication Error: {e}")
            st.error("Make sure you have:")
            st.error("1. Run 'earthengine authenticate' locally, OR")
            st.error("2. Set up service account secrets for deployment")
            st.stop()
    except Exception as e:  # pylint: disable=broad-except
        st.error(f"Earth Engine Service Account Error: {e}")
        st.stop()
