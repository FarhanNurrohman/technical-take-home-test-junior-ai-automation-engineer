import pytest


@pytest.fixture
def sample_workspace_dir(tmp_path):
    return tmp_path