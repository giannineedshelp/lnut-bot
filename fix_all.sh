#!/bin/bash
set -e
cd ~/storage/shared/Documents/lnut-bot/In_bot || cd /storage/emulated/0/Documents/lnut-bot/In_bot || exit 1

echo "=== 1. Fix commands.py - ensure requests fallback works ==="
sed -i 's/import curl_cffi.requests as cr/    try:\n        import curl_cffi.requests as cr\n    except ImportError:\n        import requests as cr/' commands/commands.py
sed -i 's/        import curl_cffi.requests as cr/    try:\n        import curl_cffi.requests as cr\n    except ImportError:\n        import requests as cr/' commands/hub.py

echo "=== 2. Add /hub command to hub.py ==="
grep -q 'app_commands.command.*hub' commands/hub.py 2>/dev/null || {
cat >> commands/hub.py << 'EOF'

@app_commands.command(name="hub", description="Open the LanguageNut control hub")
async def hub_slash(self, interaction: Interaction):
    embed = build_hub_embed(interaction.guild_id)
    view = HubView(interaction.guild_id) 
    await interaction.response.send_message(embed=embed, view=view)

HubCog.hub = hub_slash
EOF
}

echo "=== 3. Fix main.py cogs list ==="
python3 -c "
p = 'main.py'
with open(p) as f:
    c = f.read()
# Fix cogs list - add commands.hub
import re
old = \"initial_extensions = [\\n            \\\"commands.commands\\\",\\n        ]\"
new = \"initial_extensions = [\\n            \\\"commands.commands\\\",\\n            \\\"commands.hub\\\",\\n        ]\"
if old in c:
    c = c.replace(old, new)
with open(p, 'w') as f:
    f.write(c)
print('main.py updated')
"

echo "=== 4. Delete broken admin_commands.py ==="
rm -f commands/admin_commands.py
echo "Deleted admin_commands.py"

echo "=== 5. Test compile ==="
python3 -c "import py_compile; py_compile.compile('main.py', doraise=True)" 2>&1 || python3 -m py_compile main.py 2>&1
for f in commands/commands.py commands/hub.py; do
    python3 -c "import py_compile; py_compile.compile('$f', doraise=True)" 2>&1 || python3 -m py_compile "$f" 2>&1
done
echo "=== All files compile check done ==="

echo "=== 6. Git push ==="
git add -A
git commit -m "Fix: add /hub command, delete broken admin_commands, fix imports"
git push origin main

echo "=== DONE ==="
