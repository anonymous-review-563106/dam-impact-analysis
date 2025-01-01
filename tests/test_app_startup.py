import pytest
import subprocess
import time
import requests


@pytest.fixture(scope="session")
def streamlit_app():
    """Start streamlit app for testing."""
    process = subprocess.Popen([
        "streamlit", "run", "app.py",
        "--server.port", "8503",
        "--server.headless", "true"
    ])

    base_url = "http://localhost:8503"

    for _ in range(60):
        try:
            requests.get(f"{base_url}/healthz", timeout=1)
            break
        except Exception:
            time.sleep(0.5)
    else:
        process.terminate()
        raise RuntimeError("Streamlit app failed to start.")

    yield base_url

    # Cleanup
    process.terminate()
    process.wait()


def test_app_loads(streamlit_app):
    """Test that the main page loads."""
    response = requests.get(streamlit_app)
    assert response.status_code == 200


def test_health_endpoint(streamlit_app):
    """Test the health endpoint."""
    response = requests.get(f"{streamlit_app}/healthz")
    assert response.status_code == 200