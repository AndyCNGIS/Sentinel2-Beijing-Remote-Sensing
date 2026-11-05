from pathlib import Path
from getpass import getpass
import requests
import xml.etree.ElementTree as ET

from pystac_client import Client


TARGET_ID = (
    "S2B_MSIL2A_20210929T030539_N0500_R075_"
    "T50TMK_20230125T172544"
)


def main():
    print("[1/4] Connecting to Copernicus STAC...")

    catalog = Client.open(
        "https://stac.dataspace.copernicus.eu/v1"
    )

    search = catalog.search(
        collections=["sentinel-2-l2a"],
        bbox=[116.25, 39.80, 116.50, 40.05],
        datetime="2021-06-01/2021-09-30",
        query={"eo:cloud_cover": {"lt": 20}},
        max_items=30,
    )

    item = next(
        (x for x in search.items() if x.id == TARGET_ID),
        None,
    )

    if item is None:
        raise RuntimeError("目标产品没有找到")

    asset = item.assets.get("product_metadata")

    if asset is None:
        raise RuntimeError("产品没有 product_metadata")

    metadata_url = (
        asset.extra_fields["alternate"]["https"]["href"]
    )

    print("[2/4] Please enter Copernicus credentials.")

    username = input("Copernicus账号：").strip()
    password = getpass("Copernicus密码：")

    token_url = (
        "https://identity.dataspace.copernicus.eu/"
        "auth/realms/CDSE/protocol/openid-connect/token"
    )

    response = requests.post(
        token_url,
        data={
            "client_id": "cdse-public",
            "username": username,
            "password": password,
            "grant_type": "password",
        },
        timeout=30,
    )

    response.raise_for_status()
    token = response.json()["access_token"]

    print("[3/4] Downloading product XML...")

    response = requests.get(
        metadata_url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=60,
    )

    response.raise_for_status()

    xml_bytes = response.content

    root = ET.fromstring(xml_bytes)

    output_dir = Path("data/raw")
    output_dir.mkdir(parents=True, exist_ok=True)

    xml_path = output_dir / f"{TARGET_ID}_MTD_MSIL2A.xml"
    xml_path.write_bytes(xml_bytes)

    print("XML saved:", xml_path)
    print("XML size:", len(xml_bytes), "bytes")

    print("[4/4] Extracting radiometric metadata...")

    def local_name(tag):
        return tag.split("}")[-1]

    for element in root.iter():
        name = local_name(element.tag)

        if name in (
            "PROCESSING_BASELINE",
            "BOA_QUANTIFICATION_VALUE",
            "QUANTIFICATION_VALUE",
            "BOA_ADD_OFFSET",
        ):
            print(name, "=", element.text)

        elif name == "BOA_ADD_OFFSET_VALUES_LIST":
            print("BOA_ADD_OFFSET_VALUES_LIST:")

            for child in element:
                print(" ", child.attrib, "=", child.text)

    print("SUCCESS: real product metadata inspected.")


if __name__ == "__main__":
    main()
