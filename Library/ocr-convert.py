"""Docling conversion implementation, run through ocr's isolated Python."""
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(prog="ocr", description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('-o', '--output', required=True, type=Path)
    parser.add_argument('--no-tables', action='store_true',
                        help='Skip table-structure inference for plain scanned text')
    args = parser.parse_args()
    source = args.source.resolve()
    if not source.is_file():
        parser.error('Source must be a local file')
    if args.output.exists():
        parser.error('Output already exists; choose a new path')
    import onnxruntime
    onnxruntime.disable_telemetry_events()
    from docling.document_converter import DocumentConverter, PdfFormatOption, ImageFormatOption
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions, RapidOcrOptions, LayoutOptions
    from docling.datamodel.layout_model_specs import DOCLING_LAYOUT_HERON
    options = PdfPipelineOptions()
    options.do_ocr = True
    options.do_table_structure = not args.no_tables
    options.ocr_options = RapidOcrOptions(force_full_page_ocr=True)
    options.layout_options = LayoutOptions(model_spec=DOCLING_LAYOUT_HERON.model_copy(
        update={'revision': '8f39ad3c0b4c58e9c2d2c84a38465abf757272d8'}))
    converter = DocumentConverter(format_options={
        InputFormat.PDF: PdfFormatOption(pipeline_options=options),
        InputFormat.IMAGE: ImageFormatOption(pipeline_options=options),
    })
    result = converter.convert(source)
    from docling.datamodel.base_models import ConversionStatus
    if result.status != ConversionStatus.SUCCESS:
        raise SystemExit('Conversion did not fully succeed: ' + str(result.status))
    doc = result.document
    pages = sorted(doc.pages)
    output = '\n\n'.join(f'=====PAGE {n}=====\n\n' + doc.export_to_markdown(page_no=n) for n in pages)
    if not pages or not any(doc.export_to_markdown(page_no=n).strip() for n in pages):
        raise SystemExit('No text recovered; inspect the source visually')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as stream:
        stream.write(output + '\n')
    print(f'{args.output}: {len(pages)} page(s)')


if __name__ == '__main__':
    main()
