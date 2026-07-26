from __future__ import annotations

import copy
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Literal

import numpy as np
from docling_core.types.doc import BoundingBox, DocItemLabel, TableCell
from docling_core.types.doc.page import BoundingRectangle, TextCellUnit

from docling.datamodel.base_models import Page, Table, TableStructurePrediction
from docling.datamodel.document import ConversionResult
from docling.datamodel.pipeline_options import TableStructureOptions
from docling.datamodel.settings import settings
from docling.models.base_table_model import BaseTableStructureModel
from docling.utils.profiling import TimeRecorder
from medical_redactor_onnx.paths import tableformer_dir
from medical_redactor_onnx.tableformer_predictor import OrtTFPredictor


class OnnxTableStructureModel(BaseTableStructureModel):
    """Docling table structure model backed by the app-local ONNX TableFormer."""

    def __init__(
        self,
        enabled: bool,
        artifacts_path: Path | None,
        options: TableStructureOptions,
        accelerator_options,
        enable_remote_services: Literal[False] = False,
    ):
        del artifacts_path, accelerator_options, enable_remote_services
        self.options = options
        self.enabled = enabled
        self.do_cell_matching = options.do_cell_matching
        self.scale = 2.0
        if self.enabled:
            self.tf_predictor = OrtTFPredictor(tableformer_dir(require=True))

    @classmethod
    def get_options_type(cls) -> type[TableStructureOptions]:
        return TableStructureOptions

    def draw_table_and_cells(
        self,
        conv_res: ConversionResult,
        page: Page,
        tbl_list: Iterable[Table],
        show: bool = False,
    ):
        from PIL import ImageDraw

        assert page._backend is not None
        assert page.size is not None

        image = page._backend.get_page_image()
        scale_x = image.width / page.size.width
        scale_y = image.height / page.size.height
        draw = ImageDraw.Draw(image)

        for table_element in tbl_list:
            x0, y0, x1, y1 = table_element.cluster.bbox.as_tuple()
            draw.rectangle(
                [(x0 * scale_x, y0 * scale_y), (x1 * scale_x, y1 * scale_y)],
                outline="red",
            )

        if show:
            image.show()
        else:
            out_path = Path(settings.debug.debug_output_path) / f"debug_{conv_res.input.file.stem}"
            out_path.mkdir(parents=True, exist_ok=True)
            image.save(str(out_path / f"table_struct_page_{page.page_no:05}.png"), format="png")

    def predict_tables(
        self,
        conv_res: ConversionResult,
        pages: Sequence[Page],
    ) -> Sequence[TableStructurePrediction]:
        pages = list(pages)
        predictions: list[TableStructurePrediction] = []

        for page in pages:
            assert page._backend is not None
            if not page._backend.is_valid():
                existing_prediction = page.predictions.tablestructure or TableStructurePrediction()
                page.predictions.tablestructure = existing_prediction
                predictions.append(existing_prediction)
                continue

            with TimeRecorder(conv_res, "table_structure"):
                assert page.predictions.layout is not None
                assert page.size is not None

                table_prediction = TableStructurePrediction()
                page.predictions.tablestructure = table_prediction

                in_tables = [
                    (
                        cluster,
                        [
                            round(cluster.bbox.l) * self.scale,
                            round(cluster.bbox.t) * self.scale,
                            round(cluster.bbox.r) * self.scale,
                            round(cluster.bbox.b) * self.scale,
                        ],
                    )
                    for cluster in page.predictions.layout.clusters
                    if cluster.label in [DocItemLabel.TABLE, DocItemLabel.DOCUMENT_INDEX]
                ]
                if not in_tables:
                    predictions.append(table_prediction)
                    continue

                page_input = {
                    "width": page.size.width * self.scale,
                    "height": page.size.height * self.scale,
                    "image": np.asarray(page.get_image(scale=self.scale)),
                }

                for table_cluster, table_box in in_tables:
                    segmented_page = page._backend.get_segmented_page()
                    if segmented_page is not None:
                        text_cells = segmented_page.get_cells_in_bbox(
                            cell_unit=TextCellUnit.WORD,
                            bbox=table_cluster.bbox,
                        )
                        if len(text_cells) == 0:
                            text_cells = table_cluster.cells
                    else:
                        text_cells = table_cluster.cells

                    tokens = []
                    for cell in text_cells:
                        if len(cell.text.strip()) > 0:
                            new_cell = copy.deepcopy(cell)
                            new_cell.rect = BoundingRectangle.from_bounding_box(
                                new_cell.rect.to_bounding_box().scaled(scale=self.scale)
                            )
                            tokens.append(
                                {
                                    "id": new_cell.index,
                                    "text": new_cell.text,
                                    "bbox": new_cell.rect.to_bounding_box().model_dump(),
                                }
                            )
                    page_input["tokens"] = tokens

                    tf_output = self.tf_predictor.multi_table_predict(
                        page_input,
                        [table_box],
                        do_matching=self.do_cell_matching,
                    )
                    table_out = tf_output[0]
                    table_cells = []
                    for element in table_out["tf_responses"]:
                        if not self.do_cell_matching:
                            bbox = BoundingBox.model_validate(element["bbox"]).scaled(
                                1 / self.scale
                            )
                            text_piece = page._backend.get_text_in_rect(bbox)
                            element["bbox"]["token"] = text_piece

                        table_cell = TableCell.model_validate(element)
                        if table_cell.bbox is not None:
                            table_cell.bbox = table_cell.bbox.scaled(1 / self.scale)
                        table_cells.append(table_cell)

                    num_rows = table_out["predict_details"].get("num_rows", 0)
                    num_cols = table_out["predict_details"].get("num_cols", 0)
                    otsl_seq = (
                        table_out["predict_details"]
                        .get("prediction", {})
                        .get("rs_seq", [])
                    )

                    table = Table(
                        otsl_seq=otsl_seq,
                        table_cells=table_cells,
                        num_rows=num_rows,
                        num_cols=num_cols,
                        id=table_cluster.id,
                        page_no=page.page_no,
                        cluster=table_cluster,
                        label=table_cluster.label,
                    )

                    table_prediction.table_map[table_cluster.id] = table

                if settings.debug.visualize_tables:
                    self.draw_table_and_cells(
                        conv_res,
                        page,
                        page.predictions.tablestructure.table_map.values(),
                    )

                predictions.append(table_prediction)

        return predictions

