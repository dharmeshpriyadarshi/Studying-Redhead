
"""Offline regression tests for scientific MOLA label auditing."""

import hashlib
import json

import pytest
import xml.etree.ElementTree as ET

from src.pipeline import pds_label_audit as audit


@pytest.fixture
def sample_xml():
    pds = audit.archive.PDS_NAMESPACE

    return f'''<?xml version="1.0" encoding="UTF-8"?>
<Product_Observational xmlns="{pds}"
                       xmlns:cart="http://pds.nasa.gov/pds4/cart/v1">
  <Identification_Area>
    <logical_identifier>{audit.archive.EXPECTED_LID}</logical_identifier>
    <version_id>1.1</version_id>
  </Identification_Area>

  <Observation_Area>
    <Discipline_Area>
      <cart:Cartography>
        <cart:map_projection_name>Equirectangular</cart:map_projection_name>
        <cart:latitude_type>Planetocentric</cart:latitude_type>
        <cart:longitude_direction>Positive East</cart:longitude_direction>
        <cart:west_bounding_coordinate>0</cart:west_bounding_coordinate>
        <cart:east_bounding_coordinate>90</cart:east_bounding_coordinate>
        <cart:south_bounding_coordinate>0</cart:south_bounding_coordinate>
        <cart:north_bounding_coordinate>44</cart:north_bounding_coordinate>
      </cart:Cartography>
    </Discipline_Area>
  </Observation_Area>

  <File_Area_Observational>
    <File>
      <file_name>megt44n000hb.img</file_name>
    </File>

    <Array_2D_Image>
      <local_identifier>gridded_image</local_identifier>
      <offset unit="byte">0</offset>
      <axes>2</axes>
      <axis_index_order>Last Index Fastest</axis_index_order>

      <Element_Array>
        <data_type>SignedMSB2</data_type>
        <unit>meter</unit>
        <scaling_factor>1</scaling_factor>
        <value_offset>0</value_offset>
      </Element_Array>

      <Axis_Array>
        <axis_name>Line</axis_name>
        <elements>5632</elements>
        <sequence_number>1</sequence_number>
      </Axis_Array>

      <Axis_Array>
        <axis_name>Sample</axis_name>
        <elements>11520</elements>
        <sequence_number>2</sequence_number>
      </Axis_Array>

      <Special_Constants>
        <missing_constant>-32768</missing_constant>
      </Special_Constants>
    </Array_2D_Image>
  </File_Area_Observational>

  <File_Area_Observational_Supplemental>
    <File><file_name>megt44n000hb.lbl</file_name></File>
  </File_Area_Observational_Supplemental>

  <File_Area_Observational_Supplemental>
    <File><file_name>megt44n000hb.hdr</file_name></File>
  </File_Area_Observational_Supplemental>
</Product_Observational>
'''.encode("utf-8")


def analyze(raw):
    digest = hashlib.sha256(raw).hexdigest()
    return audit.analyze_pds_label(
        raw, expected_sha256=digest
    )


def test_valid_scientific_metadata(sample_xml):
    report = analyze(sample_xml)

    assert report["identity"]["identity_verified"] is True
    assert report["raster"]["lines"] == 5632
    assert report["raster"]["samples"] == 11520
    assert report["raster"]["data_type"] == "SignedMSB2"
    assert report["raster"]["byte_order"] == "big"
    assert report["raster"]["expected_array_bytes"] == 129761280
    assert report["raster"]["minimum_file_bytes"] == 129761280
    assert report["raster"]["unit"] == "meter"
    assert report["review"]["scientific_processing_approved"] is False


def test_cartography_extracted(sample_xml):
    cart = analyze(sample_xml)["cartography"]

    assert cart["map_projection_name"] == "Equirectangular"
    assert cart["latitude_type"] == "Planetocentric"
    assert cart["longitude_direction"] == "Positive East"
    assert cart["metadata_complete"] is True
    assert cart["coordinates_transformed"] is False


def test_supplemental_files_not_treated_as_raster(sample_xml):
    report = analyze(sample_xml)

    assert report["raster"]["file_name"] == "megt44n000hb.img"
    assert report["supplemental_files"] == [
        "megt44n000hb.hdr",
        "megt44n000hb.lbl",
    ]


def test_special_constants_preserved(sample_xml):
    result = analyze(sample_xml)

    assert result["raster"]["special_constants_as_labelled"] == {
        "missing_constant": "-32768",
    }



def test_missing_special_constants_remains_unknown(sample_xml):
    root = ET.fromstring(sample_xml)

    namespace = audit.archive.PDS_NAMESPACE

    array = root.find(
        f".//{{{namespace}}}Array_2D_Image"
    )

    assert array is not None

    special = array.find(
        f"{{{namespace}}}Special_Constants"
    )

    assert special is not None

    array.remove(special)

    modified_xml = ET.tostring(
        root,
        encoding="utf-8",
    )

    report = analyze(modified_xml)

    assert report["raster"][
        "special_constants_as_labelled"
    ] == {}



def test_absent_scaling_fields_not_invented(sample_xml):
    raw = sample_xml.replace(
        b"<scaling_factor>1</scaling_factor>", b""
    ).replace(
        b"<value_offset>0</value_offset>", b""
    )

    values = analyze(raw)["raster"]

    assert values["scaling_factor_as_labelled"] is None
    assert values["value_offset_as_labelled"] is None


@pytest.mark.parametrize("old,new", [
    (b"<axes>2</axes>", b"<axes>3</axes>"),
    (
        b"<axis_index_order>Last Index Fastest</axis_index_order>",
        b"<axis_index_order>First Index Fastest</axis_index_order>",
    ),
    (
        b"<data_type>SignedMSB2</data_type>",
        b"<data_type>UnsupportedType</data_type>",
    ),
    (
        b"<file_name>megt44n000hb.img</file_name>",
        b"<file_name>wrong.img</file_name>",
    ),
    (
        b"<elements>5632</elements>",
        b"<elements>0</elements>",
    ),
])
def test_invalid_array_metadata_rejected(sample_xml, old, new):
    with pytest.raises(audit.PDSLabelAuditError):
        analyze(sample_xml.replace(old, new))


def test_wrong_product_identifier_rejected(sample_xml):
    with pytest.raises(
        audit.PDSLabelAuditError,
        match="identity/integrity",
    ):
        analyze(
            sample_xml.replace(
                audit.archive.EXPECTED_LID.encode(),
                b"urn:nasa:pds:wrong:product",
            )
        )


def test_checksum_mismatch_rejected(sample_xml):
    with pytest.raises(
        audit.PDSLabelAuditError,
        match="identity/integrity",
    ):
        audit.analyze_pds_label(
            sample_xml,
            expected_sha256="0" * 64,
        )



def test_geographical_bounds_rejected(sample_xml):
    root = ET.fromstring(sample_xml)

    cart_namespace = (
        "http://pds.nasa.gov/pds4/cart/v1"
    )

    east = root.find(
        f".//{{{cart_namespace}}}east_bounding_coordinate"
    )

    assert east is not None

    east.text = "-10"

    modified_xml = ET.tostring(
        root,
        encoding="utf-8",
    )

    with pytest.raises(
        audit.PDSLabelAuditError,
        match="geographical bounds",
    ):
        analyze(modified_xml)



def test_duplicate_primary_array_rejected(sample_xml):
    start = sample_xml.index(b"<Array_2D_Image>")
    end = sample_xml.index(b"</Array_2D_Image>") + len(
        b"</Array_2D_Image>"
    )
    array = sample_xml[start:end]

    raw = sample_xml.replace(
        b"</File_Area_Observational>",
        array + b"</File_Area_Observational>",
    )

    with pytest.raises(
        audit.PDSLabelAuditError,
        match="exactly one primary 2D",
    ):
        analyze(raw)


def test_declared_file_too_small_rejected(sample_xml):
    raw = sample_xml.replace(
        b"<file_name>megt44n000hb.img</file_name>",
        b"<file_name>megt44n000hb.img</file_name>"
        b"<file_size>100</file_size>",
    )

    with pytest.raises(
        audit.PDSLabelAuditError,
        match="smaller",
    ):
        analyze(raw)


def test_missing_cartography_is_not_approved(sample_xml):
    start = sample_xml.index(b"<cart:Cartography>")
    end = sample_xml.index(b"</cart:Cartography>") + len(
        b"</cart:Cartography>"
    )

    raw = sample_xml[:start] + sample_xml[end:]
    report = analyze(raw)

    assert report["cartography"]["metadata_complete"] is False
    assert report["review"]["scientific_processing_approved"] is False


def test_local_audit_is_reproducible(
    sample_xml, tmp_path, monkeypatch
):
    label = tmp_path / "megt44n000hb.xml"
    report = tmp_path / "audit.json"

    label.write_bytes(sample_xml)

    monkeypatch.setattr(
        audit.archive,
        "PINNED_SHA256",
        hashlib.sha256(sample_xml).hexdigest(),
    )

    first = audit.audit_local_label(label, report)
    previous_bytes = report.read_bytes()

    second = audit.audit_local_label(label, report)

    assert first == second
    assert report.read_bytes() == previous_bytes
    assert json.loads(previous_bytes) == first


def test_missing_local_label_rejected(tmp_path):
    with pytest.raises(
        audit.PDSLabelAuditError,
        match="Could not read",
    ):
        audit.audit_local_label(
            tmp_path / "missing.xml",
            tmp_path / "report.json",
        )


def test_oversized_local_label_rejected(tmp_path):
    label = tmp_path / "huge.xml"
    label.write_bytes(
        b"x" * (audit.archive.MAX_LABEL_BYTES + 1)
    )

    with pytest.raises(
        audit.PDSLabelAuditError,
        match="size limit",
    ):
        audit.audit_local_label(
            label,
            tmp_path / "report.json",
        )
