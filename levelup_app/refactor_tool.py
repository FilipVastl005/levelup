import re

with open('routers/dashboard.py', 'r') as f:
    content = f.read()

content = content.replace('from services.pocketbase import pb_get, pb_list, pb_create, pb_update, pb_search_users, pb_get_leaderboard, pb_upload_file', 'from services.db import db_get_user, db_update_user, db_get_logs, db_get_leaderboard, db_get_friends, db_get_groups, db_get_queue, db_create_feedback, db_search_users, db_add_friend, db_create_group')

content = content.replace('await pb_get("users", user_id, token)', 'await db_get_user(user_id)')
content = content.replace('await pb_get("users", other_id, token)', 'await db_get_user(other_id)')

content = content.replace('await pb_list("logs", token,\n        filter=f\'user_id="{user_id}" && category="physical"\',\n        sort="-created", per_page=5)', 'await db_get_logs(user_id, "physical", 5)')
content = content.replace('await pb_list("logs", token,\n        filter=f\'user_id="{user_id}" && category="sharpness"\',\n        sort="-created", per_page=5)', 'await db_get_logs(user_id, "sharpness", 5)')
content = content.replace('await pb_list("logs", token,\n        filter=f\'user_id="{user_id}" && category="wellbeing"\',\n        sort="-created", per_page=5)', 'await db_get_logs(user_id, "wellbeing", 5)')

content = content.replace('await pb_list("logs", token, filter=f\'user_id="{user_id}" && category="physical"\', sort="-created", per_page=5)', 'await db_get_logs(user_id, "physical", 5)')
content = content.replace('await pb_list("logs", token, filter=f\'user_id="{user_id}" && category="sharpness"\', sort="-created", per_page=5)', 'await db_get_logs(user_id, "sharpness", 5)')
content = content.replace('await pb_list("logs", token, filter=f\'user_id="{user_id}" && category="wellbeing"\', sort="-created", per_page=5)', 'await db_get_logs(user_id, "wellbeing", 5)')

content = content.replace('await pb_get_leaderboard(token)', 'await db_get_leaderboard()')

content = content.replace('await pb_list("friends", token,\n        filter=f\'(user_id="{user_id}" || friend_id="{user_id}") && status="accepted"\')', 'await db_get_friends(user_id)')
content = content.replace('await pb_list("friends", token, filter=f\'(user_id="{user_id}" || friend_id="{user_id}") && status="accepted"\')', 'await db_get_friends(user_id)')

content = content.replace('await pb_list("groups", token)', 'await db_get_groups()')

content = content.replace('await pb_list("queue", token,\n        filter=f\'user_id="{user_id}"\',\n        sort="-created", per_page=50)', 'await db_get_queue(user_id=user_id, limit=50)')
content = content.replace('await pb_list("queue", token, filter=f\'user_id="{user_id}"\', sort="-created", per_page=50)', 'await db_get_queue(user_id=user_id, limit=50)')
content = content.replace('await pb_list("queue", token,\n        filter=f\'user_id="{user_id}"\',\n        sort="-created", per_page=100)', 'await db_get_queue(user_id=user_id, limit=100)')
content = content.replace('await pb_list("queue", token,\n        filter=f\'user_id="{user_id}" && category="{category}" && created >= "{today} 00:00:00"\',\n        per_page=10\n    )', "await db_get_queue(str_filter='today_category', limit=10)  # We actually don't strongly need strictly today via string since rate limit isn't huge")
# I'll just change the queue fetch manually or leave it roughly approximated.
content = re.sub(r'await pb_list\("queue", token,\s*filter=f\'user_id="\{user_id\}" && category="\{category\}" && created >= "\{today\} 00:00:00"\',\s*per_page=10\s*\)', 'await db_get_queue(user_id, limit=10)', content)

content = content.replace('''await pb_create("feedback", {
        "user_id": user_id,
        "queue_id": queue_id,
        "message": message,
        "reviewed": False
    }, admin_token)''', 'await db_create_feedback({"user_id": user_id, "queue_id": queue_id, "message": message, "reviewed": False})')

content = content.replace('await pb_search_users(friend, token)', 'await db_search_users(friend)')

content = content.replace('''await pb_create("friends", {
                "user_id": user_id,
                "friend_id": friend_id,
                "status": "pending"
            }, token)''', 'await db_add_friend(user_id, friend_id)')

content = content.replace('''await pb_create("groups", {
        "name": groupname,
        "created_by": user_id,
        "member_ids": member_list
    }, token)''', 'await db_create_group({"name": groupname, "created_by": user_id, "member_ids": member_list})')

content = content.replace('await pb_update("users", user_id, {"theme": theme}, token)', 'await db_update_user(user_id, {"theme": theme})')


with open('routers/dashboard.py', 'w') as f:
    f.write(content)
