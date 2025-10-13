import pytest
import datetime
from unittest.mock import patch, MagicMock

from clients.ImpactClient import ImpactClient


@pytest.fixture
def mock_config(tmp_path):
    # Create a fake config.json file
    config = {
        "account_SID_DK": "test_sid",
        "token_DK": "test_token"
    }
    config_file = tmp_path / "config.json"
    config_file.write_text('{"account_SID_DK": "test_sid", "token_DK": "test_token"}')
    return str(config_file)


@pytest.fixture
def client(mock_config):
    return ImpactClient(mock_config, "DK")


def make_response(status=200, json_data=None):
    """Helper to create fake response objects"""
    mock_resp = MagicMock()
    mock_resp.status_code = status
    mock_resp.json.return_value = json_data or {}
    mock_resp.text = "error"
    return mock_resp


# ---- Tests ----

@patch("clients.ImpactClient.requests.get")
def test_get_actions_success(mock_get, client):
    # First page returns 2 actions
    mock_get.side_effect = [
        make_response(json_data={"Actions": [{"Id": "A1"}, {"Id": "A2"}]}),        # Second page empty -> stop
        make_response(json_data={"Actions": []}),
    ]

    actions = client.get_actions("CAMP123", "2025-09-01", "2025-09-02", page_size=2)

    assert len(actions) == 2
    assert actions[0]["Id"] == "A1"
    assert mock_get.call_count == 2


@patch("clients.ImpactClient.requests.get")
def test_get_actions_http_error(mock_get, client):
    mock_get.return_value = make_response(status=500)

    actions = client.get_actions("CAMP123", "2025-09-01", "2025-09-02")

    assert actions == []  # returns empty on error
    assert mock_get.called


@patch("clients.ImpactClient.requests.get")
def test_retrieve_action_success(mock_get, client):
    mock_get.return_value = make_response(json_data={"Id": "A1", "Status": "APPROVED"})

    result = client.retrieve_action("A1")

    assert result["Id"] == "A1"
    mock_get.assert_called_once()


@patch("clients.ImpactClient.requests.get")
def test_retrieve_action_failure(mock_get, client):
    mock_get.return_value = make_response(status=404)

    result = client.retrieve_action("A1")

    assert result is None


@patch("clients.ImpactClient.requests.put")
def test_update_action_success(mock_put, client):
    mock_put.return_value = make_response(json_data={"Id": "A1", "Updated": True})

    result = client.update_action("A1", 100, "Reason")

    assert result["Updated"] is True
    mock_put.assert_called_once()


@patch("clients.ImpactClient.requests.put")
def test_update_action_failure(mock_put, client):
    mock_put.return_value = make_response(status=400)

    result = client.update_action("A1", 100, "Reason")

    assert result is None


@patch("clients.ImpactClient.requests.delete")
def test_reverse_action_success(mock_delete, client):
    mock_delete.return_value = make_response(json_data={"Id": "A1", "Reversed": True})

    result = client.reverse_action("A1", 50, "Return")

    assert result["Reversed"] is True
    mock_delete.assert_called_once()


@patch("clients.ImpactClient.requests.delete")
def test_reverse_action_failure(mock_delete, client):
    mock_delete.return_value = make_response(status=403)

    result = client.reverse_action("A1", 50, "Return")

    assert result is None
