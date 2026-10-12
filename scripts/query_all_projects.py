import subprocess

cmd = """
SELECT p.id, p.title, count(DISTINCT t.id) as tasks, count(DISTINCT tc.id) as completions
FROM project p
LEFT JOIN task t ON t.project_id = p.id
LEFT JOIN task_completion tc ON tc.task_id = t.id
GROUP BY p.id, p.title
ORDER BY p.id DESC;
"""
res = subprocess.check_output(["psql", "-U", "guobiao", "-d", "labelstudio", "-c", cmd]).decode()
print(res)
