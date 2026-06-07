from google.genai import types
from db_utils import update_substance_quantity, get_all_substances
import voice_state

TOOLS = [
    types.FunctionDeclaration(
        name="answer_microfeedback",
        description="Record the user's quantity answer for the current substance awaiting feedback.",
        parameters=types.Schema(type=types.Type.OBJECT, properties={
            "level": types.Schema(type=types.Type.STRING, 
                          description="One of: A LOT, MEDIUM, LOW, SKIP")
        }, required=["level"])
    ),
    types.FunctionDeclaration(
        name="query_inventory",
        description="Answer a question about a substance's location, status, or quantity.",
        parameters=types.Schema(type=types.Type.OBJECT, properties={
            "substance_name": types.Schema(type=types.Type.STRING,
                                   description="Name of the substance to look up")
        }, required=["substance_name"])
    )
]

def handle_answer_microfeedback(args, context: dict) -> str:
    # Bulletproof args parsing: convert whatever object args is to a string and find the keyword!
    args_str = str(args).upper()
    
    if "A LOT" in args_str:
        level = "A LOT"
    elif "MEDIUM" in args_str:
        level = "MEDIUM"
    elif "LOW" in args_str:
        level = "LOW"
    elif "SKIP" in args_str:
        level = "SKIP"
    else:
        return f"Invalid level. I received arguments: {args_str}. Please say A LOT, MEDIUM, LOW, or SKIP."
    
    tag_id = context.get("pending_tag_id")
    if not tag_id:
        with open("/home/vince/GitHub/ambient-intelligence-internship/python/tool_log.txt", "a") as f:
            f.write(f"Early return: no tag_id. args: {args_str}\n")
        return "No substance is currently awaiting feedback."
    
    if level != "SKIP":
        update_substance_quantity(tag_id, level)
    
    # Signal dashboard to dismiss the modal
    voice_state.mark_resolved(level)
    with open("/home/vince/GitHub/ambient-intelligence-internship/python/tool_log.txt", "a") as f:
        f.write(f"Successfully marked resolved for {tag_id} with level {level}\n")
    return f"Recorded: {level}."

def handle_query_inventory(args: dict) -> str:
    name = args.get("substance_name", "").strip()
    # Fuzzy match: case-insensitive LIKE search
    all_substances = get_all_substances()
    matches = [s for s in all_substances 
               if name.lower() in s["substance_name"].lower()]
    
    if not matches:
        return f"I couldn't find any substance matching '{name}'."
    
    s = matches[0]  # take best match
    parts = [f"{s['substance_name']} is in {s['location']}"]
    parts.append(f"and is currently {s['state'].replace('_', ' ').title()}")
    
    if s["quantity_level"] != "UNKNOWN":
        parts.append(f"with {s['quantity_level'].lower()} remaining")
    
    return ", ".join(parts) + "."
