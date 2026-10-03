class_name BpmnTasks
extends HttpJson
## Operator view of the BPMN engine (Operaton REST): open user tasks, their form fields, completion.
## Polled (the engine has no push channel); the Tasklist web app shows the same tasks.

var base_url := "http://localhost:8092/engine-rest"


## Open user tasks: [{id, name, taskDefinitionKey, processInstanceId, created, businessKey?}].
func list_tasks() -> Array:
	var r := await request("%s/task?sortBy=created&sortOrder=asc" % base_url)
	return r.data if r.ok and r.data is Array else []


## Form fields (generated forms) and current values: {name: {type, value}}.
func form_variables(task_id: String) -> Dictionary:
	var r := await request("%s/task/%s/form-variables" % [base_url, task_id])
	return r.data if r.ok and r.data is Dictionary else {}


## Process variables visible to the task (e.g. `container` of an exchange task): {name: value}.
func variables(task_id: String) -> Dictionary:
	var r := await request("%s/task/%s/variables" % [base_url, task_id])
	var out := {}
	if r.ok and r.data is Dictionary:
		for key: String in r.data:
			out[key] = r.data[key].get("value")
	return out


func complete(task_id: String, values: Dictionary) -> bool:
	var variables_json := {}
	for key: String in values:
		var v: Variant = values[key]
		var type := "Boolean" if v is bool else "Long" if v is int else "String"
		variables_json[key] = {"value": v, "type": type}
	var r := await request("%s/task/%s/complete" % [base_url, task_id], HTTPClient.METHOD_POST,
		{"variables": variables_json})
	return r.ok
