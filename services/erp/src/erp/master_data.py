"""Material master of the ERP, derived from the asset data the AAS is built from (aas/data): the finished good
PC3280 (PC3280_TYPE) and its purchased components with article number (customerPartId), bill-of-material
quantity, supplier (Nameplate.ManufacturerName of the component type) and the component type's AAS tag."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from provisioner.build import DATA_ROOT, load_assets

PRODUCT = "PC3280"
PRODUCT_TAG = "PC3280_TYPE"


@dataclass(frozen=True)
class Material:
    id: str             # article number (MaterialDefinitionID)
    description: str
    kind: str           # "FinishedGood" | "Component"
    supplier: str = ""
    bom_node: str = ""  # node of the product type BoM (key in part_released.lots)
    bom_quantity: float = 0.0
    asset_tag: str = ""  # AAS tag of the type (CMP_..., PC3280_TYPE)

    def to_dict(self) -> dict:
        return asdict(self)


def load_materials(data_dir=DATA_ROOT) -> dict[str, Material]:
    specs = {s["tag"]: s for s in load_assets(data_dir)}
    product = specs[PRODUCT_TAG]
    name = product["displayName"]["en"].removesuffix(" (type)")
    materials = {PRODUCT: Material(PRODUCT, name, "FinishedGood", asset_tag=PRODUCT_TAG)}
    articles = _articles(product)
    for node in _bom_nodes(product):
        tag = node["globalAssetId"].removeprefix("${asset:").rstrip("}")
        component = specs[tag]
        article = component.get("specificAssetIds", {}).get("customerPartId") or articles.get(tag, tag)
        nameplate = next(s["values"] for s in component["submodels"] if s["template"].startswith("Nameplate"))
        name = component["displayName"]["en"].removesuffix(" (component type)")
        materials[article] = Material(article, name, "Component", nameplate["ManufacturerName"]["en"],
                                      node["_idShort"],
                                      float(node["statements"]["BulkCount"]), tag)
    return materials


def _bom_nodes(product: dict) -> list[dict]:
    bom = next(s["values"] for s in product["submodels"]
               if s["template"].startswith("HierarchicalStructures"))
    return bom["EntryNode"]["statements"]["Node"]


def _articles(node, found: dict | None = None) -> dict[str, str]:
    """{component tag: customerPartId} from every entity of the product type that carries both."""
    found = {} if found is None else found
    if isinstance(node, dict):
        ids = node.get("specificAssetIds")
        if isinstance(ids, list) and str(node.get("globalAssetId", "")).startswith("${asset:"):
            for entry in ids:
                if entry.get("name") == "customerPartId":
                    found[node["globalAssetId"].removeprefix("${asset:").rstrip("}")] = entry["value"]
        for value in node.values():
            _articles(value, found)
    elif isinstance(node, list):
        for value in node:
            _articles(value, found)
    return found
