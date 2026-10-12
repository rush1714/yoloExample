import subprocess
import json

cmd = """
SELECT t.id, t.data, tc.result
FROM task t
JOIN task_completion tc ON tc.task_id = t.id
WHERE t.project_id = 29;
"""
res = subprocess.check_output(["psql", "-U", "guobiao", "-d", "labelstudio", "-t", "-A", "-c", cmd]).decode()
lines = [l for l in res.split('\n') if l.strip()]
print(f"Total annotations in project 29: {len(lines)}")

# Let's inspect other projects as well, e.g. project 28, 27, 25, 22, 21
cmd2 = """
SELECT p.id, p.title, count(tc.id) as completion_count, count(DISTINCT t.id) as annotated_tasks
FROM project p
JOIN task t ON t.project_id = p.id
JOIN task_completion tc ON tc.task_id = t.id
GROUP BY p.id, p.title;
"""
res2 = subprocess.check_output(["psql", "-U", "guobiao", "-d", "labelstudio", "-c", cmd2]).decode()
print(res2)

