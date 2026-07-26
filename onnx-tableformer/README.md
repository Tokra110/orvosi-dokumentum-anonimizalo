# TableFormer -> ONNX runtime

Working ONNX Runtime port of Docling's TableFormer table-structure model.
This is now integrated through `medical_redactor_onnx/` so the app runtime can
use Docling-quality table reconstruction without PyTorch.

## Status: integrated, artifacts local

- `export_onnx.py` - low-level exporter for the accurate TableFormer checkpoint into three
  graphs: `encoder.onnx` (ResNet + tag-transformer encoder, runs once per
  table), `decoder_step.onnx` (one greedy step with layer-output cache), and
  `bbox_decoder.onnx` (per-cell bbox head, vectorized). Needs torch +
  onnxscript, export-time only.
- `../scripts/export_tableformer_onnx.py` - project-level wrapper that exports
  the runtime layout into `../models/tableformer-onnx/`.
- `ort_tableformer.py` - original spike runtime used for parity work.
- `../medical_redactor_onnx/tableformer_runtime.py` - productionized
  numpy/onnxruntime port of
  `TableModel04_rs.predict()` including the OTSL structure-error correction
  and horizontal-span bbox merging.
- `../medical_redactor_onnx/tableformer_predictor.py` - torch-free subset of
  `TFPredictor.multi_table_predict()` used by Docling.
- `test_parity.py` - renders a synthetic lab-report table, runs both
  implementations on the identical tensor: tag sequences identical, bbox
  coords match to ~5e-7. Skips automatically when torch is absent.

Artifacts are gitignored and reproduced from the project root with:

```bash
.venv/bin/python scripts/export_tableformer_onnx.py
.venv/bin/python onnx-tableformer/test_parity.py
```

The runtime expects:

```text
models/tableformer-onnx/
  encoder.onnx
  encoder.onnx.data
  decoder_step.onnx
  decoder_step.onnx.data
  bbox_decoder.onnx
  bbox_decoder.onnx.data
  word_map.json
  tm_config.json
```

## Numbers (Ryzen workstation, CPU, warm)

| impl | ms/table |
|------|----------|
| torch | ~480 |
| onnxruntime (this port) | ~750 |

The ORT loop is unoptimized: it re-embeds the full tag sequence every step
and pays Python/session overhead per token. Known levers: IO binding, keeping
the embedding lookup incremental, fusing the argmax into the graph.

## Current tradeoffs

- The runtime uses the full cell-matching path (`do_cell_matching=True`):
  `CellMatcher` + `MatchingPostProcessor` snap predicted cells onto PDF text
  tokens. They are pure numpy, vendored in `medical_redactor_onnx/vendor/` so
  `docling-ibm-models` (which imports torch at module import time) is never
  imported at runtime. The earlier no-matching variant lost ~70% of table
  content on real lab reports — do not go back to it.
- Preprocessing must match upstream exactly: normalize with `(img - 255*mean)/std`,
  cv2 bilinear resize to 448, then transpose to **(channels, width, height)** —
  the model is trained on that orientation; standard (C, H, W) mangles rows.
- Coordinate-space handling matters: crop in the resized 1024px page image,
  but translate predicted cell boxes back through the original Docling
  page-scale table bbox before Docling reads text.
- Keep `docling>=2.96,<2.97` pinned until this adapter is retested against a
  newer internal Docling table API.

## Real-document validation (2026-07-05)

Verified against a 2-page Hungarian lab report previously processed by the
torch/CUDA variant: 76/76 table rows reproduced, 71 cell-for-cell identical
(rest are formatting variants), non-table text equivalent. The torch-free
output additionally caught a birth date the torch reference had leaked.
