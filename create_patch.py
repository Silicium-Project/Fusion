import re

with open('C:\\Users\\luisf\\Silicium-Project\\Fusion\\patch_runner2.py', 'w') as f:
    f.write('''import re
import sys

path = "/opt/silicium/BackEnd/internal/silicium/runner.go"
with open(path, "r", encoding="utf-8") as f:
    content = f.read()

# Add OrchestratorExportDir to struct
content = re.sub(r"MinVerifyReputation\\\\s+string\\\\n}", "MinVerifyReputation  string\\\\n\\\\tOrchestratorExportDir string\\\\n}", content)

# Add OrchestratorExportDir to ConfigFromEnv
content = re.sub(r"MinVerifyReputation:\\\\s+envDefault\\\\(.+?\\\\),", "MinVerifyReputation:  envDefault(\\"SILICIUM_MIN_VERIFY_REPUTATION\\", \\"40\\"),\\\\n\\\\t\\\\tOrchestratorExportDir: envDefault(\\"SILICIUM_ORCHESTRATOR_EXPORT_DIR\\", \\"/var/lib/silicium/network/orchestrator/export\\"),", content)

# Add args
content = re.sub(r"\\\\-\\\\-node\\\\-mode\\\\", \\"network\\\\",", "\\"----node-mode\\", \\"network\\",\\\\n\\\\t\\\\t\\"--no-network-start-emitter\\",\\\\n\\\\t\\\\t\\"--export-dir\\", cfg.OrchestratorExportDir,", content)

with open(path, "w", encoding="utf-8") as f:
    f.write(content)
print("Patched successfully")
''')
