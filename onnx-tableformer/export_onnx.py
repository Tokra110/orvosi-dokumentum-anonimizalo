"""Export docling's TableFormer (accurate) to ONNX.

Produces three graphs plus the word map:
  encoder.onnx      -- image [1,3,448,448] -> enc_out [1,28,28,C], memory [784,1,512]
  decoder_step.onnx -- tags [seq,1], memory, cache [L,cache_len,1,512]
                       -> logits [1,vocab], last_hidden [1,512], new_cache
  bbox_decoder.onnx -- enc_out, tag_H [num_cells,512] -> classes, coords
  word_map.json     -- OTSL tag vocabulary (needed by the greedy loop)

The autoregressive loop, OTSL structure-error correction and span merging
stay in Python (see ort_tableformer.py); only tensor math is in the graphs.

Run inside the project venv: .venv/bin/python onnx-tableformer/export_onnx.py
"""

import argparse
import json
import shutil
from pathlib import Path

import torch
import torch.nn as nn

DEFAULT_OUT_DIR = Path(__file__).parent
ARTIFACTS = (
    Path.home()
    / ".cache/huggingface/hub/models--docling-project--docling-models/snapshots"
)


def find_artifacts_dir(mode: str = "accurate") -> Path:
    snaps = sorted(ARTIFACTS.glob(f"*/model_artifacts/tableformer/{mode}"))
    if not snaps:
        raise FileNotFoundError(f"no cached tableformer/{mode} artifacts under {ARTIFACTS}")
    return snaps[-1]


def load_predictor(mode: str = "accurate"):
    import docling_ibm_models.tableformer.common as c
    from docling_ibm_models.tableformer.data_management.tf_predictor import TFPredictor

    art = find_artifacts_dir(mode)
    config = c.read_config(str(art / "tm_config.json"))
    config["model"]["save_dir"] = str(art)
    return TFPredictor(config, "cpu", 4)


class EncoderWrapper(nn.Module):
    """Encoder04 CNN + tag-transformer encoder, run once per table image."""

    def __init__(self, model):
        super().__init__()
        self._encoder = model._encoder
        self._input_filter = model._tag_transformer._input_filter
        self._tt_encoder = model._tag_transformer._encoder

    def forward(self, img):
        enc_out = self._encoder(img)  # [1, 28, 28, C]
        mem_in = self._input_filter(enc_out.permute(0, 3, 1, 2)).permute(0, 2, 3, 1)
        b, d = mem_in.size(0), mem_in.size(-1)
        enc_inputs = mem_in.view(b, -1, d).permute(1, 0, 2)  # [784, 1, 512]
        # upstream passes an all-False mask, numerically identical to None
        memory = self._tt_encoder(enc_inputs, mask=None)
        return enc_out, memory


class DecoderStepWrapper(nn.Module):
    """One greedy step of the tag decoder, with layer-output cache in/out."""

    def __init__(self, model):
        super().__init__()
        tt = model._tag_transformer
        self._embedding = tt._embedding
        self._pos_pe = tt._positional_encoding.pe  # buffer [max_len, 1, d]
        self._layers = tt._decoder.layers
        self._fc = tt._fc

    def forward(self, tags, memory, cache):
        # tags [seq, 1] int64; cache [n_layers, seq-1, 1, 512]
        emb = self._embedding(tags)
        emb = emb + self._pos_pe[: emb.size(0), :]
        output = emb
        tag_cache = []
        for i, mod in enumerate(self._layers):
            out_i = mod(output, memory)  # [1, 1, 512], last token only
            tag_cache.append(out_i)
            output = torch.cat([cache[i], out_i], dim=0)
        new_cache = torch.cat([cache, torch.stack(tag_cache, dim=0)], dim=1)
        last_h = output[-1, :, :]  # [1, 512]
        logits = self._fc(last_h)  # [1, vocab]
        return logits, last_h, new_cache


class BBoxWrapper(nn.Module):
    """Vectorized BBoxDecoder.inference (the per-cell loop is batched)."""

    def __init__(self, model):
        super().__init__()
        bd = model._bbox_decoder
        self._input_filter = bd._input_filter
        self._attention = bd._attention
        self._init_h = bd._init_h
        self._f_beta = bd._f_beta
        self._class_embed = bd._class_embed
        self._bbox_embed = bd._bbox_embed

    def forward(self, enc_out, tag_H):
        # enc_out [1, 28, 28, C]; tag_H [num_cells, 512]
        x = self._input_filter(enc_out.permute(0, 3, 1, 2)).permute(0, 2, 3, 1)
        d = x.size(3)
        x = x.view(1, -1, d)  # [1, num_pixels, 512]
        h = self._init_h(x.mean(dim=1))  # [1, 512]
        num = tag_H.size(0)
        awe, _ = self._attention(x, tag_H, h.expand(num, -1))
        gate = torch.sigmoid(self._f_beta(h))
        hh = (gate * awe) * h
        return self._class_embed(hh), self._bbox_embed(hh).sigmoid()


def export_tableformer(out_dir: Path, mode: str = "accurate"):
    out_dir.mkdir(parents=True, exist_ok=True)
    predictor = load_predictor("accurate")
    model = predictor._model
    model.eval()

    word_map = predictor._init_data["word_map"]["word_map_tag"]
    (out_dir / "word_map.json").write_text(json.dumps(word_map, indent=2))
    shutil.copy2(find_artifacts_dir(mode) / "tm_config.json", out_dir / "tm_config.json")

    d_model = 512
    n_layers = len(model._tag_transformer._decoder.layers)

    with torch.no_grad():
        img = torch.randn(1, 3, 448, 448)

        enc = EncoderWrapper(model).eval()
        enc_out, memory = enc(img)
        print(f"encoder: enc_out {tuple(enc_out.shape)}, memory {tuple(memory.shape)}")
        torch.onnx.export(
            enc, (img,), str(out_dir / "encoder.onnx"),
            input_names=["image"], output_names=["enc_out", "memory"],
            dynamo=True, optimize=True,
        )

        dec = DecoderStepWrapper(model).eval()
        seq_len = 3
        tags = torch.full((seq_len, 1), int(word_map["<start>"]), dtype=torch.long)
        cache = torch.randn(n_layers, seq_len - 1, 1, d_model)
        logits, last_h, new_cache = dec(tags, memory, cache)
        print(f"decoder: logits {tuple(logits.shape)}, cache {tuple(new_cache.shape)}")
        seq_dim = torch.export.Dim("seq", min=1, max=2048)
        cache_dim = torch.export.Dim("cache_len", min=0, max=2048)
        torch.onnx.export(
            dec, (tags, memory, cache), str(out_dir / "decoder_step.onnx"),
            input_names=["tags", "memory", "cache"],
            output_names=["logits", "last_hidden", "new_cache"],
            dynamic_shapes={
                "tags": {0: seq_dim},
                "memory": None,
                "cache": {1: cache_dim},
            },
            dynamo=True, optimize=True,
        )

        bbox = BBoxWrapper(model).eval()
        tag_H = torch.randn(5, d_model)
        classes, coords = bbox(enc_out, tag_H)
        print(f"bbox: classes {tuple(classes.shape)}, coords {tuple(coords.shape)}")
        cells_dim = torch.export.Dim("num_cells", min=1, max=4096)
        torch.onnx.export(
            bbox, (enc_out, tag_H), str(out_dir / "bbox_decoder.onnx"),
            input_names=["enc_out", "tag_H"], output_names=["classes", "coords"],
            dynamic_shapes={"enc_out": None, "tag_H": {0: cells_dim}},
            dynamo=True, optimize=True,
        )

    for f in ("encoder.onnx", "decoder_step.onnx", "bbox_decoder.onnx"):
        size = (out_dir / f).stat().st_size / 1e6
        print(f"exported {f}: {size:.1f} MB")


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Directory for ONNX graphs, external-data files, word_map.json, and tm_config.json.",
    )
    parser.add_argument("--mode", choices=["accurate", "fast"], default="accurate")
    args = parser.parse_args(argv)
    export_tableformer(args.output_dir, args.mode)


if __name__ == "__main__":
    main()
