"""Offline unit tests for OCR image preprocessing (no Ollama, no Tesseract run)."""

import numpy as np
import pytest
from PIL import Image

from app.services import ocr_service


def _solid(value: int, size=(200, 120)) -> Image.Image:
    return Image.fromarray(np.full((size[1], size[0]), value, dtype=np.uint8), mode="L")


def test_preprocess_returns_grayscale_binary_image():
    rgb = Image.new("RGB", (300, 200), (200, 190, 170))
    out = ocr_service.preprocess(rgb)
    assert out.mode == "L"
    values = set(np.unique(np.asarray(out)))
    assert values <= {0, 255}, f"expected pure black/white, got {values}"


def test_auto_invert_flips_dark_page_to_light():
    dark = _solid(20)
    out = ocr_service.auto_invert(dark)
    assert np.asarray(out, dtype=np.float32).mean() > 127.5


def test_auto_invert_leaves_light_page_alone():
    light = _solid(230)
    out = ocr_service.auto_invert(light)
    assert np.asarray(out, dtype=np.float32).mean() > 127.5
    assert np.array_equal(np.asarray(out), np.asarray(light))


def test_upscale_enlarges_small_scan():
    small = _solid(240, size=(200, 120))
    out = ocr_service.upscale(small)
    assert min(out.size) >= ocr_service.MIN_SIDE
    assert max(out.size) <= ocr_service.MAX_SIDE


def test_upscale_leaves_large_scan_unchanged():
    large = _solid(240, size=(2000, 1500))
    out = ocr_service.upscale(large)
    assert out.size == large.size


def test_binarize_separates_ink_from_sepia_paper():
    arr = np.full((120, 200), 200, dtype=np.uint8)  # sepia-ish paper
    arr[40:80, 40:160] = 60  # dark ink block
    img = Image.fromarray(arr, mode="L")
    out = np.asarray(ocr_service.binarize(img))
    assert out[10, 10] == 255  # paper -> white
    assert out[60, 60] == 0  # ink -> black


def test_pad_adds_white_border():
    img = _solid(240, size=(100, 100))
    out = ocr_service.pad(img)
    assert out.size == (100 + 2 * ocr_service.PAD, 100 + 2 * ocr_service.PAD)
    corner = np.asarray(out)[0, 0]
    assert corner == 255


def test_otsu_threshold_between_two_modes():
    arr = np.concatenate(
        [np.full(5000, 60, dtype=np.uint8), np.full(5000, 200, dtype=np.uint8)]
    )
    t = ocr_service._otsu_threshold(arr)
    # Threshold must sit at/above the ink mode and below the paper mode so that
    # `arr > t` maps ink->0 and paper->255.
    assert 60 <= t < 200
