#!/usr/bin/env python3
# fix_skeleton_stubs.py - Fix class skeleton to show method/class stubs.
from pathlib import Path

def patch(path_str, old, new, label):
    p = Path(path_str)
    text = p.read_text()
    count = text.count(old)
    if count != 1:
        print(f"FAIL [{label}]: expected 1 match in {path_str}, found {count}")
        raise SystemExit(1)
    p.write_text(text.replace(old, new))
    print(f"OK   [{label}]")


PYTHON = "app/ingestion/languages/python_language.py"
FACTORY = "app/ingestion/chunking/chunk_factory.py"

# --- Fix 1: python_language.py ---
old_stub = "def get_class_member_stub_info(node, content: bytes):\n    \"\"\"For class-skeleton building: identify a method node and its stub signature.\n\n    Only ever called on class-body children NOT already in definition_ids (i.e.\n    things the query never captured as a function/class in the first place --\n    plain statements, docstrings, class-level assignments). Returns None for\n    anything that isn't a (possibly decorated) function, so the caller falls\n    back to rendering it as plain class-level text.\n    \"\"\"\n    target = resolve_wrapped_definition(node)\n    if target.type != \"function_definition\":\n        return None\n\n    decorators: list[str] = []\n    if node.type == \"decorated_definition\":\n        decorators = [\n            node_text(child, content)\n            for child in node.children\n            if child.type == \"decorator\"\n        ]\n\n    name = node_text(target.child_by_field_name(\"name\"), content)\n    params = node_text(target.child_by_field_name(\"parameters\"), content)\n    prefix = \"async def\" if any(child.type == \"async\" for child in target.children) else \"def\"\n\n    return {\"name\": name, \"params\": params, \"decorators\": decorators, \"prefix\": prefix}"

new_stub = "def get_class_member_stub_info(node, content: bytes):\n    \"\"\"For class-skeleton building: return a stub signature for methods and nested classes.\n\n    Called on every class-body child. Returns a dict for functions/classes so the\n    caller can render a one-line stub (e.g. 'def name(params): ...'). Returns None\n    for plain statements (variables, docstrings), so the caller renders them as-is.\n    \"\"\"\n    target = resolve_wrapped_definition(node)\n\n    if target.type == \"function_definition\":\n        decorators: list[str] = []\n        if node.type == \"decorated_definition\":\n            decorators = [\n                node_text(child, content)\n                for child in node.children\n                if child.type == \"decorator\"\n            ]\n        name = node_text(target.child_by_field_name(\"name\"), content)\n        params = node_text(target.child_by_field_name(\"parameters\"), content)\n        prefix = \"async def\" if any(child.type == \"async\" for child in target.children) else \"def\"\n        return {\"name\": name, \"params\": params, \"decorators\": decorators, \"prefix\": prefix}\n\n    if target.type == \"class_definition\":\n        name = node_text(target.child_by_field_name(\"name\"), content)\n        return {\"name\": name, \"params\": \"\", \"decorators\": [], \"prefix\": \"class\"}\n\n    return None"

patch(PYTHON, old_stub, new_stub, "python_lang.stub_info_both_kinds")

# --- Fix 2: chunk_factory.py ---
old_loop = "    member_lines: list[str] = []\n    if body is not None:\n        for child in body.children:\n            if child.id in definition_ids:\n                continue\n            if get_member_stub_info is not None:\n                try:\n                    member_info = get_member_stub_info(child, parsed.content)\n                except Exception as e:\n                    raise ChunkExtractionError(\n                        f\"Failed extracting member info for {class_name} \"\n                        f\"(node type={child.type}): {e}\"\n                    ) from e\n\n                if member_info is not None:\n                    decorators = \"\".join(\n                        f\"{decorator}\\n    \" for decorator in member_info[\"decorators\"]\n                    )\n                    prefix = member_info[\"prefix\"]\n                    keyword = f\"{prefix} \" if prefix else \"\"\n                    member_lines.append(\n                        f\"    {decorators}{keyword}\"\n                        f\"{member_info['name']}{member_info['params']}: ...\"\n                    )\n                    continue\n\n            # Not a method, not independently captured -- genuine class-level code\n            # (docstring, class-level variable/constant assignment, etc.)\n            text = node_text(child, parsed.content).strip()\n            if text:\n                indented = \"\\n\".join(\n                    f\"    {line}\" if line.strip() else line\n                    for line in text.split(\"\\n\")\n                )\n                member_lines.append(indented)"

new_loop = "    member_lines: list[str] = []\n    if body is not None:\n        for child in body.children:\n            if get_member_stub_info is not None:\n                try:\n                    member_info = get_member_stub_info(child, parsed.content)\n                except Exception as e:\n                    raise ChunkExtractionError(\n                        f\"Failed extracting member info for {class_name} \"\n                        f\"(node type={child.type}): {e}\"\n                    ) from e\n\n                if member_info is not None:\n                    decorators = \"\".join(\n                        f\"{decorator}\\n    \" for decorator in member_info[\"decorators\"]\n                    )\n                    prefix = member_info[\"prefix\"]\n                    keyword = f\"{prefix} \" if prefix else \"\"\n                    member_lines.append(\n                        f\"    {decorators}{keyword}\"\n                        f\"{member_info['name']}{member_info['params']}: ...\"\n                    )\n                    continue\n\n            # Plain class-level code (variables, docstrings, etc.) -- not a method/class\n            text = node_text(child, parsed.content).strip()\n            if text:\n                indented = \"\\n\".join(\n                    f\"    {line}\" if line.strip() else line\n                    for line in text.split(\"\\n\")\n                )\n                member_lines.append(indented)"

patch(FACTORY, old_loop, new_loop, "factory.class_skeleton.remove_definition_skip")

print("\nPatches applied. Run tests to verify.")
