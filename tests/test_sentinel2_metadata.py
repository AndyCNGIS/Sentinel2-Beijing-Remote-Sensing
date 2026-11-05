import pytest

from src.sentinel2_metadata import parse_l2a_product_metadata


def create_metadata(
    tmp_path,
    baseline="05.00",
    include_offsets=True,
):
    offsets = ""

    if include_offsets:
        offsets = """
        <BOA_ADD_OFFSET_VALUES_LIST>
            <BOA_ADD_OFFSET band_id="1">-1000</BOA_ADD_OFFSET>
            <BOA_ADD_OFFSET band_id="2">-1000</BOA_ADD_OFFSET>
            <BOA_ADD_OFFSET band_id="3">-1000</BOA_ADD_OFFSET>
            <BOA_ADD_OFFSET band_id="7">-1000</BOA_ADD_OFFSET>
        </BOA_ADD_OFFSET_VALUES_LIST>
        """

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
    <Level-2A_User_Product xmlns="urn:sentinel:test">
        <General_Info>
            <Product_Info>
                <PROCESSING_BASELINE>{baseline}</PROCESSING_BASELINE>
            </Product_Info>
            <Product_Image_Characteristics>
                <QUANTIFICATION_VALUE>10000</QUANTIFICATION_VALUE>
                {offsets}
            </Product_Image_Characteristics>
        </General_Info>
    </Level-2A_User_Product>
    """

    path = tmp_path / "MTD_MSIL2A.xml"
    path.write_text(xml, encoding="utf-8")

    return path


def test_parse_pb05_offsets(tmp_path):
    path = create_metadata(tmp_path)

    metadata = parse_l2a_product_metadata(path)

    assert metadata.processing_baseline == "05.00"
    assert metadata.quantification_value == 10000.0
    assert metadata.offset_for("B02") == -1000
    assert metadata.offset_for("B03") == -1000
    assert metadata.offset_for("B04") == -1000
    assert metadata.offset_for("B08") == -1000


def test_pre_pb04_missing_offsets_default_to_zero(tmp_path):
    path = create_metadata(
        tmp_path,
        baseline="03.01",
        include_offsets=False,
    )

    metadata = parse_l2a_product_metadata(path)

    assert metadata.offset_for("B02") == 0
    assert metadata.offset_for("B04") == 0


def test_pb04_or_later_requires_offsets(tmp_path):
    path = create_metadata(
        tmp_path,
        baseline="05.00",
        include_offsets=False,
    )

    with pytest.raises(ValueError, match="requires BOA offsets"):
        parse_l2a_product_metadata(path)


def test_missing_metadata_file_fails(tmp_path):
    path = tmp_path / "missing.xml"

    with pytest.raises(FileNotFoundError):
        parse_l2a_product_metadata(path)
