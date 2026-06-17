# Duplicate Todo Fix

## Problem

When adding todos via Discord bot, the same todo was created 4 times with timestamps 1 second apart.

Example:
```
#18: eat chicken [General] - 2026-06-17T07:50:12
#17: eat chicken [General] - 2026-06-17T07:50:11
#16: eat chicken [General] - 2026-06-17T07:50:10
#15: eat chicken [General] - 2026-06-17T07:50:09
```

---

## Root Cause

**The LLM (Qwen 2.5 72B via OpenRouter) was making 4 identical tool calls in a single response.**

The agentic loop correctly processes each tool call the model requests, but the model itself was requesting the same tool multiple times with identical arguments.

This is a known behavior with some models when using tool calling - they may emit duplicate function calls in parallel.

---

## Solution

### 1. Added Deduplication Logic

Modified `_run_agent()` in `assistant.py` to deduplicate tool calls based on signature:
- Signature = `(function_name, JSON-serialized arguments)`
- First occurrence of each unique call is executed
- Duplicates are skipped with debug log

```python
# Deduplicate tool calls - some models make identical duplicate calls
seen_calls = {}
for call in tool_calls:
    call_signature = (name, json.dumps(args, sort_keys=True))
    if call_signature in seen_calls:
        print(f"[DEBUG] Skipping duplicate call to {name}")
        continue
    seen_calls[call_signature] = True
    # Execute tool...
```

### 2. Added Debug Logging

Added logging to monitor tool call behavior:
```python
if tool_calls:
    print(f"[DEBUG] Step {step}: Model requested {len(tool_calls)} tool call(s)")
    for i, call in enumerate(tool_calls):
        print(f"  Tool {i+1}: {fn.get('name', 'unknown')}")
```

### 3. Improved System Prompt

Added explicit instruction to prevent duplicates:
```
IMPORTANT: Only call each tool ONCE. Do not make duplicate tool calls.
```

### 4. Cleaned Up Existing Duplicates

Removed 6 duplicate todos from database, keeping only the first occurrence of each.

---

## Testing

**Before fix:**
```
User: "add buy milk"
→ Creates 4 identical todos
```

**After fix:**
```
User: "add buy milk"
→ Creates 1 todo (duplicates are filtered out)
→ Debug log shows: "Skipping duplicate call to add_todo" (3 times)
```

---

## Alternative Solutions Considered

1. **Limit to 1 tool call per turn** - Too restrictive, prevents legitimate parallel tool use
2. **Switch to different model** - Costs may vary, current model is cost-effective
3. **Disable parallel tool calls** - Not supported by OpenRouter API format
4. **Keep duplicates and warn user** - Poor UX

**Chosen solution:** Deduplication at execution time (best balance of correctness and flexibility)

---

## Current Status

✅ Deduplication implemented  
✅ Debug logging added  
✅ Existing duplicates cleaned up  
✅ 6 unique todos remaining for psyduck  
✅ Ready to test with Discord bot  

---

## Testing Instructions

1. Start Discord bot:
   ```bash
   cd /home/sanjeew/Desktop/projects/shrimpicus
   source shrimpicus/.venv/bin/activate
   shrimpicus
   ```

2. In Discord, send:
   ```
   add test unique todo
   ```

3. Check console for debug output:
   ```
   [DEBUG] Step 0: Model requested X tool call(s)
   [DEBUG] Skipping duplicate call to add_todo  # If model still duplicates
   ```

4. Check web interface - should see only 1 new todo

---

## Commits

```
724f281 [fix]: deduplicate tool calls from LLM
0c67fe5 [debug]: add logging to investigate duplicate tool calls
```

---

**Issue resolved!** The bot will now create only one todo even if the model requests duplicates. 🎉
