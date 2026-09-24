"""Vendored torch-free modules from docling-ibm-models 3.13.2.

`tf_cell_matcher.py`, `matching_post_processor.py`, `otsl.py`, and
`settings.py` are copied unmodified from upstream except for import-path
rewrites. They are pure Python/numpy; vendoring them avoids importing the
`docling_ibm_models` package, whose model modules require torch. Re-sync when
bumping the ONNX TableFormer artifacts to a new upstream release.
"""
