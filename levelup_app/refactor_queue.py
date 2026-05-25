with open('services/queue.py', 'r') as f:
    content = f.read()

content = content.replace("""    # Also save to PocketBase queue collection for dashboard display
    from services.pocketbase import pb_admin_token, pb_create
    token = await pb_admin_token()
    await pb_create("queue", {
        "job_id": job_id,
        "user_id": user_id,
        "category": category,
        "description": description,
        "status": "pending"
    }, token)""", """    # Save to SQLite DB for dashboard display
    from services.db import db_create_queue
    await db_create_queue({
        "job_id": job_id,
        "user_id": user_id,
        "category": category,
        "description": description,
        "status": "pending"
    })""")

# I need to match the large processing block.
start = content.find("            # Update PocketBase status")
end = content.find('''                # Update job file and move to completed''')

if start != -1 and end != -1:
    new_processing_block = """            # Update SQLite state
            from services.db import db_update_queue, db_get_queue, db_get_user, db_create_log, db_update_user
            from services.ollama import ask_coach
            from services.xp import calculate_level, apply_streak_bonus, calculate_total_level, update_streak
            from datetime import date

            try:
                # Update queue record in DB
                queue_records = await db_get_queue(str_filter=f'job_id="{job_id}"', limit=1)
                db_queue_id = None
                if queue_records.get("items"):
                    db_queue_id = queue_records["items"][0]["id"]
                    await db_update_queue(db_queue_id, {"status": "processing"})

                user = await db_get_user(job["user_id"])
                category = job["category"]
                level = user.get(f"{category}_level", 1)
                baseline = user.get(f"{category}_baseline", 5)
                streak = user.get("current_streak", 0)

                # Load screenshot from disk if exists
                image_bytes = None
                if job.get("screenshot_path") and os.path.exists(job["screenshot_path"]):
                    from PIL import Image
                    import io
                    with open(job["screenshot_path"], "rb") as f:
                        raw_bytes = f.read()
                    
                    img = Image.open(io.BytesIO(raw_bytes))
                    img.thumbnail((800, 800))
                    buffer = io.BytesIO()
                    img.save(buffer, format="JPEG", quality=85)
                    image_bytes = buffer.getvalue()

                coach_result = await ask_coach(
                    category, job["description"], level, baseline, image_bytes
                )

                xp_awarded = coach_result.get("xp_awarded", 10)
                message = coach_result.get("message", "")
                verified = coach_result.get("verified", True)

                new_streak = update_streak(user.get("last_log_date"), streak)
                xp_awarded = apply_streak_bonus(xp_awarded, new_streak)

                xp_key = f"{category}_xp"
                level_key = f"{category}_level"
                current_xp = user.get(xp_key, 0)
                new_xp = current_xp + xp_awarded
                new_level = calculate_level(new_xp)

                physical_level = user.get("physical_level", 1)
                sharpness_level = user.get("sharpness_level", 1)
                wellbeing_level = user.get("wellbeing_level", 1)

                if category == "physical": physical_level = new_level
                elif category == "sharpness": sharpness_level = new_level
                elif category == "wellbeing": wellbeing_level = new_level

                new_total_level = calculate_total_level(physical_level, sharpness_level, wellbeing_level)
                new_total_xp = user.get("total_xp", 0) + xp_awarded

                # Save to logs 
                await db_create_log({
                    "user_id": job["user_id"],
                    "category": category,
                    "description": job["description"],
                    "xp_awarded": xp_awarded,
                    "ai_response": message,
                    "verified": verified
                })

                # Update user stats
                await db_update_user(job["user_id"], {
                    xp_key: new_xp,
                    level_key: new_level,
                    "total_xp": new_total_xp,
                    "total_level": new_total_level,
                    "physical_level": physical_level,
                    "sharpness_level": sharpness_level,
                    "wellbeing_level": wellbeing_level,
                    "current_streak": new_streak,
                    "last_log_date": date.today().isoformat()
                })

                # Update queue record in DB
                if db_queue_id:
                    await db_update_queue(db_queue_id, {
                        "status": "completed",
                        "xp_awarded": xp_awarded,
                        "ai_response": message,
                        "verified": verified
                    })

"""
    content = content[:start] + new_processing_block + content[end:]


content = content.replace('''                if pb_queue_id:
                    await pb_update("queue", pb_queue_id, {
                        "status": "failed",
                        "ai_response": str(e)
                    }, token)''', '''                if db_queue_id:
                    await db_update_queue(db_queue_id, {
                        "status": "failed",
                        "ai_response": str(e)
                    })''')

with open('services/queue.py', 'w') as f:
    f.write(content)

