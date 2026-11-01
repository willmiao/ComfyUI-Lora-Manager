from types import SimpleNamespace

from py.metadata_collector.constants import SIZE
from py.metadata_collector.node_extractors import BaseSamplerExtractor


def _extract(shape):
    metadata = {}
    inputs = {"latent_image": {"samples": SimpleNamespace(shape=shape)}}
    BaseSamplerExtractor.extract_latent_dimensions("1", inputs, metadata)
    return metadata


def test_image_latent_records_pixel_size():
    size = _extract((1, 4, 128, 96))[SIZE]["1"]
    assert (size["height"], size["width"]) == (1024, 768)


def test_audio_latent_has_no_pixel_size():
    # Audio latents such as YuE2 are [batch, channels, frames]: three dimensions, no width.
    assert SIZE not in _extract((1, 64, 1500))


def test_video_latent_uses_trailing_spatial_dims():
    # Video latents such as Wan are [batch, channels, frames, height/8, width/8].
    size = _extract((1, 16, 21, 60, 104))[SIZE]["1"]
    assert (size["height"], size["width"]) == (480, 832)
