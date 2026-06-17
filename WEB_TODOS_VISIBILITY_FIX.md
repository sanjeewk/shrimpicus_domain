# Web Todos Visibility Fix

## Problem

Todos added through the web interface were not visible to the Discord bot (not in RAG context, not in `list_todos` tool results).

---

## Root Cause

**Data model mismatch between web and Discord bot:**

- **Web interface**: Creates todos with `chat_id=0, user_id=2`
- **Discord bot**: Creates todos with `chat_id=2, user_id=2`
- **Database queries**: Were using `WHERE chat_id = ?` instead of `WHERE user_id = ?`

This meant:
- Bot could only see its own todos (chat_id=2)
- Web todos (chat_id=0) were invisible to bot
- RAG context was incomplete

---

## Solution

Changed all `list_*` methods in `db.py` to query by `user_id` instead of `chat_id`:

### Updated Methods:
1. ✅ `list_todos()` - `WHERE user_id = ? AND done = 0`
2. ✅ `list_habits()` - `WHERE user_id = ?`
3. ✅ `list_reminders()` - `WHERE user_id = ?`
4. ✅ `list_birthdays()` - `WHERE user_id = ?`

Since Discord bot uses `default_chat_id = 2` (which is passed as `chat_id` parameter but represents `user_id`), all queries now work correctly for both sources.

---

## Data Flow (After Fix)

```
Web Interface:
  Add todo → DB: {chat_id=0, user_id=2}
  
Discord Bot:
  Add todo → DB: {chat_id=2, user_id=2}
  
Bot queries:
  list_todos(chat_id=2) → SELECT WHERE user_id=2
  → Returns todos from BOTH web and Discord ✅
  
RAG Context:
  build_context() → Calls list_todos()
  → Includes all user data ✅
```

---

## Testing Results

**Before fix:**
```sql
SELECT * FROM todos WHERE chat_id = 2 AND done = 0
→ 0 results (web todos have chat_id=0)
```

**After fix:**
```sql
SELECT * FROM todos WHERE user_id = 2 AND done = 0
→ 3 results:
  #14: test 3 [General] - created via Web
  #12: a [General] - created via Web
  #5: Reach enlightenment [General] - created via Web
```

---

## What Works Now

✅ **Discord bot sees web-created todos**  
✅ **RAG context includes all user data**  
✅ **`list_todos` tool returns complete list**  
✅ **Bot can reference web todos in conversations**  
✅ **Unified view across Discord and web**  

---

## Testing Instructions

### 1. Start Discord Bot
```bash
cd /home/sanjeew/Desktop/projects/shrimpicus
source shrimpicus/.venv/bin/activate
shrimpicus
```

### 2. Add Todo via Web
- Visit http://127.0.0.1:5005
- Login as **psyduck**
- Add todo: "Test from web interface"

### 3. Ask Bot in Discord
```
what's on my list?
```

**Expected:** Bot should list todos from both Discord and web, including "Test from web interface" ✅

### 4. Verify RAG Context
```
add review todos to my list
```

**Expected:** Bot should understand context from all todos (web + Discord) when suggesting categories or avoiding duplicates ✅

---

## Technical Details

### Why user_id Works

The parameter name is still `chat_id` in method signatures for backward compatibility, but:
- Discord bot passes `self.default_chat_id` (which is `settings.default_user_id = 2`)
- Web interface passes `session["user_id"]` (which is `2` for psyduck)
- Both resolve to the same `user_id` in the database

So `list_todos(chat_id=2)` effectively means "list todos for user_id=2" after the fix.

---

## Commit

```
99113e6 [fix]: query todos, habits, reminders, birthdays by user_id instead of chat_id
```

---

**Issue resolved! Discord bot can now see todos created via web interface.** 🎉
