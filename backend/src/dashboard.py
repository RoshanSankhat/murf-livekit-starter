"""
Day 7 dashboard - shows human-help requests from the escalations table.
Reads via db.list_escalations() / db.set_escalation_status(), so it uses
the exact same Postgres connection your agent already uses.

Run with:  python dashboard.py
Then open: http://localhost:5050
"""

from flask import Flask, render_template_string, request, redirect, url_for

import db
from datetime import datetime

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
CALLS_TEMPLATE = """
<!doctype html>
<html>
<head>
<title>Call Analytics</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 2rem; background: #f7f7f8; }
  h1 { margin-bottom: 0.25rem; }
  .stats { display: flex; gap: 1rem; margin: 1.5rem 0; }
  .stat-card { background: white; padding: 1.2rem 1.6rem; border-radius: 10px; box-shadow: 0 1px 3px rgba(0,0,0,.1); min-width: 140px; }
  .stat-card .num { font-size: 2rem; font-weight: 700; }
  .stat-card .label { font-size: 0.85rem; color: #666; margin-top: 0.2rem; }
  .success .num { color: #16a34a; }
  .failed .num { color: #dc2626; }
  table { border-collapse: collapse; width: 100%; background: white; box-shadow: 0 1px 3px rgba(0,0,0,.1); margin-top: 1rem; }
  th, td { text-align: left; padding: 0.6rem 0.8rem; border-bottom: 1px solid #eee; font-size: 0.85rem; }
  th { background: #fafafa; }
  .badge { padding: 2px 8px; border-radius: 10px; font-size: 0.75rem; font-weight: 600; color: white; display: inline-block; }
  .success-badge { background: #16a34a; }
  .failed-badge { background: #dc2626; }
  .nav a { margin-right: 1rem; }
</style>
</head>
<body>
<p class="nav"><a href="{{ url_for('index') }}">Human Help Requests</a> | <a href="{{ url_for('calls') }}">Call Analytics</a></p>
<h1>Call Analytics</h1>

<div class="stats">
  <div class="stat-card">
    <div class="num">{{ stats['total'] }}</div>
    <div class="label">Total Calls</div>
  </div>
  <div class="stat-card success">
    <div class="num">{{ stats['successful'] }}</div>
    <div class="label">Successful Calls</div>
  </div>
  <div class="stat-card failed">
    <div class="num">{{ stats['failed'] }}</div>
    <div class="label">Failed Calls</div>
  </div>
  <div class="stat-card">
    <div class="num">{{ success_rate }}%</div>
    <div class="label">Success Rate</div>
  </div>
</div>

<h2>Recent Calls</h2>
<table>
<tr>
  <th>Call ID</th><th>Channel</th><th>Outcome</th><th>Reason</th>
  <th>Started</th><th>Duration (s)</th>
</tr>
{% for c in calls %}
<tr>
  <td>{{ c['call_id'] }}</td>
  <td>{{ c['channel'] }}</td>
  <td><span class="badge {{ 'success-badge' if c['outcome'] == 'success' else 'failed-badge' }}">{{ c['outcome'] }}</span></td>
  <td>{{ c['failure_reason'] or '-' }}</td>
  <td>{{ c['started_at'] }}</td>
  <td>{{ c['duration_seconds'] if c['duration_seconds'] is not none else '-' }}</td>
</tr>
{% endfor %}
</table>
</body>
</html>
"""


@app.route("/calls")
def calls():
    stats = db.get_call_stats()
    total = stats.get("total", 0) or 0
    successful = stats.get("successful", 0) or 0
    success_rate = round((successful / total) * 100, 1) if total > 0 else 0
    recent = db.list_calls(limit=25)
    return render_template_string(
        CALLS_TEMPLATE, stats=stats, success_rate=success_rate, calls=recent
    )

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