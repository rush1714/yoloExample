import subprocess
import json

cmd = """
SELECT t.id, t.data, tc.result, tc.was_cancelled, tc.created_at
FROM task t
JOIN task_completion tc ON tc.task_id = t.id
WHERE t.project_id = 29;
"""
res = subprocess.check_output(["psql", "-U", "guobiao", "-d", "labelstudio", "-t", "-A", "-c", cmd]).decode()
lines = [l for l in res.split('\n') if l.strip()]
print(f"Total completions in DB for project 29: {len(lines)}")

# Let's also check if there are other projects created around that time or since then
cmd2 = """
SELECT id, title, created_at FROM project ORDER BY id DESC;
"""
res2 = subprocess.check_output(["psql", "-U", "guobiao", "-d", "labelstudio", "-c", cmd2]).decode()
print(res2)
