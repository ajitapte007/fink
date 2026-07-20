import sys
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

# Setup PYTHONPATH for testing
test_dir = Path(__file__).parent.resolve()
root_dir = test_dir.parent.resolve()
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

# Import the module to test
from static.update_assets import update_assets, DEFAULT_CHARTJS_VERSION

@patch("urllib.request.urlopen")
@patch("urllib.request.Request")
def test_update_assets_success(mock_request, mock_urlopen, tmp_path):
    """Test successful download and file saving of Chart.js."""
    # Create fake response stream
    mock_response = MagicMock()
    mock_response.read.return_value = b"console.log('mock chartjs code');"
    mock_urlopen.return_value.__enter__.return_value = mock_response

    # Patch the destination file path to a temp directory
    dest_file = tmp_path / "chart.js"
    with patch("static.update_assets.Path") as mock_path_cls:
        # Mock Path(__file__).parent to resolve to tmp_path
        mock_path_instance = MagicMock()
        mock_path_instance.parent = tmp_path
        mock_path_cls.return_value = mock_path_instance

        # Run script
        update_assets("4.4.1")

    # Assertions
    assert dest_file.exists()
    assert dest_file.read_bytes() == b"console.log('mock chartjs code');"
    mock_request.assert_called_once_with(
        "https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.js",
        headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    )

@patch("urllib.request.urlopen")
def test_update_assets_network_failure(mock_urlopen, tmp_path):
    """Test updating assets handles connection errors gracefully by raising SystemExit."""
    # Mock connection failure
    mock_urlopen.side_effect = Exception("Connection refused")

    # Patch path resolution to avoid writing anything
    with patch("static.update_assets.Path") as mock_path_cls:
        mock_path_instance = MagicMock()
        mock_path_instance.parent = tmp_path
        mock_path_cls.return_value = mock_path_instance

        # Run script and assert SystemExit is raised
        with pytest.raises(SystemExit) as exc_info:
            update_assets("4.4.1")
        assert exc_info.value.code == 1
