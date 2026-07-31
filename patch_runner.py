import os
p = '/opt/silicium/BackEnd/internal/silicium/runner.go'
with open(p, 'r') as f:
    c = f.read()
c = c.replace('envDefault("SILICIUM_MESH_KEY", "demo-mesh")', 'os.Getenv("SILICIUM_MESH_KEY")')
with open(p, 'w') as f:
    f.write(c)
