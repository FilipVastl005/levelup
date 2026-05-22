with open('routers/admin.py', 'r') as f: content = f.read()

content = content.replace('from services.pocketbase import pb_list, pb_update, pb_admin_token, pb_get, pb_auth', 'from services.db import db_get_admin_dashboard_data, db_update_queue, db_update_feedback')

# find admin_dashboard block
import re
start_str = "    try:\n        token = await pb_admin_token()\n        if not token:"
match_start = content.find(start_str)

end_str = "            \"feedback\": resolved_feedback\n        })"
match_end = content.find(end_str) + len(end_str)

replacement = """    try:
        data = await db_get_admin_dashboard_data()
        return templates.TemplateResponse("admin.html", {
            "request": request,
            "error": None,
            "stats": data["stats"],
            "active_users": data["active_users"],
            "active_jobs": data["active_jobs"],
            "failed_jobs": data["failed_jobs"],
            "feedback": data["feedback"]
        })"""

if match_start != -1 and match_end != -1:
    content = content[:match_start] + replacement + content[match_end:]

content = content.replace('''    token = await pb_admin_token()
    await pb_update("queue", queue_id, {"status": "pending"}, token)''', '''    await db_update_queue(queue_id, {"status": "pending"})''')

content = content.replace('''    token = await pb_admin_token()
    await pb_update("feedback", feedback_id, {"reviewed": True}, token)''', '''    await db_update_feedback(feedback_id, {"reviewed": True})''')

with open('routers/admin.py', 'w') as f: f.write(content)

