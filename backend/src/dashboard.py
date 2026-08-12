"""
Day 7 dashboard - shows human-help requests from the escalations table.
Reads via db.list_escalations() / db.set_escalation_status(), so it uses
the exact same Postgres connection your agent already uses.

Run with:  python dashboard.py
Then open: http://localhost:5050
"""

from flask import Flask, render_template_string, request, redirect, url_for

import db

app = Flask(__name__)

TEMPLATE = """
<!doctype html>
<html>
<head>
<title>Human Help Requests</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 2rem; background: #f7f7f8; }
  h1 { margin-bottom: 0.25rem; }
  table { border-collapse: collapse; width: 100%; background: white; box-shadow: 0 1px 3px rgba(0,0,0,.1); }
  th, td { text-align: left; padding: 0.6rem 0.8rem; border-bottom: 1px solid #eee; font-size: 0.9rem; vertical-align: top; }
  th { background: #fafafa; }
  .badge { padding: 2px 8px; border-radius: 10px; font-size: 0.75rem; font-weight: 600; color: white; display: inline-block; }
  .low { background: #6b7280; } .medium { background: #d97706; }
  .high { background: #dc2626; } .emergency { background: #7c1d1d; }
  .open { background: #2563eb; } .in_progress { background: #7c3aed; } .resolved { background: #16a34a; }
  form.inline { display: inline; }
  select, button { font-size: 0.8rem; }
  pre { white-space: pre-wrap; margin: 0; font-family: inherit; }
  .filters a { margin-right: 1rem; }
</style>
</head>
<body>
<h1>Human Help Requests</h1>
<p class="filters">
  <a href="{{ url_for('index') }}">All</a>
  <a href="{{ url_for('index', status='open') }}">Open</a>
  <a href="{{ url_for('index', status='in_progress') }}">In progress</a>
  <a href="{{ url_for('index', status='resolved') }}">Resolved</a>
</p>
<table>
<tr>
  <th>Reference</th><th>Who</th><th>Reason</th><th>Urgency</th><th>Status</th>
  <th>What happened</th><th>Checked</th><th>Lang</th><th>Follow-up</th><th>Created</th><th>Actions</th>
</tr>
{% for e in escalations %}
<tr>
  <td>{{ e['reference_id'] }}</td>
  <td>{{ e['user_id'] }}</td>
  <td>{{ e['reason_code'] }}</td>
  <td><span class="badge {{ e['urgency'] }}">{{ e['urgency'] }}</span></td>
  <td><span class="badge {{ e['status'] }}">{{ e['status'] }}</span></td>
  <td><pre>{{ e['what_happened'] }}</pre></td>
  <td><pre>{{ e['what_agent_checked'] }}</pre></td>
  <td>{{ e['language'] }}</td>
  <td>{{ e['follow_up_method'] }}</td>
  <td>{{ e['created_at'] }}</td>
  <td>
    <form class="inline" method="post" action="{{ url_for('update_status', ref=e['reference_id']) }}">
      <select name="status">
        <option value="open" {% if e['status']=='open' %}selected{% endif %}>open</option>
        <option value="in_progress" {% if e['status']=='in_progress' %}selected{% endif %}>in_progress</option>
        <option value="resolved" {% if e['status']=='resolved' %}selected{% endif %}>resolved</option>
      </select>
      <button type="submit">Update</button>
    </form>
  </td>
</tr>
{% endfor %}
</table>
</body>
</html>
"""


@app.route("/")
def index():
    status = request.args.get("status")
    rows = db.list_escalations(status=status)
    return render_template_string(TEMPLATE, escalations=rows)


@app.route("/escalations/<ref>/status", methods=["POST"])
def update_status(ref):
    new_status = request.form.get("status", "open")
    db.set_escalation_status(ref, new_status)
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True, port=5050)