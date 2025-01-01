from service.parser import clean_coordinate


class TestCleanCoordinate:
    """Test the clean_coordinate function."""

    def test_clean_coordinate_valid_float(self):
        """Test cleaning valid float strings."""
        assert clean_coordinate("45.123") == 45.123
        assert clean_coordinate(45.123) == 45.123

    def test_clean_coordinate_with_degree_symbol(self):
        """Test cleaning coordinates with degree symbols."""
        assert clean_coordinate("45.123°") == 45.123

    def test_clean_coordinate_with_compass_directions(self):
        """Test cleaning coordinates with N/S/E/W."""
        assert clean_coordinate("45.123N") == 45.123
        assert clean_coordinate("45.123S") == 45.123
        assert clean_coordinate("45.123E") == 45.123
        assert clean_coordinate("45.123W") == 45.123

    def test_clean_coordinate_with_comma_decimal(self):
        """Test cleaning coordinates with comma as decimal separator."""
        assert clean_coordinate("45,123") == 45.123

    def test_clean_coordinate_with_whitespace(self):
        """Test cleaning coordinates with whitespace."""
        assert clean_coordinate("  45.123  ") == 45.123

    def test_clean_coordinate_invalid_input(self):
        """Test handling invalid coordinate inputs."""
        assert clean_coordinate("invalid") is None
        assert clean_coordinate("") is None
        assert clean_coordinate(None) is None

    def test_clean_coordinate_complex_format(self):
        """Test cleaning complex coordinate formats."""
        assert clean_coordinate("45.123°N") == 45.123
        assert clean_coordinate("  45,123°W  ") == 45.123
