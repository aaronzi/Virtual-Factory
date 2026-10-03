class_name AasClient
extends HttpJson
## Read access to the AAS infrastructure (AAS Part 2 HTTP API) for the in-world AAS inspector (ADR-0023):
## asset id -> Discovery (/lookup/shells) -> AAS id -> AAS Registry (/shell-descriptors) -> endpoint (href)
## -> shell / submodels. `registries` may list several environments (federation); hrefs are cached and
## dropped on BaSyx change events (`forget`). Ids that no registry knows fall back to `base_url` (repository
## of the own environment, documented fallback); concept descriptions are always read from `base_url`.

var base_url := "http://localhost:8091"
var id_base := "https://virtual-factory.example/ids"
## [{name, discovery, aas_registry, submodel_registry}]; empty = all three at `base_url`.
var registries: Array = []
var _units := {}  # concept id -> unit
var _shell_hrefs := {}  # AAS id -> shell endpoint
var _submodel_hrefs := {}  # submodel id -> submodel endpoint


## Asset id by convention for devices (`<id_base>/asset/<tag>`, printed on their type plates); workpieces and
## the product type are identified by their GS1 Digital Link instead.
func asset_id(tag: String) -> String:
	return "%s/asset/%s" % [id_base, tag]


## AAS tag of a workpiece serial (PC3280-2026-000123 -> WP_PC3280_2026_000123).
static func workpiece_tag(serial: String) -> String:
	return "WP_" + serial.replace("-", "_")


## Discovery: AAS ids of the asset (globalAssetId), over all environments; [] if unknown.
func lookup(global_asset_id: String) -> Array:
	var link := b64url(JSON.stringify({"name": "globalAssetId", "value": global_asset_id}))
	for env: Dictionary in _environments():
		var r := await request("%s/lookup/shells?assetIds=%s" % [env.discovery, link])
		if r.ok and r.data is Dictionary and not r.data.get("result", []).is_empty():
			return r.data.result
	return []


## Registry: shell descriptor of an AAS ({} if not registered); caches the shell and submodel endpoints.
func describe(aas_id: String) -> Dictionary:
	for env: Dictionary in _environments():
		var r := await request("%s/shell-descriptors/%s" % [env.aas_registry, b64url(aas_id)])
		if r.ok and r.data is Dictionary:
			remember(r.data)
			return r.data
	return {}


## Caches the endpoints of a shell descriptor.
func remember(descriptor: Dictionary) -> void:
	var href := endpoint_href(descriptor, "AAS-")
	if href != "":
		_shell_hrefs[descriptor.get("id", "")] = href
	for sm: Dictionary in descriptor.get("submodelDescriptors", []):
		var sm_href := endpoint_href(sm, "SUBMODEL-")
		if sm_href != "":
			_submodel_hrefs[sm.get("id", "")] = sm_href


## Drops cached endpoints (BaSyx shell/submodel change events).
func forget(id: String) -> void:
	_shell_hrefs.erase(id)
	_submodel_hrefs.erase(id)


static func endpoint_href(descriptor: Dictionary, interface_prefix: String) -> String:
	for endpoint: Dictionary in descriptor.get("endpoints", []):
		if String(endpoint.get("interface", "")).begins_with(interface_prefix):
			return String(endpoint.get("protocolInformation", {}).get("href", ""))
	return ""


func get_shell(id: String) -> Dictionary:
	var r := await request(await shell_href(id))
	return r.data if r.ok and r.data is Dictionary else {}


func get_submodel(id: String) -> Dictionary:
	var r := await request(await submodel_href(id))
	return r.data if r.ok and r.data is Dictionary else {}


## Endpoint of a shell: registry descriptor, else the own repository.
func shell_href(id: String) -> String:
	if not _shell_hrefs.has(id):
		await describe(id)
	return _shell_hrefs.get(id, "%s/shells/%s" % [base_url, b64url(id)])


## Endpoint of a submodel: from its shell's descriptor or the submodel registry, else the own repository.
func submodel_href(id: String) -> String:
	if not _submodel_hrefs.has(id):
		for env: Dictionary in _environments():
			var r := await request("%s/submodel-descriptors/%s" % [env.submodel_registry, b64url(id)])
			if r.ok and r.data is Dictionary and endpoint_href(r.data, "SUBMODEL-") != "":
				_submodel_hrefs[id] = endpoint_href(r.data, "SUBMODEL-")
				break
	return _submodel_hrefs.get(id, "%s/submodels/%s" % [base_url, b64url(id)])


## Unit of a concept description (IEC 61360), "" if none; cached because many elements share concepts.
func get_unit(concept_id: String) -> String:
	return (await get_units([concept_id]))[concept_id]


## Several submodels in parallel (missing ones are omitted); endpoints from the shell's descriptor.
func get_submodels(ids: Array) -> Array:
	var urls := []
	for id: String in ids:
		urls.append(await submodel_href(id))
	var out := []
	for r: Dictionary in await request_many(urls):
		if r.ok and r.data is Dictionary:
			out.append(r.data)
	return out


## Units of several concept descriptions in parallel (cached): {concept id: unit}.
func get_units(concept_ids: Array) -> Dictionary:
	var missing := concept_ids.filter(func(id: String) -> bool: return not _units.has(id))
	var urls := missing.map(func(id: String) -> String:
		return "%s/concept-descriptions/%s" % [base_url, b64url(id)])
	var results := await request_many(urls)
	for i in missing.size():
		var unit := ""
		if results[i].ok and results[i].data is Dictionary:
			for spec: Dictionary in results[i].data.get("embeddedDataSpecifications", []):
				unit = String(spec.get("dataSpecificationContent", {}).get("unit", ""))
		_units[missing[i]] = unit
	var out := {}
	for id: String in concept_ids:
		out[id] = _units[id]
	return out


## The shell's default thumbnail as an Image, or null.
func get_thumbnail(id: String) -> Image:
	var r := await request("%s/asset-information/thumbnail" % await shell_href(id))
	if not r.ok or r.body.is_empty():
		return null
	var image := Image.new()
	var err := image.load_png_from_buffer(r.body)
	if err != OK:
		err = image.load_jpg_from_buffer(r.body)
	return image if err == OK else null


## Synchronous operation invocation; inputs {idShort: value} of Property variables, returns {idShort: value}.
func invoke(submodel_id: String, path: String, inputs: Dictionary) -> Dictionary:
	var args := []
	for key: String in inputs:
		var v: Variant = inputs[key]
		var value_type := "xs:boolean" if v is bool else "xs:int" if v is int else "xs:string"
		args.append({"value": {"modelType": "Property", "idShort": key, "valueType": value_type,
			"value": str(v).to_lower() if v is bool else str(v)}})
	var url := "%s/submodel-elements/%s/invoke" % [await submodel_href(submodel_id), path]
	var r := await request(url, HTTPClient.METHOD_POST, {"inputArguments": args,
		"clientTimeoutDuration": "PT15S"})
	var out := {"ok": r.ok}
	if r.ok and r.data is Dictionary:
		for arg: Dictionary in r.data.get("outputArguments", []):
			out[arg.value.idShort] = arg.value.get("value")
	return out


func _environments() -> Array:
	if not registries.is_empty():
		return registries
	return [{"name": "vf", "discovery": base_url, "aas_registry": base_url, "submodel_registry": base_url}]
