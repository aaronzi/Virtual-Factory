"""Rebuilds every Blender asset (run inside Blender via the MCP):
    exec(open("<repo>/blender/scripts/build_all.py").read())
Order matters only for review renders; each script resets the scene.
"""

from pathlib import Path

SCRIPTS = ["build_cylinder.py", "build_conveyor.py", "build_light_barrier.py", "build_qa_station.py", "build_klt.py",
           "build_assembly_cell.py", "build_ur5e.py", "build_hall.py", "build_props.py",
           "build_stack_light.py"]
_dir = Path("/Users/zielstor/Documents/GitProjects/Virtual-Factory/blender/scripts")
summary = {}
for _script in SCRIPTS:
    _ns = {}
    exec(open(_dir / _script).read(), _ns)
    summary[_script] = _ns.get("result", {}).get("triangles")
result = summary
