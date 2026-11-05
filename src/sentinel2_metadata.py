"""Read Sentinel-2 L2A radiometric metadata from product XML."""

from dataclasses import dataclass
from pathlib import Path
import xml.etree.ElementTree as ET


BAND_ID_BY_NAME = {
    "B01": 0,
    "B02": 1,
    "B03": 2,
    "B04": 3,
    "B05": 4,
    "B06": 5,
    "B07": 6,
    "B08": 7,
    "B8A": 8,
    "B09": 9,
    "B10": 10,
    "B11": 11,
    "B12": 12,
}

REQUIRED_BANDS = ("B02", "B03", "B04", "B08")


def local_name(tag: str) -> str:
    """Remove an XML namespace from a tag."""
    return tag.rsplit("}", 1)[-1]


def baseline_tuple(value: str) -> tuple:
    """Convert a processing baseline such as 05.00 to (5, 0)."""
    try:
        parts = value.strip().split(".")
        return tuple(int(x) for x in parts)
    except (ValueError, AttributeError) as exc:
        raise ValueError(
            f"Invalid Sentinel-2 processing baseline: {value!r}"
        ) from exc


@dataclass(frozen=True)
class L2AMetadata:
    processing_baseline: str
    quantification_value: float
    band_offsets: dict

    def offset_for(self, band: str) -> float:
        band = band.upper()

        if band not in self.band_offsets:
            raise KeyError(f"Unsupported Sentinel-2 band: {band}")

        return self.band_offsets[band]


def parse_l2a_product_metadata(xml_path) -> L2AMetadata:
    """Parse quantification value and BOA offsets from L2A XML.

    Supports the common product metadata element names
    BOA_QUANTIFICATION_VALUE and QUANTIFICATION_VALUE.

    PB >= 04.00 requires an explicit BOA_ADD_OFFSET for each
    band used by this project. For older baselines, missing
    offsets are interpreted as zero.
    """
    path = Path(xml_path)

    if not path.is_file():
        raise FileNotFoundError(
            f"Sentinel-2 product metadata not found: {path}"
        )

    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise ValueError(
            f"Invalid Sentinel-2 XML metadata: {path}"
        ) from exc

    elements = list(root.iter())

    def find_values(names):
        result = []

        for element in elements:
            if local_name(element.tag) in names:
                if element.text and element.text.strip():
                    result.append(element.text.strip())

        return result

    baseline_values = find_values({"PROCESSING_BASELINE"})

    if not baseline_values:
        raise ValueError(
            "PROCESSING_BASELINE is missing from product metadata"
        )

    processing_baseline = baseline_values[0]
    pb = baseline_tuple(processing_baseline)

    if len(pb) < 2:
        pb = pb + (0,)

    # Prefer the explicit BOA quantification field when present.
    quant_values = find_values({"BOA_QUANTIFICATION_VALUE"})

    if not quant_values:
        quant_values = find_values({"QUANTIFICATION_VALUE"})

    if not quant_values:
        raise ValueError(
            "BOA reflectance quantification value is missing"
        )

    try:
        quantification_value = float(quant_values[0])
    except ValueError as exc:
        raise ValueError(
            f"Invalid quantification value: {quant_values[0]!r}"
        ) from exc

    if quantification_value <= 0:
        raise ValueError(
            "BOA quantification value must be greater than zero"
        )

    offsets_by_id = {}

    for element in elements:
        if local_name(element.tag) != "BOA_ADD_OFFSET":
            continue

        band_id = element.attrib.get("band_id")

        if band_id is None or not element.text:
            raise ValueError(
                "BOA_ADD_OFFSET has a missing band_id or value"
            )

        try:
            band_id = int(band_id)
            offset = float(element.text.strip())
        except ValueError as exc:
            raise ValueError(
                "Invalid BOA_ADD_OFFSET entry"
            ) from exc

        if band_id in offsets_by_id:
            if offsets_by_id[band_id] != offset:
                raise ValueError(
                    f"Conflicting offsets for band_id={band_id}"
                )

        offsets_by_id[band_id] = offset

    missing_bands = [
        band
        for band in REQUIRED_BANDS
        if BAND_ID_BY_NAME[band] not in offsets_by_id
    ]

    # PB 04.00 introduced band-dependent BOA radiometric offsets.
    if pb >= (4, 0):
        if missing_bands:
            raise ValueError(
                "Processing baseline "
                f"{processing_baseline} requires BOA offsets, "
                f"but metadata is missing offsets for: "
                f"{', '.join(missing_bands)}"
            )

    band_offsets = {}

    for band in REQUIRED_BANDS:
        band_id = BAND_ID_BY_NAME[band]

        if band_id in offsets_by_id:
            band_offsets[band] = offsets_by_id[band_id]
        else:
            band_offsets[band] = 0.0

    return L2AMetadata(
        processing_baseline=processing_baseline,
        quantification_value=quantification_value,
        band_offsets=band_offsets,
    )
