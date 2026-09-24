from __future__ import annotations

import sys
import types
from dataclasses import dataclass


class _DisabledChartExtractionModel:
    elements_batch_size = 1

    def __init__(self, *, enabled: bool, **_kwargs):
        if enabled:
            raise RuntimeError(
                "Docling chart extraction is disabled in the torch-free runtime"
            )
        self.enabled = False

    def is_processable(self, doc, element) -> bool:
        return False

    def prepare_element(self, conv_res, element):
        return None

    def __call__(self, doc, element_batch):
        for element in element_batch:
            yield element.item


def install_docling_torch_free_shims() -> None:
    _install_cpu_accelerator_shim()
    _install_chart_extraction_shim()
    _install_docling_ibm_reading_order_shims()


def _install_cpu_accelerator_shim() -> None:
    from docling.utils import accelerator_utils

    def decide_device(_accelerator_device, supported_devices=None) -> str:
        return "cpu"

    accelerator_utils.decide_device = decide_device
    for module_name in (
        "docling.models.inference_engines.object_detection.onnxruntime_engine",
        "docling.models.stages.ocr.rapid_ocr_model",
    ):
        module = sys.modules.get(module_name)
        if module is not None:
            module.decide_device = decide_device


def _install_chart_extraction_shim() -> None:
    module_name = "docling.models.stages.chart_extraction.granite_vision"
    if module_name in sys.modules:
        return
    module = types.ModuleType(module_name)
    module.ChartExtractionModelGraniteVision = _DisabledChartExtractionModel
    module.ChartExtractionModelGraniteVisionV4 = _DisabledChartExtractionModel
    sys.modules[module_name] = module


def _ensure_module(name: str) -> types.ModuleType:
    if name in sys.modules:
        return sys.modules[name]
    module = types.ModuleType(name)
    sys.modules[name] = module
    return module


def _install_docling_ibm_reading_order_shims() -> None:
    _ensure_module("docling_ibm_models")
    _ensure_module("docling_ibm_models.list_item_normalizer")
    list_module = _ensure_module(
        "docling_ibm_models.list_item_normalizer.list_marker_processor"
    )

    class ListItemMarkerProcessor:
        def process_list_item(self, _item):
            return None

    list_module.ListItemMarkerProcessor = ListItemMarkerProcessor

    _ensure_module("docling_ibm_models.reading_order")
    reading_module = _ensure_module("docling_ibm_models.reading_order.reading_order_rb")

    @dataclass
    class PageElement:
        cid: int
        ref: object
        text: str
        page_no: int
        page_size: object
        label: object
        l: float
        r: float
        b: float
        t: float
        coord_origin: object

    class ReadingOrderPredictor:
        def predict_reading_order(self, page_elements):
            return sorted(page_elements, key=lambda el: (el.page_no, el.t, el.l, el.cid))

        def predict_to_captions(self, sorted_elements):
            return {}

        def predict_to_footnotes(self, sorted_elements):
            return {}

        def predict_merges(self, sorted_elements):
            return {}

    reading_module.PageElement = PageElement
    reading_module.ReadingOrderPredictor = ReadingOrderPredictor


def register_onnx_tableformer() -> None:
    from docling.datamodel.pipeline_options import TableStructureOptions
    from docling.models.factories import get_table_structure_factory
    from docling.models.plugins import defaults

    from medical_redactor_onnx.docling_table_model import OnnxTableStructureModel

    def table_structure_engines():
        return {"table_structure_engines": [OnnxTableStructureModel]}

    defaults.table_structure_engines = table_structure_engines
    get_table_structure_factory.cache_clear()
    factory = get_table_structure_factory()
    factory.classes[TableStructureOptions] = OnnxTableStructureModel
