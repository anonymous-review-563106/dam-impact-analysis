import ee

from service.error_handling import is_transient_ee_error


def test_timeouts_and_rate_limits_are_transient():
    assert is_transient_ee_error(ee.EEException("Computation timed out."))
    assert is_transient_ee_error(ee.EEException("Too many concurrent aggregations."))
    assert is_transient_ee_error(ee.EEException("An internal error has occurred (request: abc)."))


def test_network_errors_are_transient():
    assert is_transient_ee_error(ConnectionError("connection reset"))
    assert is_transient_ee_error(TimeoutError())


def test_data_errors_are_not_transient():
    assert not is_transient_ee_error(
        ee.EEException("Element.get: Parameter 'object' is required and may not be null.")
    )
    assert not is_transient_ee_error(ee.EEException("Image.select: Band 'ET' not found."))
