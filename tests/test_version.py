import re
from handelsregister.version import __version__


def test_version_format():
    """Test that the version string follows semantic versioning."""
    # Check if version follows semantic versioning (X.Y.Z)
    pattern = r'^\d+\.\d+\.\d+$'
    assert re.match(pattern, __version__), f"Version {__version__} doesn't match semantic versioning format X.Y.Z"
