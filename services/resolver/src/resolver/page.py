"""Human-readable passport page (en/de) of a resolved Digital Link: the public sections of the DPP; sections
for authorised parties (quality, process, as-built BoM, technical data) are only named."""

from __future__ import annotations

from html import escape
from pathlib import Path

from .links import Link
from .render import pick, scalar, value_html
from .service import Resolution

NAMEPLATE = "https://admin-shell.io/idta/nameplate/3/0/Nameplate"
PCF = "https://admin-shell.io/idta/CarbonFootprint/CarbonFootprint/1/0"
SMT = "https://virtual-factory.example/ids/smt/"
PUBLIC = [  # (semantic id, anchor, en, de)
    (PCF, "sustainability", "Carbon footprint", "CO2-Fußabdruck"),
    (SMT + "ProductMaterialComposition/1/0/Submodel", "materials", "Material composition",
     "Materialzusammensetzung"),
    (SMT + "ProductCircularity/1/0/Submodel", "circularity", "Circularity", "Kreislauffähigkeit"),
    ("https://admin-shell.io/zvei/nameplate/1/0/ContactInformations", "contacts", "Contacts", "Kontakte"),
    (NAMEPLATE, "nameplate", "Nameplate", "Typschild"),
]
RESTRICTED = {
    "0173-1#01-AHX837#002": ("Technical data", "Technische Daten"),
    "https://admin-shell.io/idta/HierarchicalStructures/1/1/Submodel": ("As-built bill of materials",
                                                                        "Stückliste (wie gebaut)"),
    "https://admin-shell.io/idta/ExecutedProcesses/1/0": ("Executed processes", "Durchgeführte Prozesse"),
    SMT + "QualityInspection/1/0/Submodel": ("Quality inspection", "Qualitätsprüfung"),
}
TEXT = {
    "title": ("Digital product passport", "Digitaler Produktpass"),
    "serial": ("Serial number", "Seriennummer"), "type": ("Type", "Typ"),
    "manufactured": ("Manufactured", "Hergestellt"), "status": ("Passport status", "Status des Passes"),
    "pcf": ("Product carbon footprint (A1-A3)", "CO2-Fußabdruck des Produkts (A1-A3)"),
    "documents": ("Documents", "Dokumente"),
    "restricted": ("For authorised parties only", "Nur für berechtigte Akteure"),
    "restricted_note": ("Available through the DPP API / AAS with access rights.",
                        "Über die DPP-API / VWS mit Zugriffsrechten verfügbar."),
    "machine": ("Machine-readable", "Maschinenlesbar"),
    "no_dpp": ("No passport is published for this product yet.",
               "Für dieses Produkt ist noch kein Produktpass veröffentlicht."),
    "model": ("Product type (model-level passport)", "Produkttyp (Pass auf Modellebene)"),
    "phase": ("Life cycle phases", "Lebenszyklusphasen"), "method": ("Method", "Methode"),
    "published": ("Published", "Veröffentlicht"),
    "login": (", login required", ", Anmeldung erforderlich"),
}
STYLE = (Path(__file__).parent / "passport.css").read_text(encoding="utf-8")


def t(key: str, lang: str) -> str:
    en, de = TEXT[key]
    return de if lang == "de" else en


def render(res: Resolution, lang: str, self_url: str) -> str:
    dpp = res.dpp or {}
    plate = dpp.get(NAMEPLATE) or {}
    name = pick(plate.get("ManufacturerProductDesignation"), lang) or res.anchor
    sections = [_facts(res, plate, lang)]
    if not dpp:
        sections.append(f'<div class="card">{t("no_dpp", lang)}</div>')
    sections.append(_documents(res.links, lang))
    for sem, anchor, en, de in PUBLIC:
        if dpp.get(sem):
            body = _pcf(dpp[sem], lang) if sem == PCF else _card(value_html(dpp[sem], lang))
            sections.append(f'<h2 id="{anchor}">{escape(de if lang == "de" else en)}</h2>{body}')
    sections += [_restricted(dpp, lang), _machine(res.links, lang)]
    other = "en" if lang == "de" else "de"
    title = f'{t("title", lang)} - {res.dl.serial or res.dl.gtin}'
    return (f'<!doctype html><html lang="{lang}"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1">'
            f"<title>{escape(title)}</title><style>{STYLE}</style></head><body><header><div class=\"in\">"
            f'<a class="lang" href="{escape(self_url)}?lang={other}">{other.upper()}</a>'
            f'<div class="sub">{escape(t("title", lang))}</div><h1>{escape(name)}</h1>'
            f'<div class="sub"><code>{escape(res.anchor)}</code></div></div></header>'
            f'<main>{"".join(sections)}</main></body></html>')


def _facts(res: Resolution, plate: dict, lang: str) -> str:
    dpp = res.dpp or {}
    facts = [("serial", res.dl.serial or t("model", lang)),
             ("type", plate.get("ManufacturerProductType", "")),
             ("manufactured", plate.get("DateOfManufacture", "")), ("status", dpp.get("dppStatus", ""))]
    cells = "".join(f"<div><b>{t(k, lang)}</b>{escape(str(v))}</div>" for k, v in facts if v)
    pcf = next((p for p in (dpp.get(PCF) or {}).get("ProductCarbonFootprints") or []
                if "A1-A3" in (p.get("LifeCyclePhases") or [])), None)
    if pcf:
        unit = escape(str(pcf.get("ReferenceImpactUnitForCalculation", "")))
        cells += (f'<div><b>{t("pcf", lang)}</b><span class="big">{escape(str(pcf.get("PcfCO2eq")))}</span>'
                  f" kg CO2e / {unit}</div>")
    return f'<div class="card facts">{cells}</div>'


def _pcf(section: dict, lang: str) -> str:
    rows = "".join(
        f"<tr><td>{escape(', '.join(p.get('LifeCyclePhases') or []))}</td>"
        f"<td><b>{escape(str(p.get('PcfCO2eq', '')))}</b> kg CO2e / "
        f"{escape(str(p.get('ReferenceImpactUnitForCalculation', '')))}</td>"
        f"<td>{escape(', '.join(p.get('PcfCalculationMethods') or []))}</td>"
        f"<td>{escape(str(p.get('PublicationDate', ''))[:10])}</td></tr>"
        for p in section.get("ProductCarbonFootprints") or [])
    titles = (t("phase", lang), "CO2e", t("method", lang), t("published", lang))
    head = "".join(f"<th>{h}</th>" for h in titles)
    return _card(f"<table><thead><tr>{head}</tr></thead><tbody>{rows}</tbody></table>", "card scroll")


def _card(html: str, css: str = "card") -> str:
    return f'<div class="{css}">{html}</div>'


def _documents(links: list[Link], lang: str) -> str:
    docs = [k for k in links if k.media_type == "application/pdf"]
    if not docs:
        return ""
    items = "".join(f'<li><a href="{escape(k.href)}">{escape(k.as_target(lang)["title"])}</a></li>'
                    for k in docs)
    return f'<h2 id="documents">{t("documents", lang)}</h2><div class="card"><ul>{items}</ul></div>'


def _restricted(dpp: dict, lang: str) -> str:
    """Sections for authorised parties: restricted ones in the passport, and (secure profile) every section
    listed in contentSpecificationIds that the DPP API withheld from the public role."""
    listed = set(dpp.get("contentSpecificationIds") or [])
    withheld = {sem: (en, de) for sem, _, en, de in PUBLIC if sem in listed and not dpp.get(sem)}
    names = [de if lang == "de" else en for sem, (en, de) in {**RESTRICTED, **withheld}.items()
             if dpp.get(sem) or sem in listed]
    if not names:
        return ""
    return (f'<h2>{t("restricted", lang)}</h2><div class="card"><ul>'
            + "".join(f"<li>{escape(n)}</li>" for n in names)
            + f'</ul><p class="muted">{t("restricted_note", lang)}</p></div>')


def _machine(links: list[Link], lang: str) -> str:
    items = "".join(f'<li><a href="{escape(k.href)}">{scalar(k.as_target(lang)["title"], lang)}</a> '
                    f'<span class="muted">({escape(k.media_type)}{t("login", lang) if k.restricted else ""})'
                    f'</span></li>' for k in links if k.media_type == "application/json")
    return f'<h2>{t("machine", lang)}</h2><div class="card"><ul>{items}</ul></div>' if items else ""
