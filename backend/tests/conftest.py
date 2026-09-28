import os
import tempfile

_TMP = tempfile.mkdtemp(prefix="doculens-test-")
os.environ["UPLOAD_DIR"] = os.path.join(_TMP, "uploads")
os.environ["PROCESSED_DIR"] = os.path.join(_TMP, "processed")
os.environ["INDEX_DIR"] = os.path.join(_TMP, "indexes")
os.environ["REPORT_DIR"] = os.path.join(_TMP, "reports")
os.environ["MAX_FILE_SIZE_MB"] = "1"

import pytest  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.services import file_service, vector_store  # noqa: E402

get_settings.cache_clear()
get_settings().ensure_dirs()


@pytest.fixture(autouse=True)
def clean_state():
    file_service.clear_all()
    vector_store.clear()
    yield
    file_service.clear_all()
    vector_store.clear()
