class_name Fmi3DoStepResult
extends RefCounted
## Out-parameters of fmi3DoStep.

var status := Fmi3.Status.OK
var event_handling_needed := false
var terminate_simulation := false
var early_return := false
var last_successful_time := 0.0
